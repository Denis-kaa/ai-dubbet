#!/usr/bin/env python3
"""
Benchmark: CPU vs GPU Video Encoding

Compares encoding performance between CPU (libx264) and GPU (NVENC) encoding.

Usage:
    # Basic benchmark with a local video file
    python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4

    # Benchmark with custom settings
    python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4 \
        --duration 60 --iterations 3

    # Test specific NVENC presets
    python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4 \
        --nvenc-presets p1,p4,p7

Output:
    - Console table with timing results
    - JSON report file (benchmark_cpu_vs_gpu_results.json)
"""

import os
import sys
import json
import time
import argparse
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@dataclass
class EncodingResult:
    """Encoding natijalari."""
    codec: str
    preset: str
    tune: str
    input_file: str
    input_duration_sec: float
    input_size_mb: float
    output_file: str
    output_size_mb: float
    encoding_time_sec: float
    fps: float  # frames per second
    speedup_vs_cpu: float  # how much faster than CPU baseline


def check_nvenc_available() -> bool:
    """Check if NVENC is actually available (not just compiled in)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            test_output = f.name
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
                    "-c:v", "h264_nvenc", "-preset", "p1",
                    "-frames:v", "1",
                    test_output,
                ],
                capture_output=True, text=True, timeout=15,
            )
            return result.returncode == 0 and os.path.getsize(test_output) > 0
        finally:
            try:
                os.unlink(test_output)
            except OSError:
                pass
    except Exception:
        return False


def get_video_info(video_path: str) -> dict:
    """Get video file info."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration,size",
            "-show_entries", "stream=width,height,codec_name,r_frame_rate",
            "-of", "json",
            video_path,
        ],
        capture_output=True, text=True,
    )

    try:
        probe = json.loads(result.stdout)
        fmt = probe.get("format", {})
        video_stream = next(
            (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
            {},
        )
    except Exception:
        fmt, video_stream = {}, {}

    return {
        "duration": float(fmt.get("duration", 0)),
        "size_mb": int(fmt.get("size", 0)) / (1024 * 1024),
        "width": video_stream.get("width", 0),
        "height": video_stream.get("height", 0),
        "codec": video_stream.get("codec_name", "unknown"),
        "fps": video_stream.get("r_frame_rate", "unknown"),
    }


def create_test_video(duration_sec: int = 60, output_path: str = None) -> str:
    """Create a test video for benchmarking."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".mp4")

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration_sec}:size=1920x1080:rate=30",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_sec}",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=300)
    return output_path


def benchmark_encoding(
    input_path: str,
    codec: str,
    preset: str,
    tune: str,
    output_path: str,
    extra_args: list = None,
) -> EncodingResult:
    """Run encoding benchmark for a specific codec/preset."""
    input_info = get_video_info(input_path)
    input_size_mb = input_info["size_mb"]
    input_duration = input_info["duration"]

    # Build FFmpeg command
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-c:v", codec,
        "-preset", preset,
        "-tune", tune,
    ]

    # Add extra args (for NVENC)
    if extra_args:
        cmd.extend(extra_args)

    # Add audio codec
    cmd.extend([
        "-c:a", "aac", "-b:a", "192k",
        output_path,
    ])

    # Run encoding
    start_time = time.monotonic()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    encoding_time = time.monotonic() - start_time

    if result.returncode != 0:
        raise RuntimeError(f"Encoding failed: {result.stderr[-500:]}")

    # Get output info
    output_info = get_video_info(output_path)
    output_size_mb = output_info["size_mb"]

    # Calculate FPS
    fps = input_duration / encoding_time if encoding_time > 0 else 0

    return EncodingResult(
        codec=codec,
        preset=preset,
        tune=tune,
        input_file=input_path,
        input_duration_sec=input_duration,
        input_size_mb=input_size_mb,
        output_file=output_path,
        output_size_mb=output_size_mb,
        encoding_time_sec=round(encoding_time, 2),
        fps=round(fps, 2),
        speedup_vs_cpu=0,  # Will be calculated later
    )


def run_benchmark(
    video_path: str,
    duration: int = 60,
    iterations: int = 1,
    nvenc_presets: list[str] = None,
) -> list[EncodingResult]:
    """Run full benchmark."""
    results = []

    if nvenc_presets is None:
        nvenc_presets = ["p1"]  # Default: fastest NVENC preset

    # Check NVENC availability
    has_nvenc = check_nvenc_available()
    print(f"\n{'='*70}")
    print(f"BENCHMARK: CPU vs GPU Video Encoding")
    print(f"{'='*70}")
    print(f"Video: {video_path}")
    print(f"Duration: {duration}s")
    print(f"Iterations: {iterations}")
    print(f"NVENC available: {'✅ Yes' if has_nvenc else '❌ No (CPU only)'}")
    print(f"{'='*70}\n")

    # Use provided video or create test video
    if video_path and os.path.exists(video_path):
        input_video = video_path
        cleanup_input = False
    else:
        print("Creating test video...")
        input_video = create_test_video(duration)
        cleanup_input = True

    try:
        for i in range(iterations):
            print(f"\n--- Iteration {i+1}/{iterations} ---")

            # CPU encoding (libx264)
            print(f"CPU (libx264 ultrafast)...", end=" ", flush=True)
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                    cpu_output = f.name
                cpu_result = benchmark_encoding(
                    input_video, "libx264", "ultrafast", "zerolatency", cpu_output,
                    extra_args=["-threads", "0"],
                )
                print(f"{cpu_result.encoding_time_sec}s")
                results.append(cpu_result)
            except Exception as e:
                print(f"FAILED: {e}")

            # GPU encoding (NVENC)
            if has_nvenc:
                for preset in nvenc_presets:
                    print(f"GPU (NVENC {preset} ull)...", end=" ", flush=True)
                    try:
                        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
                            gpu_output = f.name
                        gpu_result = benchmark_encoding(
                            input_video, "h264_nvenc", preset, "ull", gpu_output,
                            extra_args=["-rc", "vbr", "-cq", "23", "-b:v", "0"],
                        )
                        print(f"{gpu_result.encoding_time_sec}s")
                        results.append(gpu_result)
                    except Exception as e:
                        print(f"FAILED: {e}")
            else:
                print("GPU (NVENC): Skipped (not available)")

    finally:
        # Cleanup
        if cleanup_input and os.path.exists(input_video):
            os.unlink(input_video)

    # Calculate speedups
    if results:
        cpu_baseline = next((r for r in results if r.codec == "libx264"), None)
        if cpu_baseline:
            for r in results:
                if r.codec != "libx264":
                    r.speedup_vs_cpu = round(
                        cpu_baseline.encoding_time_sec / r.encoding_time_sec, 2
                    ) if r.encoding_time_sec > 0 else 0

    return results


def print_results(results: list[EncodingResult]):
    """Print results in a nice table."""
    if not results:
        print("\nNo results to display.")
        return

    print(f"\n{'='*90}")
    print(f"ENCODING BENCHMARK RESULTS")
    print(f"{'='*90}\n")

    # Table header
    print(f"{'Codec':<15} {'Preset':<10} {'Tune':<8} {'Time (s)':<10} {'Size (MB)':<12} {'Speed':<10} {'vs CPU':<10}")
    print("-" * 90)

    for r in results:
        speedup_str = f"{r.speedup_vs_cpu}x" if r.speedup_vs_cpu > 0 else "baseline"
        print(
            f"{r.codec:<15} "
            f"{r.preset:<10} "
            f"{r.tune:<8} "
            f"{r.encoding_time_sec:<10} "
            f"{r.output_size_mb:<12} "
            f"{r.fps:<10} "
            f"{speedup_str:<10}"
        )

    # Summary
    cpu_results = [r for r in results if r.codec == "libx264"]
    gpu_results = [r for r in results if r.codec == "h264_nvenc"]

    if cpu_results and gpu_results:
        avg_cpu = sum(r.encoding_time_sec for r in cpu_results) / len(cpu_results)
        avg_gpu = sum(r.encoding_time_sec for r in gpu_results) / len(gpu_results)
        speedup = avg_cpu / avg_gpu if avg_gpu > 0 else 0

        print()
        print(f"📊 Summary:")
        print(f"   CPU average: {avg_cpu:.2f}s")
        print(f"   GPU average: {avg_gpu:.2f}s")
        print(f"   Speedup: {speedup:.2f}x faster with GPU")
        print(f"   Time saved: {avg_cpu - avg_gpu:.2f}s per encoding")
    elif cpu_results:
        print()
        print(f"📊 Only CPU encoding available (no GPU)")
    else:
        print()
        print(f"📊 No results")


def save_results(results: list[EncodingResult], output_path: str):
    """Save results to JSON."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "results": [asdict(r) for r in results],
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\n📊 Results saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark: CPU vs GPU Video Encoding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic benchmark
  python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4

  # Create test video and benchmark
  python -m backend.scripts.benchmark_cpu_vs_gpu --duration 60

  # Benchmark multiple NVENC presets
  python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4 \\
      --nvenc-presets p1,p4,p7

  # Quick benchmark with fewer iterations
  python -m backend.scripts.benchmark_cpu_vs_gpu --video /path/to/video.mp4 \\
      --iterations 1
        """,
    )

    parser.add_argument(
        "--video", "-v",
        help="Path to video file (if not provided, creates test video)",
    )
    parser.add_argument(
        "--duration", "-d",
        type=int,
        default=60,
        help="Test video duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--iterations", "-i",
        type=int,
        default=1,
        help="Number of benchmark iterations (default: 1)",
    )
    parser.add_argument(
        "--nvenc-presets", "-n",
        type=str,
        default="p1",
        help="Comma-separated NVENC presets to test (default: p1)",
    )
    parser.add_argument(
        "--output", "-o",
        default="benchmark_cpu_vs_gpu_results.json",
        help="Output JSON file path (default: benchmark_cpu_vs_gpu_results.json)",
    )

    args = parser.parse_args()

    # Parse NVENC presets
    nvenc_presets = [p.strip() for p in args.nvenc_presets.split(",")]

    # Validate video file if provided
    if args.video and not os.path.exists(args.video):
        print(f"❌ Error: Video file not found: {args.video}")
        sys.exit(1)

    # Run benchmark
    results = run_benchmark(
        video_path=args.video,
        duration=args.duration,
        iterations=args.iterations,
        nvenc_presets=nvenc_presets,
    )

    # Print results
    print_results(results)

    # Save results
    save_results(results, args.output)


if __name__ == "__main__":
    main()
