import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
DEFAULT_SENDER = "onboarding@resend.dev"


def _prepare_attachment(attachment_path: Union[str, Path]) -> Dict[str, str]:
    """
    Validate and encode a file for Resend attachment payload.
    """
    path = Path(attachment_path).resolve()

    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Attachment file not found at: {path}")

    if path.stat().st_size == 0:
        raise ValueError(f"Attachment file is empty: {path}")

    if path.suffix.lower() not in {".xlsx", ".pdf", ".csv", ".txt"}:
        raise ValueError(f"Unsupported attachment file type '{path.suffix}': {path}")

    with open(path, "rb") as file_obj:
        encoded_content = base64.b64encode(file_obj.read()).decode("utf-8")

    return {
        "filename": path.name,
        "content": encoded_content,
    }


def send_email(
    recipient: str,
    subject: str,
    html: str,
    sender: Optional[str] = None,
    attachment_path: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Send an email via Resend API with optional attachments.
    
    API Key is securely retrieved from RESEND_API_KEY environment variable.
    """
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key or not api_key.strip():
        raise RuntimeError("RESEND_API_KEY environment variable is not set or empty.")

    sender_env = (os.getenv("EMAIL_SENDER") or "").strip()
    sender_email = (sender or "").strip() or sender_env or DEFAULT_SENDER

    payload: Dict[str, Any] = {
        "from": sender_email,
        "to": [recipient],
        "subject": subject,
        "html": html,
    }

    if attachment_path:
        attachment_obj = _prepare_attachment(attachment_path)
        payload["attachments"] = [attachment_obj]

    try:
        response = requests.post(
            RESEND_API_URL,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        response.raise_for_status()
        return response.json()

    except requests.RequestException as exc:
        # Avoid leaking sensitive tokens or full authorization header in error logs
        error_msg = f"Failed to send email via Resend API: {exc}"
        if hasattr(exc, "response") and exc.response is not None:
            try:
                err_data = exc.response.json()
                error_msg += f" | Details: {err_data}"
            except Exception:
                error_msg += f" | Status code: {exc.response.status_code}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from exc


def send_daily_report(
    recipient: str,
    subject: str,
    html: str,
    attachment_path: Optional[Union[str, Path]] = None,
    sender: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send the daily job opportunity report email with optional Excel attachment.
    """
    return send_email(
        recipient=recipient,
        subject=subject,
        html=html,
        sender=sender,
        attachment_path=attachment_path,
    )


if __name__ == "__main__":
    import sys
    
    test_recipient = os.getenv("JOB_REPORT_EMAIL", "lakshyadogra05@gmail.com")
    print(f"Manual Email Dispatch Tool")
    print(f"Recipient: {test_recipient}")
    print(f"Sender: {os.getenv('EMAIL_SENDER', DEFAULT_SENDER)}")

    if not os.getenv("RESEND_API_KEY"):
        print("ERROR: RESEND_API_KEY environment variable is missing. Set it to send test email.")
        sys.exit(1)

    print("Sending test verification email...")
    try:
        res = send_email(
            recipient=test_recipient,
            subject="🚀 Test Email Verification — AI Job Opportunity Agent",
            html="<h2>Resend Integration Test</h2><p>Your AI Job Opportunity Agent email setup is operational!</p>",
        )
        print("Email sent successfully! Response:", res)
    except Exception as e:
        print("Error sending test email:", e)
        sys.exit(1)
