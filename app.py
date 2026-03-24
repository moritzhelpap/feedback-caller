"""
Twilio outbound call app with Claude AI conversation and transcript saving.
Deployed on Railway — no local tunnel needed.

Flow:
  1. Deploy to Railway (see instructions)
  2. Set env vars in Railway dashboard
  3. Visit https://your-app.railway.app/make-call in a browser to trigger the call
  4. Twilio calls Isaac, webhooks hit Railway
  5. Claude responds naturally to speech
  6. Transcript printed to Railway logs when done
"""

import os
from datetime import datetime
from flask import Flask, request, Response, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
import anthropic
from dotenv import load_dotenv

load_dotenv()  # no-op on Railway (env vars set in dashboard), works locally

app = Flask(__name__)

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
twilio_client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))

# In-memory transcript store keyed by call SID
transcripts: dict[str, list[dict]] = {}

SYSTEM_PROMPT = """\
You are making a warm, friendly phone call to Isaac on behalf of his friend Moritz.
Isaac is about to travel to the US for a wedding.

Your goals for this call:
1. Have a genuine, warm conversation — not scripted or stiff.
2. You already greeted him and wished him well at the start, so don't repeat that greeting.
3. Check in: ask if there is anything still open or pending on his side that needs to be handled before he leaves.
4. Listen and respond helpfully and naturally to whatever he says.
5. Keep your replies brief — 2 to 4 sentences max, since this is a phone call.
6. When the conversation feels complete, or Isaac signals he wants to wrap up, say a warm goodbye.
   End your final message with the exact token: [HANGUP]

Be conversational, warm, and genuine. Never use filler like "Certainly!" or "Of course!".\
"""

INITIAL_GREETING = (
    "Hey Isaac, it's great to catch you! I just wanted to quickly reach out — "
    "wishing you an amazing trip to the US and an absolutely unforgettable wedding, "
    "that's going to be so special! Before you head off, I wanted to check in — "
    "is there anything still open on your end that needs taking care of?"
)


# ---------------------------------------------------------------------------
# Trigger: initiate the outbound call (visit this URL in a browser)
# ---------------------------------------------------------------------------

@app.route("/make-call", methods=["GET", "POST"])
def make_call():
    base_url = os.getenv("BASE_URL", request.host_url.rstrip("/"))
    target = os.getenv("TARGET_PHONE_NUMBER")
    from_number = os.getenv("TWILIO_PHONE_NUMBER")

    if not target or not from_number:
        return jsonify({"error": "TARGET_PHONE_NUMBER or TWILIO_PHONE_NUMBER not set"}), 500

    call = twilio_client.calls.create(
        to=target,
        from_=from_number,
        url=f"{base_url}/answer",
        status_callback=f"{base_url}/status",
        status_callback_event=["completed"],
        status_callback_method="POST",
    )
    print(f"Call initiated → SID: {call.sid}, to: {target}")
    return jsonify({"status": "call initiated", "call_sid": call.sid, "to": target})


# ---------------------------------------------------------------------------
# Webhook: call answered
# ---------------------------------------------------------------------------

@app.route("/answer", methods=["POST"])
def answer():
    call_sid = request.form.get("CallSid", "unknown")
    transcripts.setdefault(call_sid, [])
    transcripts[call_sid].append({"role": "assistant", "content": INITIAL_GREETING})

    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(INITIAL_GREETING, voice="Polly.Joanna")
    response.append(gather)

    # If Isaac says nothing, re-prompt gently
    response.redirect("/no-input")
    return Response(str(response), mimetype="text/xml")


# ---------------------------------------------------------------------------
# Webhook: Isaac said something
# ---------------------------------------------------------------------------

@app.route("/respond", methods=["POST"])
def respond():
    call_sid = request.form.get("CallSid", "unknown")
    speech = request.form.get("SpeechResult", "").strip()
    confidence = request.form.get("Confidence", "n/a")

    print(f"[{call_sid[:8]}] Isaac said (confidence {confidence}): {speech!r}")

    transcripts.setdefault(call_sid, [])
    if speech:
        transcripts[call_sid].append({"role": "user", "content": speech})

    # Build message history for Claude (exclude the initial assistant greeting
    # from context if it would confuse the model — keep it for completeness)
    messages = transcripts[call_sid]

    claude_resp = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    ai_text: str = claude_resp.content[0].text.strip()
    print(f"[{call_sid[:8]}] Claude: {ai_text!r}")

    transcripts[call_sid].append({"role": "assistant", "content": ai_text})

    hang_up = "[HANGUP]" in ai_text
    spoken_text = ai_text.replace("[HANGUP]", "").strip()

    response = VoiceResponse()
    if hang_up:
        response.say(spoken_text, voice="Polly.Joanna")
        response.hangup()
    else:
        gather = Gather(
            input="speech",
            action="/respond",
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(spoken_text, voice="Polly.Joanna")
        response.append(gather)
        response.redirect("/no-input")

    return Response(str(response), mimetype="text/xml")


# ---------------------------------------------------------------------------
# Webhook: no speech detected
# ---------------------------------------------------------------------------

@app.route("/no-input", methods=["POST"])
def no_input():
    call_sid = request.form.get("CallSid", "unknown")
    nudge = "Sorry, I didn't quite catch that — are you still there?"

    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action="/respond",
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(nudge, voice="Polly.Joanna")
    response.append(gather)
    # Hang up after two rounds of silence
    response.say("Alright, I'll let you go — take care, Isaac!", voice="Polly.Joanna")
    response.hangup()
    return Response(str(response), mimetype="text/xml")


# ---------------------------------------------------------------------------
# Webhook: call status / completion → save transcript
# ---------------------------------------------------------------------------

@app.route("/status", methods=["POST"])
def status():
    call_sid = request.form.get("CallSid", "unknown")
    call_status = request.form.get("CallStatus", "unknown")
    duration = request.form.get("CallDuration", "?")
    print(f"[{call_sid[:8]}] Call ended — status={call_status}, duration={duration}s")

    if call_sid in transcripts and transcripts[call_sid]:
        _save_transcript(call_sid, transcripts[call_sid], call_status, duration)

    return "", 204


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_transcript(call_sid: str, messages: list[dict], status: str, duration: str):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"transcript_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("CALL TRANSCRIPT — Isaac Farewell Call\n")
        f.write("=" * 60 + "\n")
        f.write(f"Date       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Call SID   : {call_sid}\n")
        f.write(f"Status     : {status}\n")
        f.write(f"Duration   : {duration}s\n")
        f.write("=" * 60 + "\n\n")

        for msg in messages:
            speaker = "Claude" if msg["role"] == "assistant" else "Isaac"
            f.write(f"[{speaker}]\n{msg['content']}\n\n")

    print(f"Transcript saved → {filename}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Flask on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False)
