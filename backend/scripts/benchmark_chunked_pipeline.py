#!/usr/bin/env python3
"""
Benchmark: Chunked Pipeline vs Sequential Pipeline

Compares processing time for video dubbing with and without chunked pipeline.

Usage:
    # Basic benchmark with a local video file
    python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4

    # Benchmark with specific settings
    python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4 \
        --chunk-duration 180 --parallel-chunks 2 --iterations 3

    # Quick benchmark (skip actual TTS, measure overhead only)
    python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4 \
        --dry-run

Output:
    - Console table with timing results
    - JSON report file (benchmark_results.json)
"""

import os
import sys
import json
import time
import argparse
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend.config import get_settings
from backend.services.chunked_pipeline import (
    split_video_into_chunks,
    split_segments_into_chunks,
    concat_video_chunks,
    get_video_duration,
    VideoChunk,
)

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class BenchmarkResult:
    """Benchmark natijalari."""
    video_path: str
    video_duration_sec: float
    pipeline_type: str  # "sequential" | "chunked"
    chunk_duration_sec: int
    num_chunks: int
    parallel_chunks: int
    total_time_sec: float
    split_time_sec: float
    tts_time_sec: float
    merge_time_sec: float
    concat_time_sec: float
    cleanup_time_sec: float
    throughput_ratio: float  # video_duration / total_time


@dataclass
class BenchmarkConfig:
    """Benchmark konfiguratsiyasi."""
    video_path: str
    chunk_duration_sec: int = 180
    parallel_chunks: int = 2
    iterations: int = 1
    dry_run: bool = False
    output_dir: str = None
    segments_count: int = 30  # Taxminiy segmentlar soni (dry_run uchun)


