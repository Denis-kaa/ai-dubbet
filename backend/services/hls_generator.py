"""
HLS Generator — video chunk'larni HLS formatiga aylantirish.

Progressive playback uchun:
1. Video chunk'larini HLS segmentlarga bo'lish
2. Playlist (m3u8) yaratish
3. Har bir ready chunk'ni playlist'ga qo'shish
4. Frontend player uchun streaming

Usage:
    from backend.services.hls_generator import HLSGenerator

    generator = HLSGenerator(
        job_id="abc123",
        output_dir="/outputs/abc123/hls",
    )

    # Birinchi chunk tayyor bo'lganda
    generator.add_ready_segment(
        chunk_index=0,
        video_path="/outputs/abc123/chunk_00.mp4",
        duration=180.0,
    )

    # Playlist ni yangilash
    generator.update_playlist()

    # Keyingi chunk
    generator.add_ready_segment(
        chunk_index=1,
        video_path="/outputs/abc123/chunk_01.mp4",
        duration=180.0,
    )
    generator.update_playlist()
"""

import os
import subprocess
import json
import logging
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class HLSSegment:
    """HLS segment ma'lumotlari."""
    index: int
    filename: str
    duration: float
    uri: str
    ready: bool = False


@dataclass
class HLSPlaylist:
    """HLS playlist ma'lumotlari."""
    target_duration: int = 6  # Har bir segmentning maqsadli davomiyligi
    media_sequence: int = 0
    version: int = 3
    segments: list[HLSSegment] = field(default_factory=list)


class HLSGenerator:
    """
    HLS (HTTP Live Streaming) generator.

    Video chunk'larni HLS formatiga aylantiradi:
    - .m3u8 playlist
    - .ts yoki .m4s segmentlar
    - Progressive playback support
    """

    def __init__(
        self,
        job_id: str,
        output_dir: str,
        segment_duration: int = 6,
    ):
        """
        Args:
            job_id: Job identifikatori
            output_dir: Chiqish papkasi
            segment_duration: Har bir segmentning davomiyligi (soniya)
        """
        self.job_id = job_id
        self.output_dir = Path(output_dir)
        self.segment_duration = segment_duration
        self.segments: list[HLSSegment] = []
        self._segment_counter = 0

        # HLS papkasini yaratish
        self.hls_dir = self.output_dir / "hls"
        self.hls_dir.mkdir(parents=True, exist_ok=True)

    def add_ready_segment(
        self,
        chunk_index: int,
        video_path: str,
        duration: float,
    ) -> Optional[str]:
        """
        Tayyor video chunk'ni HLS segmentga aylantirish.

        Args:
            chunk_index: Chunk raqami
            video_path: Video fayl yo'li
            duration: Video davomiyligi (soniya)

        Returns:
            Segment fayl yo'li yoki None
        """
        if not os.path.exists(video_path):
            logger.error(f"Video not found: {video_path}")
            return None

        # Segment fayl nomi
        segment_filename = f"segment_{self._segment_counter:03d}.m4s"
        segment_path = self.hls_dir / segment_filename

        # Video'ni HLS segmentga aylantirish (FFmpeg)
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "zerolatency",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "mp4",
            "-movflags", "frag_keyframe+empty_moov",
            str(segment_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"FFmpeg HLS error: {result.stderr[-300:]}")
                return None

            # Segment qo'shish
            segment = HLSSegment(
                index=chunk_index,
                filename=segment_filename,
                duration=duration,
                uri=segment_filename,
                ready=True,
            )
            self.segments.append(segment)
            self._segment_counter += 1

            logger.info(f"HLS segment ready: {segment_filename} ({duration:.1f}s)")
            return str(segment_path)

        except Exception as e:
            logger.error(f"HLS segment creation failed: {e}")
            return None

    def update_playlist(self) -> str:
        """
        M3U8 playlist'ni yangilash.

        Returns:
            Playlist fayl yo'li
        """
        # Segmentlarni indeks bo'yicha saralash
        sorted_segments = sorted(self.segments, key=lambda s: s.index)

        # M3U8 yaratish
        lines = [
            "#EXTM3U",
            f"#EXT-X-VERSION:{3}",
            f"#EXT-X-TARGETDURATION:{self.segment_duration}",
            f"#EXT-X-MEDIA-SEQUENCE:{self._segment_counter - len(sorted_segments)}",
            "",
        ]

        for segment in sorted_segments:
            if segment.ready:
                lines.append(f"#EXTINF:{segment.duration:.3f},")
                lines.append(segment.uri)
                lines.append("")

        # Playlist faylga yozish
        playlist_path = self.hls_dir / "playlist.m3u8"
        with open(playlist_path, "w") as f:
            f.write("\n".join(lines))

        logger.info(f"HLS playlist updated: {len(sorted_segments)} segments")
        return str(playlist_path)

    def get_playlist_url(self) -> str:
        """Playlist URL'ni qaytarish."""
        return f"/outputs/{self.job_id}/hls/playlist.m3u8"

    def get_segment_count(self) -> int:
        """Tayyor segmentlar soni."""
        return len([s for s in self.segments if s.ready])

    def get_total_duration(self) -> float:
        """Jumla davomiylik."""
        return sum(s.duration for s in self.segments if s.ready)

    def cleanup(self):
        """HLS fayllarini tozalash."""
        import shutil
        if self.hls_dir.exists():
            shutil.rmtree(self.hls_dir)
            logger.info(f"HLS directory cleaned: {self.hls_dir}")


