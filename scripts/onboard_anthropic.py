"""
Anthropic onboarding script.

Anthropic requires a credit card and doesn't send a simple verification link —
the signup is mostly manual. This script creates the inbox and prints instructions.

Run: python scripts/onboard_anthropic.py
"""

import json
from pathlib import Path
from agentmail_client import create_inbox

REGISTRY_PATH = Path(__file__).parent / "service_registry.json"


def main():
    registry = json.loads(REGISTRY_PATH.read_text())
    service = next(s for s in registry["services"] if s["name"] == "Anthropic")

    print("Creating AgentMail inbox for Anthropic signup...")
    inbox = create_inbox("defi-signal-anthropic")
    address = inbox["address"]
    print(f"\n  Inbox created: {address}")

    service["agentmail_inbox"] = address
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"""
=============================================================
ANTHROPIC SIGNUP — ACTION REQUIRED
=============================================================

1. Go to: {service['signup_url']}

2. Use this email address:
       {address}

3. Add a credit card (required for API access).

4. Once logged in, go to: {service['dashboard_url']}

5. Click "Create Key"

6. Copy the key (starts with "sk-ant-...")

7. Open .env and paste it here:
       ANTHROPIC_API_KEY=<paste here>

8. Run: python scripts/verify_anthropic.py  (to confirm it works)
=============================================================
""")

    service["status"] = "inbox_created"
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


if __name__ == "__main__":
    main()
