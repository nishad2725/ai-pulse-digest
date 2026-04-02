"""
main.py — Entry point for the Daily AI News Digest system.

Usage:
    python main.py          # Start scheduler (fires 4x daily: 10 AM, 1 PM, 4 PM, 8 PM EDT)
    python main.py --test   # Run pipeline immediately, then exit

The pipeline: news_fetcher → summarizer → email_builder → email_sender

Logging: RotatingFileHandler to logs/digest.log (5MB × 3 backups) + stdout.
"""

import argparse
import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler

import certifi

# Fix macOS Python SSL certificate verification (must be set before any HTTPS connections)
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())

# Load .env BEFORE importing project modules — ensures os.getenv() works everywhere
from dotenv import load_dotenv
load_dotenv()

# Project modules — imported after load_dotenv()
import email_builder
import email_sender
import news_fetcher
import summarizer

from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure root logger with rotating file + stdout handlers."""
    os.makedirs("logs", exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Rotating file handler: max 5MB, keep 3 backups
    file_handler = RotatingFileHandler(
        "logs/digest.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Console handler for local dev visibility
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def run_digest() -> None:
    """
    Execute the full digest pipeline:
    1. Fetch articles via OpenAI web_search_preview
    2. Summarize and categorize with GPT-4o
    3. Render HTML email via Jinja2
    4. Deliver via SendGrid
    """
    import datetime
    run_start = datetime.datetime.now()
    logger.info("=" * 60)
    logger.info(f"=== Digest run starting at {run_start.strftime('%Y-%m-%d %H:%M:%S')} ===")
    logger.info("=" * 60)

    # Stage 1: Fetch
    articles = []
    try:
        articles = news_fetcher.fetch_articles()
        logger.info(f"[1/4] Fetched {len(articles)} articles")
        if len(articles) < 5:
            logger.warning(
                f"Only {len(articles)} articles fetched (expected ≥5). "
                "Sending digest with available data."
            )
    except Exception as e:
        logger.error(f"[1/4] Article fetch failed: {e}", exc_info=True)
        logger.warning("Proceeding with empty article list — email will note no stories found")

    # Stage 2: Summarize
    digest_data = {}
    try:
        digest_data = summarizer.build_digest(articles)
        categories_found = [c["name"] for c in digest_data.get("categories", [])]
        logger.info(f"[2/4] Summarization complete. Categories: {categories_found}")
    except Exception as e:
        logger.error(f"[2/4] Summarization failed: {e}", exc_info=True)
        logger.warning("Using empty digest data — email will have minimal content")
        digest_data = summarizer._empty_digest()

    # Stage 3: Render email
    subject, html_body = "", ""
    try:
        subject, html_body = email_builder.render(digest_data)
        logger.info(f"[3/4] Email rendered. Subject: {subject}")
    except Exception as e:
        logger.error(f"[3/4] Email rendering failed: {e}", exc_info=True)
        raise

    # Stage 4: Send
    try:
        email_sender.send(subject, html_body)
        logger.info("[4/4] Email delivered successfully")
    except Exception as e:
        logger.error(f"[4/4] Email delivery failed after retry: {e}", exc_info=True)
        raise

    elapsed = (datetime.datetime.now() - run_start).total_seconds()
    logger.info(f"=== Digest run complete in {elapsed:.1f}s ===")


def main() -> None:
    setup_logging()

    parser = argparse.ArgumentParser(
        description="Daily AI News Digest — fetches, summarizes, and emails top AI news"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run the full pipeline immediately without waiting for the cron schedule",
    )
    args = parser.parse_args()

    if args.test:
        logger.info("--test flag detected: running pipeline immediately")
        run_digest()
        logger.info("Test run complete. Exiting.")
        return

    # Production: start APScheduler with cron trigger — 4x daily
    tz = os.getenv("SCHEDULE_TIMEZONE", "America/New_York")
    hours = os.getenv("SCHEDULE_HOURS", "10,13,16,20")   # 10 AM, 1 PM, 4 PM, 8 PM
    minute = int(os.getenv("SCHEDULE_MINUTE", "0"))

    scheduler = BackgroundScheduler(timezone=tz)
    scheduler.add_job(
        run_digest,
        trigger="cron",
        hour=hours,
        minute=minute,
        id="digest_job",
        # Fire job if process starts within 5 min of a scheduled time
        misfire_grace_time=7200,  # 2 hours — fires on Mac wake even if late
        # Don't stack runs if one is still executing at next trigger
        coalesce=True,
    )
    scheduler.start()

    next_run = scheduler.get_job("digest_job").next_run_time
    logger.info(
        f"Scheduler started. Digest fires at {hours.replace(',', ':00, ')}:00 {tz} daily. "
        f"Next run: {next_run}"
    )
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown signal received — stopping scheduler")
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped. Goodbye.")
        sys.exit(0)


if __name__ == "__main__":
    main()
