import os
import tempfile
import unittest
from backend.services.downloader import _build_yt_opts, get_yt_dlp


class TestDownloaderCookies(unittest.TestCase):
    def test_build_yt_opts_with_readonly_cookies(self):
        # Create temporary mock cookies file with read-only permissions
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"# Netscape HTTP Cookie File\n")
            cookie_path = f.name

        os.chmod(cookie_path, 0o444)
        original_cookies_path = os.getenv("YOUTUBE_COOKIES_PATH")
        os.environ["YOUTUBE_COOKIES_PATH"] = cookie_path

        try:
            opts, temp_cookie_path = _build_yt_opts()

            assert temp_cookie_path is not None
            assert temp_cookie_path != cookie_path
            assert opts.get("cookiefile") == temp_cookie_path
            assert os.path.exists(temp_cookie_path)
        finally:
            if original_cookies_path is not None:
                os.environ["YOUTUBE_COOKIES_PATH"] = original_cookies_path
            else:
                os.environ.pop("YOUTUBE_COOKIES_PATH", None)

            if temp_cookie_path and os.path.exists(temp_cookie_path):
                os.remove(temp_cookie_path)
            if os.path.exists(cookie_path):
                os.remove(cookie_path)

    def test_get_yt_dlp_cleanup(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"# Netscape HTTP Cookie File\n")
            cookie_path = f.name

        os.chmod(cookie_path, 0o444)
        original_cookies_path = os.getenv("YOUTUBE_COOKIES_PATH")
        os.environ["YOUTUBE_COOKIES_PATH"] = cookie_path

        try:
            created_temp_path = None
            with get_yt_dlp() as ydl:
                created_temp_path = ydl.params.get("cookiefile")
                assert created_temp_path is not None
                assert os.path.exists(created_temp_path)

            # After exiting context manager, temp cookie file must be deleted
            assert not os.path.exists(created_temp_path)
        finally:
            if original_cookies_path is not None:
                os.environ["YOUTUBE_COOKIES_PATH"] = original_cookies_path
            else:
                os.environ.pop("YOUTUBE_COOKIES_PATH", None)

            if os.path.exists(cookie_path):
                os.remove(cookie_path)


if __name__ == "__main__":
    unittest.main()
