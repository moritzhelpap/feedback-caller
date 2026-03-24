"""
Initiates the outbound call via Twilio.
The Flask app runs on Railway — no local server needed.

Usage:
    python make_call.py
    # or set CALL_RECIPIENT_NAME and CALL_TOPIC env vars (done by mcp_server.py)
"""

import os
import sys
import time
import urllib3
import requests
from urllib.parse import urlencode
from twilio.rest import Client
from twilio.http.http_client import TwilioHttpClient
from dotenv import load_dotenv

# Workaround for corporate SSL inspection — remove once network issue is resolved
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

REQUIRED = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "TARGET_PHONE_NUMBER",
    "BASE_URL",
]

missing = [k for k in REQUIRED if not os.getenv(k)]
if missing:
    print(f"ERROR: Missing environment variables: {', '.join(missing)}")
    print("Please fill in your .env file first.")
    sys.exit(1)

http_client = TwilioHttpClient()
http_client.session.verify = False
client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), http_client=http_client)
base_url = os.getenv("BASE_URL").rstrip("/")

target = os.getenv("TARGET_PHONE_NUMBER")
name = os.getenv("CALL_RECIPIENT_NAME", "")
topic = os.getenv("CALL_TOPIC", "")

print(f"Calling {target}" + (f" — topic: {topic}" if topic else "") + " ...")

# Pass name + topic to Railway so the greeting and system prompt can be personalised
params = {}
if name:
    params["name"] = name
if topic:
    params["topic"] = topic
query = ("?" + urlencode(params)) if params else ""

call = client.calls.create(
    to=target,
    from_=os.getenv("TWILIO_PHONE_NUMBER"),
    url=f"{base_url}/answer{query}",
    status_callback=f"{base_url}/status",
    status_callback_event=["completed"],
    status_callback_method="POST",
    machine_detection="Enable",
)

print(f"Call initiated! SID: {call.sid}")
print("Waiting for call to complete ...")

TERMINAL_STATUSES = {"completed", "failed", "busy", "no-answer", "canceled"}
while True:
    status = client.calls(call.sid).fetch().status
    if status in TERMINAL_STATUSES:
        print(f"Call ended — status: {status}")
        break
    time.sleep(3)

if status == "completed":
    transcript_url = f"{base_url}/transcript?call_sid={call.sid}"
    print(f"\nFetching transcript from {transcript_url} ...")
    try:
        resp = requests.get(transcript_url, verify=False, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print("\n" + "=" * 60)
        print("CALL TRANSCRIPT")
        print("=" * 60)
        for msg in data.get("messages", []):
            speaker = "Claude" if msg["role"] == "assistant" else name or "Caller"
            print(f"\n[{speaker}]\n{msg['content']}")
        print("\n" + "=" * 60)
    except Exception as e:
        print(f"Could not fetch transcript: {e}")
        print("Check Railway logs: https://railway.app")
