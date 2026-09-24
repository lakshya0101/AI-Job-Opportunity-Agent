import os
from typing import Optional

import requests


RESEND_API_URL = "https://api.resend.com/emails"


def send_email(
    recipient: str,
    subject: str,
    html: str,
    sender: Optional[str] = None,
) -> dict:
    """Send an email through Resend."""

    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY environment variable is not set."
        )

    sender = sender or os.getenv(
        "EMAIL_SENDER",
        "onboarding@resend.dev",
    )

    payload = {
        "from": sender,
        "to": [recipient],
        "subject": subject,
        "html": html,
    }

    response = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def send_daily_report(
    recipient: str,
    subject: str,
    html: str,
) -> dict:
    """Send the daily job report."""

    return send_email(
        recipient=recipient,
        subject=subject,
        html=html,
    )