class ProgressiveHLSManager:
    """
    Progressive HLS boshqaruvchisi.

    Chunk'lar tayyor bo'lishi bilan playlist'ni yangilaydi
    va frontend player ga streaming qiladi.
    """

    def __init__(self, job_id: str, output_dir: str):
        self.job_id = job_id
        self.output_dir = output_dir
        self.hls = HLSGenerator(job_id, output_dir)
        self._chunks_ready: dict[int, str] = {}
        self._all_chunks: dict[int, dict] = {}

    def register_chunk(
        self,
        chunk_index: int,
        video_path: str,
        duration: float,
    ):
        """
        Chunk ni ro'yxatdan o'tkazish (hali tayyor bo'lmasligi mumkin).
        """
        self._all_chunks[chunk_index] = {
            "video_path": video_path,
            "duration": duration,
            "ready": False,
        }

    def publish_chunk(self, chunk_index: int):
        """
        Chunk tayyor bo'lganda publish qilish.
        """
        if chunk_index not in self._all_chunks:
            logger.error(f"Chunk {chunk_index} not registered")
            return

        chunk_info = self._all_chunks[chunk_index]
        if chunk_info["ready"]:
            logger.warning(f"Chunk {chunk_index} already published")
            return

        # HLS segment yaratish
        segment_path = self.hls.add_ready_segment(
            chunk_index=chunk_index,
            video_path=chunk_info["video_path"],
            duration=chunk_info["duration"],
        )

        if segment_path:
            chunk_info["ready"] = True
            self._chunks_ready[chunk_index] = segment_path

            # Playlist'ni yangilash
            self.hls.update_playlist()

            logger.info(
                f"Chunk {chunk_index} published! "
                f"({len(self._chunks_ready)}/{len(self._all_chunks)} ready)"
            )

    def get_status(self) -> dict:
        """Hozirgi holat."""
        return {
            "job_id": self.job_id,
            "total_chunks": len(self._all_chunks),
            "ready_chunks": len(self._chunks_ready),
            "playlist_url": self.hls.get_playlist_url(),
            "total_duration": self.hls.get_total_duration(),
            "progress": (
                len(self._chunks_ready) / len(self._all_chunks) * 100
                if self._all_chunks else 0
            ),
        }

    def is_first_ready(self) -> bool:
        """Birinchi chunk tayyorligini tekshirish."""
        return 0 in self._chunks_ready

    def get_first_playlist_url(self) -> Optional[str]:
        """Birinchi chunk tayyor bo'lganda playlist URL."""
        if self.is_first_ready():
            return self.hls.get_playlist_url()
        return None
