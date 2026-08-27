"""
Chunked Pipeline — video va audio ni vaqt bo'yicha qismlarga bo'lib,
TTS va MERGE ni parallel ravishda bajarish (pipeline parallelism).

Asosiy g'oya:
1. Video ni vaqt bo'yicha N chunk'ga bo'lish (masalan, 3 daqiqa)
2. Har bir chunk uchun TTS + MERGE mustaqil ravishda bajarish
3. Barcha chunklarni bitta final video'ga birlashtirish

Natija: ~1.7-2x tezroq ishlash (chunk TTS parallel, chunk MERGE parallel).

Usage:
    from backend.services.chunked_pipeline import ChunkedPipeline

    pipeline = ChunkedPipeline(
        video_path="/path/to/video.mp4",
        segments=[...],  # translated_segments
        output_dir="/path/to/output",
        voice_name="uz-UZ-SardorNeural",
        video_id="abc123",
    )
    final_path = pipeline.run()
"""

import os
import re
import subprocess
import logging
import tempfile
import shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class VideoChunk:
    """Bir video chunk'ning ma'lumotlari."""
    index: int
    video_path: str
    start_sec: float
    end_sec: float
    segments: list[dict] = field(default_factory=list)


def get_video_duration(video_path: str) -> float:
    """FFprobe orqali video davomiyligini olish (soniyada)."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def split_video_into_chunks(
    video_path: str,
    output_dir: str,
    chunk_duration_sec: int = 180,
    overlap_sec: float = 1.5,
) -> list[VideoChunk]:
    """
    Video ni vaqt bo'yicha chunk'larga bo'lish (FFmpeg extract, bez transcoding).

    Args:
        video_path: Kirish video fayl yo'li
        output_dir: Chiqish papkasi
        chunk_duration_sec: Har bir chunkning davomiyligi (soniya)
        overlap_sec: Chunklar orasidagi overlap (soniya)

    Returns:
        VideoChunk ro'yxati
    """
    duration = get_video_duration(video_path)
    if duration <= 0:
        raise ValueError(f"Video davomiyligini aniqlab bo'lmadi: {video_path}")

    chunks = []
    start = 0.0
    idx = 0

    while start < duration:
        end = min(start + chunk_duration_sec, duration)

        # Overlap: keyingi chunk bu chunk bilan overlap qiladi
        # (faqat keyingi chunk uchun, bu chunk uchun emas)
        chunk_path = os.path.join(output_dir, f"video_chunk_{idx:02d}.mp4")

        # FFmpeg: video qismini extract qilish (copy, bez transcoding)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",  # copy codec — tez va sifatsiz yo'qotish
            "-avoid_negative_ts", "make_zero",
            chunk_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            logger.warning(f"Chunk {idx} extract xatosi: {result.stderr[-300:]}")
            # Fallback: transcoding bilan
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(start),
                "-to", str(end),
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac",
                chunk_path,
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=True)

        chunks.append(VideoChunk(
            index=idx,
            video_path=chunk_path,
            start_sec=start,
            end_sec=end,
        ))

        # Keyingi chunk uchun overlap bilan
        start = end - overlap_sec if end < duration else end
        idx += 1

    logger.info(f"Video {len(chunks)} chunk'ga bo'lindi ({chunk_duration_sec}s har biri)")
    return chunks


def split_segments_into_chunks(
    segments: list[dict],
    video_chunks: list[VideoChunk],
) -> list[list[dict]]:
    """
    Segmentlarni video chunk'larga moslab bo'lish.

    Har bir segment o'z vaqt oralig'iga qarab tegishli chunk'ga tushadi.
    Overlap chunk'lardagi segmentlar taqrorlanishi mumkin (xavfsiz — TTS keyin
    overlap qismini trim qiladi).

    Args:
        segments: Tarjima qilingan segmentlar [{start, end, text, ...}]
        video_chunks: Video chunk'lar (start_sec, end_sec bilan)

    Returns:
        Har bir chunk uchun segmentlar ro'yxati
    """
    chunk_segments = [[] for _ in video_chunks]

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)
        seg_mid = (seg_start + seg_end) / 2

        # Segment ni o'z vaqtiga eng yaqin chunk'ga joylashtirish
        assigned = False
        for i, chunk in enumerate(video_chunks):
            # Overlap bilan: chunk.start - overlap <= seg_start < chunk.end
            chunk_start = chunk.start_sec - settings.CHUNK_OVERLAP_SEC if i > 0 else chunk.start_sec
            if chunk_start <= seg_mid < chunk.end_sec:
                chunk_segments[i].append(seg)
                assigned = True
                break

        # Agar hech qaysi chunk'ga tushmagan bo'lsa — oxirgi chunk'ga
        if not assigned and video_chunks:
            chunk_segments[-1].append(seg)

    # Log
    for i, segs in enumerate(chunk_segments):
        if segs:
            logger.info(f"Chunk {i}: {len(segs)} segment "
                       f"({segs[0]['start']:.1f}s - {segs[-1]['end']:.1f}s)")

    return chunk_segments


def concat_video_chunks(
    chunk_paths: list[str],
    output_path: str,
    timeout: int = 300,
) -> str:
    """
    Bir nechta video chunk'ni bitta final video'ga birlashtirish.

    FFmpeg concat demuxer ishlatiladi — bez transcoding, juda tez.

    Args:
        chunk_paths: Chunk video fayllar yo'llari (ketma-ketlikda)
        output_path: Chiqish fayl yo'li
        timeout: FFmpeg timeout (soniya)

    Returns:
        Final video fayl yo'li
    """
    if not chunk_paths:
        raise ValueError("Birlashtirish uchun chunk'lar topilmadi")

    if len(chunk_paths) == 1:
        # Bitta chunk — faqat copy
        shutil.copy2(chunk_paths[0], output_path)
        return output_path

    # Concat list faylini yaratish
    concat_file = output_path + ".concat.txt"
    with open(concat_file, "w") as f:
        for path in chunk_paths:
            # FFmpeg concat uchun nisbiy yo'l yoki to'liq yo'l
            f.write(f"file '{os.path.abspath(path)}'\n")

    try:
        # FFmpeg concat demuxer
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-c", "copy",  # copy codec — tez
            "-movflags", "+faststart",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

        if result.returncode != 0:
            logger.warning(f"Concat copy xatosi, transcoding bilan qayta urinish: {result.stderr[-300:]}")
            # Fallback: transcoding bilan
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c:v", "libx264", "-preset", "ultrafast",
                "-c:a", "aac", "-b:a", "192k",
                "-movflags", "+faststart",
                output_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode != 0:
                raise RuntimeError(f"Concat xatosi: {result.stderr[-500:]}")

        return output_path

    finally:
        # Tozalash
        try:
            os.remove(concat_file)
        except OSError:
            pass


def cleanup_chunk_files(chunks: list[VideoChunk], output_dir: str) -> None:
    """Chunk vaqtinchalik fayllarini tozalash."""
    for chunk in chunks:
        try:
            if os.path.exists(chunk.video_path):
                os.remove(chunk.video_path)
        except OSError as exc:
            logger.warning(f"Chunk faylini tozalashda xatolik: {exc}")

    # TTS chunk fayllarini ham tozalash
    tts_pattern = os.path.join(output_dir, "chunk_*_tts")
    import glob
    for tts_dir in glob.glob(tts_pattern):
        try:
            shutil.rmtree(tts_dir)
        except OSError:
            pass

    # Merged chunk fayllarini tozalash
    merged_pattern = os.path.join(output_dir, "merged_chunk_*.mp4")
    for merged_file in glob.glob(merged_pattern):
        try:
            os.remove(merged_file)
        except OSError:
            pass
