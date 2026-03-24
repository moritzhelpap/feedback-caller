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

import glob
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
latest_call_sid: str | None = None

def build_system_prompt(name: str, topic: str) -> str:
    return f"""\
You are making a warm, friendly phone call to {name} on behalf of their friend Moritz.
You have just delivered this opening message: "{topic}"

Your goals:
1. Stay focused on exactly that topic — do not invent new subjects or go off on tangents.
2. Listen and respond naturally to what {name} says.
3. Keep replies brief — 2 to 4 sentences max, since this is a phone call.
4. When the conversation feels complete, or {name} signals they want to wrap up, say a warm goodbye.
   End your final message with the exact token: [HANGUP]

Be warm and genuine. Never use filler like "Certainly!" or "Of course!".\
"""


def build_greeting(name: str, topic: str) -> str:
    return f"Hey {name}! {topic}"


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
    global latest_call_sid
    call_sid = request.form.get("CallSid", "unknown")
    latest_call_sid = call_sid
    name = request.args.get("name", "there")
    topic = request.args.get("topic", "just checking in")

    # Hang up if Twilio's answering machine detection flagged this as voicemail/fax
    answered_by = request.form.get("AnsweredBy", "")
    if answered_by in ("machine_start", "machine_end_beep", "machine_end_silence", "fax"):
        print(f"[{call_sid[:8]}] Voicemail detected ({answered_by}) — hanging up.")
        response = VoiceResponse()
        response.hangup()
        return Response(str(response), mimetype="text/xml")

    greeting = build_greeting(name, topic)
    system_prompt = build_system_prompt(name, topic)

    transcripts.setdefault(call_sid, [])
    # Store system prompt alongside transcript so /respond can retrieve it
    transcripts[call_sid] = {"system": system_prompt, "messages": [], "name": name}
    transcripts[call_sid]["messages"].append({"role": "assistant", "content": greeting})

    response = VoiceResponse()
    # Pass name+topic through to /respond so it can rebuild context if needed
    action = f"/respond?name={name}&topic={topic}"
    gather = Gather(
        input="speech",
        action=action,
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say(greeting, voice="Polly.Joanna")
    response.append(gather)
    response.redirect(f"/no-input?name={name}&topic={topic}")
    return Response(str(response), mimetype="text/xml")


# ---------------------------------------------------------------------------
# Webhook: Isaac said something
# ---------------------------------------------------------------------------

@app.route("/respond", methods=["POST"])
def respond():
    call_sid = request.form.get("CallSid", "unknown")
    speech = request.form.get("SpeechResult", "").strip()
    confidence = request.form.get("Confidence", "n/a")
    name = request.args.get("name", "there")
    topic = request.args.get("topic", "just checking in")

    print(f"[{call_sid[:8]}] {name} said (confidence {confidence}): {speech!r}")

    # Rebuild entry if Railway restarted and lost in-memory state
    if call_sid not in transcripts:
        transcripts[call_sid] = {"system": build_system_prompt(name, topic), "messages": []}

    if speech:
        transcripts[call_sid]["messages"].append({"role": "user", "content": speech})

    claude_resp = anthropic_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        system=transcripts[call_sid]["system"],
        messages=transcripts[call_sid]["messages"],
    )
    ai_text: str = claude_resp.content[0].text.strip()
    print(f"[{call_sid[:8]}] Claude: {ai_text!r}")

    transcripts[call_sid]["messages"].append({"role": "assistant", "content": ai_text})

    hang_up = "[HANGUP]" in ai_text
    spoken_text = ai_text.replace("[HANGUP]", "").strip()

    action = f"/respond?name={name}&topic={topic}"
    response = VoiceResponse()
    if hang_up:
        response.say(spoken_text, voice="Polly.Joanna")
        response.hangup()
    else:
        gather = Gather(
            input="speech",
            action=action,
            method="POST",
            speech_timeout="auto",
            language="en-US",
        )
        gather.say(spoken_text, voice="Polly.Joanna")
        response.append(gather)
        response.redirect(f"/no-input?name={name}&topic={topic}")

    return Response(str(response), mimetype="text/xml")


# ---------------------------------------------------------------------------
# Webhook: no speech detected
# ---------------------------------------------------------------------------

@app.route("/no-input", methods=["POST"])
def no_input():
    name = request.args.get("name", "there")
    topic = request.args.get("topic", "just checking in")

    action = f"/respond?name={name}&topic={topic}"
    response = VoiceResponse()
    gather = Gather(
        input="speech",
        action=action,
        method="POST",
        speech_timeout="auto",
        language="en-US",
    )
    gather.say("Sorry, I didn't quite catch that — are you still there?", voice="Polly.Joanna")
    response.append(gather)
    response.say(f"Alright, I'll let you go — take care, {name}!", voice="Polly.Joanna")
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

    entry = transcripts.get(call_sid)
    if entry and entry.get("messages"):
        _save_transcript(call_sid, entry["messages"], call_status, duration, entry.get("name", "Caller"))

    return "", 204


# ---------------------------------------------------------------------------
# Transcript retrieval
# ---------------------------------------------------------------------------

@app.route("/transcript", methods=["GET"])
def get_transcript():
    call_sid = request.args.get("call_sid") or latest_call_sid
    if not call_sid:
        return jsonify({"error": "No transcripts available yet"}), 404
    entry = transcripts.get(call_sid)
    if not entry:
        return jsonify({"error": f"Transcript not found for call_sid={call_sid}"}), 404
    messages = entry.get("messages", [])
    return jsonify({
        "call_sid": call_sid,
        "message_count": len(messages),
        "messages": messages,
    })


@app.route("/transcripts", methods=["GET"])
def list_transcripts():
    in_memory = [
        {
            "call_sid": sid,
            "message_count": len(entry.get("messages", [])),
            "preview": (entry.get("messages") or [{}])[0].get("content", "")[:120],
        }
        for sid, entry in transcripts.items()
    ]
    saved_files = sorted(glob.glob("transcript_*.txt"), reverse=True)
    return jsonify({
        "in_memory": in_memory,
        "saved_files": saved_files,
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _save_transcript(call_sid: str, messages: list[dict], status: str, duration: str, name: str = "Caller"):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"transcript_{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write("CALL TRANSCRIPT\n")
        f.write("=" * 60 + "\n")
        f.write(f"Date       : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Call SID   : {call_sid}\n")
        f.write(f"Status     : {status}\n")
        f.write(f"Duration   : {duration}s\n")
        f.write("=" * 60 + "\n\n")

        for msg in messages:
            speaker = "Claude" if msg["role"] == "assistant" else name
            f.write(f"[{speaker}]\n{msg['content']}\n\n")

    print(f"Transcript saved → {filename}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Starting Flask on port {port} ...")
    app.run(host="0.0.0.0", port=port, debug=False)
