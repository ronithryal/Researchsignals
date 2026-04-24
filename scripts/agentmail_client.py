"""
AgentMail API client.

Reads AGENTMAIL_API_KEY from .env — never hardcode keys here.
API docs: https://docs.agentmail.to
"""

import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.agentmail.to/v0"


def _headers() -> dict:
    key = os.environ.get("AGENTMAIL_API_KEY", "")
    if not key:
        raise RuntimeError(
            "\n\nAGENTMAIL_API_KEY is not set.\n"
            "1. Copy .env.example to .env\n"
            "2. Go to https://agentmail.to → Dashboard → API Keys\n"
            "3. Paste your key next to AGENTMAIL_API_KEY= in .env\n"
        )
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def create_inbox(username: str) -> dict:
    """Create a new inbox. Returns {address, username, ...}."""
    resp = httpx.post(
        f"{BASE_URL}/inboxes",
        headers=_headers(),
        json={"username": username},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def list_emails(address: str, limit: int = 10) -> list[dict]:
    """List recent email threads for an inbox."""
    resp = httpx.get(
        f"{BASE_URL}/inboxes/{address}/threads",
        headers=_headers(),
        params={"limit": limit},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("threads", [])


def get_email_body(address: str, thread_id: str) -> str:
    """Get the text body of a specific email thread."""
    resp = httpx.get(
        f"{BASE_URL}/inboxes/{address}/threads/{thread_id}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    messages = resp.json().get("messages", [])
    if not messages:
        return ""
    return messages[0].get("text", "") or messages[0].get("html", "")


def wait_for_email(address: str, subject_contains: str, timeout_seconds: int = 120) -> str:
    """
    Poll until an email arrives whose subject contains the given string.
    Returns the email body. Raises TimeoutError if nothing arrives in time.
    """
    deadline = time.time() + timeout_seconds
    print(f"  Waiting for email to {address} with subject containing '{subject_contains}'...")
    while time.time() < deadline:
        threads = list_emails(address)
        for thread in threads:
            if subject_contains.lower() in thread.get("subject", "").lower():
                print(f"  Found: {thread['subject']}")
                return get_email_body(address, thread["id"])
        time.sleep(5)
    raise TimeoutError(f"No email matching '{subject_contains}' arrived within {timeout_seconds}s")
