"""
Modal GPU Integration — ai-dubber uchun elastic compute.

_MODAL=False bo'lsa (default) — hech narsa o'zgarmaydi, local ishlaydi.
_MODAL=True bo'lsa — merge va TTS Modal cloud'da GPU bilan qayta ishlanadi.

O'rnatish:
  1. pip install modal
  2. modal token new (modal.com'da ro'yxatdan o'tgan bo'lish kerak)
  3. .env ga qo'shing: MODAL_API_KEY=modal-xxx

Foydalanish:
  backend/config.py ga qo'shing: MODAL_ENABLED: bool = False
  .env ga qo'shing: MODAL_ENABLED=true

Agar Modal yoqilgan bo'lsa — merger.py va synthesizer.py avtomatik
Modal function'larni chaqiradi. Yoqilmasa — hech narsa o'zgarmaydi.
"""

import os
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Modal tekshiruvi
# ─────────────────────────────────────────────────────────────────────────────

_MODAL_AVAILABLE = False
_modal = None

def _check_modal() -> bool:
    """Modal mavjudligini tekshirish (bir marta)."""
    global _MODAL_AVAILABLE, _modal
    if _MODAL_AVAILABLE or _modal is not None:
        return _MODAL_AVAILABLE

    try:
        import modal as _m
        _modal = _m
        # Token mavjudligini tekshirish
        api_key = os.environ.get("MODAL_API_KEY", "")
        if api_key:
            _MODAL_AVAILABLE = True
            logger.info("✅ Modal available — GPU compute enabled")
        else:
            logger.info("ℹ️ Modal installed but no MODAL_API_KEY — using local compute")
        return _MODAL_AVAILABLE
    except ImportError:
        logger.info("ℹ️ Modal not installed — using local compute (pip install modal to enable)")
        return False


def is_modal_enabled() -> bool:
    """Modal yoqilganmi?"""
    return os.environ.get("MODAL_ENABLED", "false").lower() == "true" and _check_modal()


# ─────────────────────────────────────────────────────────────────────────────
# Modal App definition (only created if Modal is enabled)
# ─────────────────────────────────────────────────────────────────────────────

def _get_app():
    """Get or create Modal App."""
    if not _check_modal():
        return None
    return _modal.App("ai-dubber")


# TTS Image — edge-tts va kerakli kutubxonalar
def _get_tts_image():
    """TTS uchun Modal image."""
    return (_modal.Image.debian_slim()
        .pip_install("edge-tts", "pydub"))


# Merge Image — ffmpeg kerak
def _get_merge_image():
    """Merge uchun Modal image."""
    return (_modal.Image.debian_slim()
        .apt_install("ffmpeg"))


# ─────────────────────────────────────────────────────────────────────────────
# Modal Functions
# ─────────────────────────────────────────────────────────────────────────────

def modal_merge_chunk(
    video_chunk_path: str,
    dubbed_audio_path: str,
    output_path: str,
    audio_filter_complex: str,
) -> str:
    """
    Modal'da GPU bilan video chunk merge.

    Agar Modal yoqilgan bo'lsa — cloud'da ishlaydi.
    Yoqilmasa — local ffmpeg ishlatadi (fallback).

    Args:
        video_chunk_path: Video chunk fayl yo'li
        dubbed_audio_path: Dublyaj audio fayl
        output_path: Chiqish fayl yo'li
        audio_filter_complex: FFmpeg audio filtergraph

    Returns:
        Chiqish fayl yo'li
    """
    if not is_modal_enabled():
        return None  # Modal yoqilmagan — local ishlatilsin

    app = _get_app()
    if not app:
        return None

    try:
        @app.function(
            image=_get_merge_image(),
            cpu=2,
            timeout=600,
        )
        def _merge_remote(video_bytes: bytes, audio_bytes: bytes, audio_filter: str) -> bytes:
            """Remote merge function."""
            import tempfile, os
            with tempfile.TemporaryDirectory() as tmp:
                v_path = os.path.join(tmp, "video.mp4")
                a_path = os.path.join(tmp, "audio.wav")
                o_path = os.path.join(tmp, "output.mp4")

                with open(v_path, "wb") as f:
                    f.write(video_bytes)
                with open(a_path, "wb") as f:
                    f.write(audio_bytes)

                cmd = [
                    "ffmpeg", "-y",
                    "-i", v_path, "-i", a_path,
                    "-filter_complex", audio_filter,
                    "-map", "0:v:0", "-map", "[final]",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k",
                    "-movflags", "+faststart",
                    o_path,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode != 0:
                    raise RuntimeError(f"Modal merge failed: {result.stderr[-500:]}")

                with open(o_path, "rb") as f:
                    return f.read()

        # Fayllarni o'qish
        with open(video_chunk_path, "rb") as f:
            video_bytes = f.read()
        with open(dubbed_audio_path, "rb") as f:
            audio_bytes = f.read()

        # Modal'da ishga tushirish
        result_bytes = _merge_remote.remote(video_bytes, audio_bytes, audio_filter_complex)

        # Natijani saqlash
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(result_bytes)

        logger.info(f"✅ Modal merge completed: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Modal merge failed, falling back to local: {e}")
        return None  # Fallback to local


def modal_tts_segment(
    text: str,
    voice: str,
    output_path: str,
) -> str:
    """
    Modal'da GPU bilan TTS synthesis.

    Agar Modal yoqilgan bo'lsa — cloud'da ishlaydi.
    Yoqilmasa — None qaytaradi (local ishlatilsin).

    Args:
        text: Matn
        voice: Ovoz (masalan: uz-UZ-SardorNeural)
        output_path: Chiqish fayl yo'li

    Returns:
        Chiqish fayl yo'li yoki None
    """
    if not is_modal_enabled():
        return None

    app = _get_app()
    if not app:
        return None

    try:
        @app.function(
            image=_get_tts_image(),
            cpu=1,
            timeout=120,
        )
        def _tts_remote(text: str, voice: str) -> bytes:
            """Remote TTS function."""
            import asyncio, tempfile, os
            import edge_tts

            async def _synthesize():
                with tempfile.TemporaryDirectory() as tmp:
                    out = os.path.join(tmp, "audio.mp3")
                    communicate = edge_tts.Communicate(text, voice)
                    await communicate.save(out)
                    with open(out, "rb") as f:
                        return f.read()

            return asyncio.run(_synthesize())

        result_bytes = _tts_remote.remote(text, voice)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(result_bytes)

        logger.info(f"✅ Modal TTS completed: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Modal TTS failed, falling back to local: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Utility: Modal status info
# ─────────────────────────────────────────────────────────────────────────────

def get_modal_status() -> dict:
    """Modal holati haqida ma'lumot."""
    enabled = is_modal_enabled()
    installed = _check_modal()
    api_key = bool(os.environ.get("MODAL_API_KEY", ""))

    return {
        "modal_enabled": enabled,
        "modal_installed": installed,
        "modal_api_key_set": api_key,
        "status": "active" if enabled else ("installed" if installed else "not_installed"),
        "instructions": (
            "To enable Modal:\n"
            "  1. pip install modal\n"
            "  2. modal token new\n"
            "  3. .env ga qo'shing: MODAL_ENABLED=true\n"
            "  4. .env ga qo'shing: MODAL_API_KEY=modal-xxx\n"
            "  5. Workerlarni qayta ishga tushiring"
        ) if not enabled else "Modal is active — GPU compute enabled",
    }
