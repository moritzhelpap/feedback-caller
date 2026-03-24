"""
MCP server exposing a make_call tool.

Usage (add to Claude Desktop config):
  {
    "mcpServers": {
      "feedback-caller": {
        "command": "python",
        "args": ["C:/Users/helpap moritz/feedback-caller/mcp_server.py"]
      }
    }
  }

Then in Claude Desktop you can say:
  "Call Isaac about the wedding logistics"
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("feedback-caller")

BASE_DIR = Path(__file__).parent
CONTACTS_FILE = BASE_DIR / "contacts.json"


def _load_contacts() -> dict:
    if not CONTACTS_FILE.exists():
        return {}
    with open(CONTACTS_FILE, encoding="utf-8") as f:
        return json.load(f)


@mcp.tool()
def make_call(name: str, topic: str) -> str:
    """
    Call a person from your contacts about a specific topic.

    Args:
        name:  The contact's name (must exist in contacts.json).
        topic: What the call is about — shapes the AI's conversation.
    """
    contacts = _load_contacts()

    # Case-insensitive lookup
    number = next(
        (v for k, v in contacts.items() if k.lower() == name.lower()), None
    )
    if not number:
        available = ", ".join(contacts.keys()) or "none"
        return f"Contact '{name}' not found. Available contacts: {available}"

    # Pass name, topic, and phone number as env vars to make_call.py
    env = os.environ.copy()
    env["TARGET_PHONE_NUMBER"] = number
    env["CALL_RECIPIENT_NAME"] = name
    env["CALL_TOPIC"] = topic

    result = subprocess.run(
        [sys.executable, str(BASE_DIR / "make_call.py")],
        env=env,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return f"Call failed:\n{result.stderr.strip()}"

    return result.stdout.strip()
