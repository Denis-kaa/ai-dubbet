"""
Cookie refresher service — runs inside container under Xvfb and refreshes Youtube cookies periodically.
"""
import time
import os
import logging
from backend.services import cookie_manager

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

INTERVAL_HOURS = int(os.getenv("COOKIE_REFRESH_HOURS", "12"))
EMAIL = os.getenv("YOUTUBE_EMAIL")
PASSWORD = os.getenv("YOUTUBE_PASSWORD")

if not EMAIL or not PASSWORD:
    logger.error("YOUTUBE_EMAIL and/or YOUTUBE_PASSWORD not set in environment. Exiting.")
    raise SystemExit(1)

logger.info(f"Starting cookie refresher: every {INTERVAL_HOURS} hours")

while True:
    try:
        logger.info("Refreshing cookies now...")
        ok = cookie_manager.get_or_refresh_cookies_sync(EMAIL, PASSWORD)
        logger.info(f"Refresh result: {ok}")
    except Exception as e:
        logger.exception(f"Cookie refresh failed: {e}")

    # Sleep until next run
    time.sleep(INTERVAL_HOURS * 3600)
