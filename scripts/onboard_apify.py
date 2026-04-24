"""
Apify onboarding script.

What this does:
  1. Creates an AgentMail inbox for the Apify signup
  2. Prints the signup URL and inbox address to use
  3. Waits for the verification email
  4. Prints instructions to retrieve the API key

You still need to:
  - Complete the signup form at console.apify.com (this script gives you the email to use)
  - Copy the API token and paste it into .env next to APIFY_API_TOKEN=

Run: python scripts/onboard_apify.py
"""

import json
from pathlib import Path
from agentmail_client import create_inbox, wait_for_email

REGISTRY_PATH = Path(__file__).parent / "service_registry.json"


def main():
    registry = json.loads(REGISTRY_PATH.read_text())
    service = next(s for s in registry["services"] if s["name"] == "Apify")

    # create a dedicated inbox for Apify
    print("Creating AgentMail inbox for Apify signup...")
    inbox = create_inbox("defi-signal-apify")
    address = inbox["address"]
    print(f"\n  Inbox created: {address}")

    # save inbox to registry
    service["agentmail_inbox"] = address
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))

    print(f"""
=============================================================
APIFY SIGNUP — ACTION REQUIRED
=============================================================

1. Go to: {service['signup_url']}

2. Use this email address when signing up:
       {address}

3. Use any password you want (store it in your password manager).

4. Waiting for the verification email...
""")

    body = wait_for_email(address, subject_contains="verify", timeout_seconds=180)
    print("  Verification email received.")
    print("  Check the email body for a verification link and click it:")
    print()
    print(body[:800])

    print(f"""
=============================================================
NEXT STEP — GET YOUR API TOKEN
=============================================================

1. Go to: {service['dashboard_url']}

2. Click "Create new token"

3. Copy the token (starts with "apify_api_...")

4. Open .env and paste it here:
       APIFY_API_TOKEN=<paste here>

5. Run: python scripts/verify_apify.py  (to confirm it works)
=============================================================
""")

    # mark status
    service["status"] = "email_verified"
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


if __name__ == "__main__":
    main()
