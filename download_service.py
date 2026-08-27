# download_service.py — DEPRECATED
# External HTTP download service removed. Worker now uses yt-dlp directly
# via backend/services/downloader.py. This file is kept only for reference.

import sys

if __name__ == "__main__":
    print("download_service.py is deprecated. Downloads are handled inside the worker with yt-dlp.")
    sys.exit(0)
