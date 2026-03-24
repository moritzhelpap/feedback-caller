"""
Initiates the outbound call to Isaac via Twilio.
Run this AFTER the Flask app and ngrok are running.

Usage:
    python make_call.py
"""

import os
import sys
from twilio.rest import Client
from dotenv import load_dotenv

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

client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
base_url = os.getenv("BASE_URL").rstrip("/")

print(f"Calling {os.getenv('TARGET_PHONE_NUMBER')} ...")

call = client.calls.create(
    to=os.getenv("TARGET_PHONE_NUMBER"),
    from_=os.getenv("TWILIO_PHONE_NUMBER"),
    url=f"{base_url}/answer",
    status_callback=f"{base_url}/status",
    status_callback_event=["completed"],
    status_callback_method="POST",
)

print(f"Call initiated! SID: {call.sid}")
print("Watch the Flask terminal for live conversation logs.")
print("Transcript will be saved automatically when the call ends.")
