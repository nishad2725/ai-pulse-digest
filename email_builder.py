"""
email_builder.py — Renders the HTML email digest using Jinja2.

Loads the Gmail-safe HTML template from templates/digest_email.html and
renders it with the digest data. Returns (subject, html_body) tuple.
"""

import logging
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)


def _get_jinja_env() -> Environment:
    """Build Jinja2 environment pointing at the templates/ directory."""
    # Support running from any working directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(base_dir, "templates")
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(digest_data: dict) -> tuple[str, str]:
    """
    Render the HTML email and build the subject line.

    Args:
        digest_data: Output from summarizer.build_digest()

    Returns:
        (subject, html_body) tuple ready for SendGrid
    """
    env = _get_jinja_env()
    template = env.get_template("digest_email.html")

    try:
        html_body = template.render(**digest_data)
    except Exception as e:
        logger.error(f"Jinja2 template render failed: {e}")
        raise

    top_n = len(digest_data.get("top_5", []))
    date = digest_data.get("date", "Today")
    subject = f"\U0001f916 Daily AI Digest \u2014 {date} | Top {top_n} Stories"

    logger.info(f"Email rendered. Subject: {subject}")
    return subject, html_body