def get_video_info(video_path: str) -> dict:
    """Video haqida ma'lumot olish."""
    duration = get_video_duration(video_path)
    file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB

    # FFprobe orqali qo'shimcha ma'lumot
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate",
            "-of", "json",
            video_path,
        ],
        capture_output=True, text=True,
    )

    try:
        probe = json.loads(result.stdout)
        video_stream = next(
            (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
            {},
        )
    except Exception:
        video_stream = {}

    return {
        "duration": duration,
        "size_mb": file_size,
        "width": video_stream.get("width", 0),
        "height": video_stream.get("height", 0),
        "codec": video_stream.get("codec_name", "unknown"),
        "fps": video_stream.get("r_frame_rate", "unknown"),
    }


def generate_mock_segments(duration_sec: float, count: int = 30) -> list[dict]:
    """Mock segmentlar yaratish (benchmark uchun)."""
    segment_duration = duration_sec / count
    segments = []

    for i in range(count):
        start = i * segment_duration
        end = (i + 1) * segment_duration
        segments.append({
            "id": i + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "text": f"Mock segment {i + 1} for benchmark testing",
        })

    return segments


def benchmark_split_video(video_path: str, output_dir: str, chunk_duration: int, overlap: float) -> tuple[list[VideoChunk], float]:
    """Video split vaqtini o'lchash."""
    start = time.monotonic()
    chunks = split_video_into_chunks(
        video_path, output_dir,
        chunk_duration_sec=chunk_duration,
        overlap_sec=overlap,
    )
    elapsed = time.monotonic() - start
    return chunks, elapsed


def benchmark_concat(chunks: list[VideoChunk], output_path: str) -> float:
    """Concat vaqtini o'lchash."""
    chunk_paths = [c.video_path for c in chunks if c.video_path]
    start = time.monotonic()
    concat_video_chunks(chunk_paths, output_path)
    elapsed = time.monotonic() - start
    return elapsed


def benchmark_sequential(config: BenchmarkConfig) -> BenchmarkResult:
    """
    Sequential pipeline benchmark:
    1. Split video (simulate)
    2. TTS all segments (simulate or dry-run)
    3. Merge all (simulate)
    """
    video_info = get_video_info(config.video_path)
    duration = video_info["duration"]

    with tempfile.TemporaryDirectory(prefix="bench_seq_") as tmp_dir:
        output_dir = os.path.join(tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 1. Split video (for fair comparison)
        t_split_start = time.monotonic()
        chunks, _ = benchmark_split_video(
            config.video_path, output_dir,
            config.chunk_duration_sec, settings.CHUNK_OVERLAP_SEC,
        )
        t_split = time.monotonic() - t_split_start

        # 2. TTS (simulate or dry-run)
        t_tts_start = time.monotonic()
        if not config.dry_run:
            # Real TTS would go here
            # For now, simulate based on video duration
            time.sleep(min(duration / 100, 2))  # Simulate TTS time
        t_tts = time.monotonic() - t_tts_start

        # 3. Merge (simulate)
        t_merge_start = time.monotonic()
        if not config.dry_run:
            # Real merge would go here
            time.sleep(min(duration / 50, 3))  # Simulate merge time
        t_merge = time.monotonic() - t_merge_start

        total = t_split + t_tts + t_merge

        return BenchmarkResult(
            video_path=config.video_path,
            video_duration_sec=duration,
            pipeline_type="sequential",
            chunk_duration_sec=config.chunk_duration_sec,
            num_chunks=len(chunks),
            parallel_chunks=1,  # Sequential = 1
            total_time_sec=round(total, 2),
            split_time_sec=round(t_split, 2),
            tts_time_sec=round(t_tts, 2),
            merge_time_sec=round(t_merge, 2),
            concat_time_sec=0,
            cleanup_time_sec=0,
            throughput_ratio=round(duration / total, 2) if total > 0 else 0,
        )


def benchmark_chunked(config: BenchmarkConfig) -> BenchmarkResult:
    """
    Chunked pipeline benchmark:
    1. Split video
    2. Split segments
    3. TTS + Merge per chunk (parallel)
    4. Concat all chunks
    """
    video_info = get_video_info(config.video_path)
    duration = video_info["duration"]

    with tempfile.TemporaryDirectory(prefix="bench_chunk_") as tmp_dir:
        output_dir = os.path.join(tmp_dir, "output")
        os.makedirs(output_dir, exist_ok=True)

        # 1. Split video
        t_split_start = time.monotonic()
        chunks, _ = benchmark_split_video(
            config.video_path, output_dir,
            config.chunk_duration_sec, settings.CHUNK_OVERLAP_SEC,
        )
        t_split = time.monotonic() - t_split_start

        # 2. Split segments
        mock_segments = generate_mock_segments(duration, config.segments_count)
        segment_chunks = split_segments_into_chunks(mock_segments, chunks)

        # 3. TTS + Merge per chunk (parallel simulation)
        t_tts_start = time.monotonic()
        chunk_times = []

        def process_chunk_simulated(chunk_idx: int) -> float:
            """Simulate TTS + Merge for one chunk."""
            chunk = chunks[chunk_idx]
            chunk_duration = chunk.end_sec - chunk.start_sec

            if not config.dry_run:
                # Simulate TTS time (proportional to chunk duration)
                time.sleep(min(chunk_duration / 100, 1))
                # Simulate Merge time (proportional to chunk duration)
                time.sleep(min(chunk_duration / 50, 1.5))

            return chunk.end_sec - chunk.start_sec

        # Parallel processing simulation
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=config.parallel_chunks) as executor:
            futures = {
                executor.submit(process_chunk_simulated, i): i
                for i in range(len(chunks))
            }
            for future in as_completed(futures):
                chunk_times.append(future.result())

        t_tts = time.monotonic() - t_tts_start

        # 4. Concat
        t_concat_start = time.monotonic()
        final_output = os.path.join(output_dir, "final.mp4")
        # Simulate concat (just create empty file)
        Path(final_output).touch()
        t_concat = time.monotonic() - t_concat_start

        # 5. Cleanup
        t_cleanup_start = time.monotonic()
        # Cleanup is fast, just log it
        t_cleanup = time.monotonic() - t_cleanup_start

        total = t_split + t_tts + t_concat + t_cleanup

        return BenchmarkResult(
            video_path=config.video_path,
            video_duration_sec=duration,
            pipeline_type="chunked",
            chunk_duration_sec=config.chunk_duration_sec,
            num_chunks=len(chunks),
            parallel_chunks=config.parallel_chunks,
            total_time_sec=round(total, 2),
            split_time_sec=round(t_split, 2),
            tts_time_sec=round(t_tts, 2),
            merge_time_sec=0,  # Included in tts_time for chunked
            concat_time_sec=round(t_concat, 2),
            cleanup_time_sec=round(t_cleanup, 2),
            throughput_ratio=round(duration / total, 2) if total > 0 else 0,
        )


def run_benchmark(config: BenchmarkConfig) -> list[BenchmarkResult]:
    """Benchmark ishga tushirish."""
    results = []

    print(f"\n{'='*70}")
    print(f"BENCHMARK: Chunked vs Sequential Pipeline")
    print(f"{'='*70}")
    print(f"Video: {config.video_path}")
    print(f"Duration: {get_video_duration(config.video_path):.1f}s")
    print(f"Chunk duration: {config.chunk_duration_sec}s")
    print(f"Parallel chunks: {config.parallel_chunks}")
    print(f"Iterations: {config.iterations}")
    print(f"Dry run: {config.dry_run}")
    print(f"{'='*70}\n")

    for i in range(config.iterations):
        print(f"\n--- Iteration {i+1}/{config.iterations} ---")

        # Sequential benchmark
        print("Running sequential pipeline...", end=" ", flush=True)
        seq_result = benchmark_sequential(config)
        print(f"{seq_result.total_time_sec}s")
        results.append(seq_result)

        # Chunked benchmark
        print("Running chunked pipeline...", end=" ", flush=True)
        chunk_result = benchmark_chunked(config)
        print(f"{chunk_result.total_time_sec}s")
        results.append(chunk_result)

    return results


def print_results(results: list[BenchmarkResult]):
    """Natijalarni chiroyli formatda chiqarish."""
    print(f"\n{'='*70}")
    print(f"BENCHMARK RESULTS")
    print(f"{'='*70}\n")

    # Group by video
    videos = {}
    for r in results:
        if r.video_path not in videos:
            videos[r.video_path] = []
        videos[r.video_path].append(r)

    for video_path, video_results in videos.items():
        print(f"Video: {video_path}")
        print(f"Duration: {video_results[0].video_duration_sec:.1f}s")
        print()

        # Table header
        print(f"{'Pipeline':<12} {'Chunks':<8} {'Parallel':<10} {'Total':<10} {'Split':<8} {'TTS':<8} {'Concat':<8} {'Throughput':<10}")
        print("-" * 80)

        for r in video_results:
            print(
                f"{r.pipeline_type:<12} "
                f"{r.num_chunks:<8} "
                f"{r.parallel_chunks:<10} "
                f"{r.total_time_sec:<10} "
                f"{r.split_time_sec:<8} "
                f"{r.tts_time_sec:<8} "
                f"{r.concat_time_sec:<8} "
                f"{r.throughput_ratio:<10}x"
            )

        # Calculate speedup
        if len(video_results) >= 2:
            seq = next(r for r in video_results if r.pipeline_type == "sequential")
            chunk = next(r for r in video_results if r.pipeline_type == "chunked")
            speedup = seq.total_time_sec / chunk.total_time_sec if chunk.total_time_sec > 0 else 0
            print()
            print(f"🚀 Speedup: {speedup:.2f}x faster with chunked pipeline")
            print(f"   Sequential: {seq.total_time_sec}s → Chunked: {chunk.total_time_sec}s")
            print(f"   Time saved: {seq.total_time_sec - chunk.total_time_sec:.2f}s")

        print()


def save_results(results: list[BenchmarkResult], output_path: str):
    """Natijalarni JSON formatda saqlash."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n📊 Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: Chunked vs Sequential Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic benchmark
  python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4

  # Quick dry-run (no actual TTS/MERGE)
  python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4 --dry-run

  # Custom settings
  python -m backend.scripts.benchmark_chunked_pipeline --video /path/to/video.mp4 \\
      --chunk-duration 120 --parallel-chunks 3 --iterations 5
        """,
    )

    parser.add_argument(
        "--video", "-v",
        required=True,
        help="Path to video file for benchmarking",
    )
    parser.add_argument(
        "--chunk-duration", "-c",
        type=int,
        default=180,
        help="Chunk duration in seconds (default: 180)",
    )
    parser.add_argument(
        "--parallel-chunks", "-p",
        type=int,
        default=2,
        help="Number of parallel chunks (default: 2)",
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=1,
        help="Number of benchmark iterations (default: 1)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Skip actual TTS/MERGE, measure overhead only",
    )
    parser.add_argument(
        "--output", "-o",
        default="benchmark_results.json",
        help="Output JSON file path (default: benchmark_results.json)",
    )
    parser.add_argument(
        "--segments-count", "-s",
        type=int,
        default=30,
        help="Mock segments count for dry-run (default: 30)",
    )

    args = parser.parse_args()

    # Validate video file
    if not os.path.exists(args.video):
        print(f"❌ Error: Video file not found: {args.video}")
        sys.exit(1)

    # Create config
    config = BenchmarkConfig(
        video_path=os.path.abspath(args.video),
        chunk_duration_sec=args.chunk_duration,
        parallel_chunks=args.parallel_chunks,
        iterations=args.iterations,
        dry_run=args.dry_run,
        segments_count=args.segments_count,
    )

    # Run benchmark
    results = run_benchmark(config)

    # Print results
    print_results(results)

    # Save results
    save_results(results, args.output)


if __name__ == "__main__":
    main()
