"""
Dune Analytics onboarding script.

Run: python scripts/onboard_dune.py
"""

import json
from pathlib import Path
from agentmail_client import create_inbox, wait_for_email

REGISTRY_PATH = Path(__file__).parent / "service_registry.json"


def main():
    registry = json.loads(REGISTRY_PATH.read_text())
    service = next(s for s in registry["services"] if s["name"] == "Dune")

    print("Creating AgentMail inbox for Dune signup...")
    inbox = create_inbox("defi-signal-dune")
    address = inbox["address"]
    print(f"\n  Inbox created: {address}")

    service["agentmail_inbox"] = address
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"""
=============================================================
DUNE SIGNUP — ACTION REQUIRED  (Phase 6, not needed for MVP)
=============================================================

1. Go to: {service['signup_url']}

2. Use this email address:
       {address}

3. Waiting for verification email...
""")

    body = wait_for_email(address, subject_contains="confirm", timeout_seconds=180)
    print("  Verification email received. Check for a confirmation link:")
    print()
    print(body[:600])

    print(f"""
=============================================================
NEXT STEP — GET YOUR API KEY
=============================================================

1. Go to: {service['dashboard_url']}

2. Click "Create new API key"

3. Copy the key

4. Open .env and paste it here:
       DUNE_API_KEY=<paste here>
=============================================================
""")

    service["status"] = "email_verified"
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


if __name__ == "__main__":
    main()
