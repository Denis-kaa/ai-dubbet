"""Проверка воспроизведения MP4 через headless Chromium.

Запуск на сервере:
    /opt/ai-dubber/venv/bin/python deploy/e2e_video_playback.py

Тест намеренно использует публичный media endpoint без авторизации: доступ к
самому файлу уже проверяется API, а здесь проверяется поведение реального
HTML5 video элемента.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("AI_DUBBER_BASE_URL", "http://127.0.0.1:8000")
JOB_ID = os.environ.get(
    "AI_DUBBER_PLAYBACK_JOB",
    "3ae1064f-1294-4de3-92d1-e0b5419c60ad",
)
VIDEO_URL = f"{BASE_URL}/api/outputs/{JOB_ID}/video"


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content(f'<video id="video" controls src="{VIDEO_URL}"></video>')
    page.wait_for_function(
        "document.querySelector('#video').readyState >= 1",
        timeout=30_000,
    )
    metadata = page.locator("#video").evaluate(
        "video => ({"
        "readyState: video.readyState,"
        "duration: video.duration,"
        "videoWidth: video.videoWidth,"
        "videoHeight: video.videoHeight,"
        "networkState: video.networkState,"
        "error: video.error ? video.error.code : null"
        "})"
    )
    print(json.dumps(metadata, ensure_ascii=True))
    assert metadata["readyState"] >= 1
    assert metadata["duration"] > 0
    assert metadata["videoWidth"] > 0
    assert metadata["videoHeight"] > 0
    assert metadata["error"] is None
    browser.close()
