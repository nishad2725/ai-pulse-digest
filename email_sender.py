"""
email_sender.py — Delivers the digest email via SendGrid with one retry.

Uses the SendGrid Python SDK. On first failure, waits 60 seconds and retries
once. If the retry also fails, logs the error and re-raises so the caller
can handle it.
"""

import logging
import os
import time

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Content, Email, Mail, To

logger = logging.getLogger(__name__)


def send(subject: str, html_body: str) -> None:
    """
    Send the digest email via SendGrid.
    Retries once after 60 seconds on failure.

    Raises:
        Exception: if both send attempts fail.
    """
    _attempt_send(subject, html_body, attempt=1)


def _attempt_send(subject: str, html_body: str, attempt: int) -> None:
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("FROM_EMAIL")
    to_email = os.getenv("TO_EMAIL")

    if not all([api_key, from_email, to_email]):
        missing = [k for k, v in {
            "SENDGRID_API_KEY": api_key,
            "FROM_EMAIL": from_email,
            "TO_EMAIL": to_email,
        }.items() if not v]
        raise ValueError(f"Missing required environment variables: {missing}")

    message = Mail(
        from_email=Email(from_email),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content("text/html", html_body),
    )

    try:
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        message_id = response.headers.get("X-Message-Id", "unknown")
        logger.info(
            f"Email sent successfully (attempt {attempt}). "
            f"Status: {response.status_code}, Message-ID: {message_id}"
        )
    except Exception as e:
        if attempt == 1:
            logger.warning(
                f"SendGrid send failed (attempt 1): {e}. "
                f"Retrying in 60 seconds..."
            )
            time.sleep(60)
            _attempt_send(subject, html_body, attempt=2)
        else:
            logger.error(
                f"SendGrid send failed on retry (attempt 2): {e}. "
                f"Giving up — email not delivered."
            )
            raise
