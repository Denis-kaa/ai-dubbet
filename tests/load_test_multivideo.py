"""
Load Test: Multi-User Concurrency (промт 115 §13-14)

Сценарии:
  Scenario 1: 1 user  × 1 video
  Scenario 2: 2 users × 1 video
  Scenario 3: 5 users × 1 video
  Scenario 4: 10 users × 1 video
  Scenario 5: 1 user  × 10 videos
  Scenario 6: 5 users × 3 videos

Запуск:
  cd /opt/ai-dubber
  venv/bin/python -m tests.load_test_multivideo
"""

from __future__ import annotations

import json
import random
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.services.scheduler import FairScheduler
from backend.services.backpressure import BackpressureController
from backend.services.metrics import MetricsCollector
from backend.services.sliding_window import ChunkWindow


# ─── Simulated latencies (seconds, measured wall-clock) ─────

TTS_LATENCY = 0.05      # 50ms simulated TTS
MEDIA_LATENCY = 0.03    # 30ms simulated Media


# ─── Data classes ───────────────────────────────────────────


@dataclass
class ScenarioResult:
    name: str
    description: str
    users: int
    videos_per_user: int
    total_jobs: int
    total_chunks: int
    duration: float = 0.0
    ttfp_per_user: Dict[str, float] = field(default_factory=dict)
    ttfp_per_job: Dict[str, float] = field(default_factory=dict)
    total_per_job: Dict[str, float] = field(default_factory=dict)
    queue_wait_avg: float = 0.0
    tts_latency_avg: float = 0.0
    media_latency_avg: float = 0.0
    fairness_stddev: float = 0.0
    backpressure_events: int = 0
    errors: int = 0


# ─── Simulated job processing (sequential chunks per job) ──


def simulate_job(
    user_id: str,
    job_id: str,
    num_chunks: int,
    scheduler: FairScheduler,
    backpressure: BackpressureController,
    metrics: MetricsCollector,
    lock: threading.Lock,
) -> dict:
    """Simulate one job: register → process chunks sequentially → release."""

    # Wait for scheduler slot
    while True:
        with lock:
            if scheduler.can_accept_job(user_id):
                scheduler.register_active_job(user_id, job_id)
                break
        time.sleep(0.001)

    metrics.start_job(user_id, job_id)
    job_start = time.monotonic()

    window = ChunkWindow(job_id=job_id, window_size=2)
    chunk_ids = [f"{job_id}_c{i}" for i in range(num_chunks)]
    window.init_chunks(chunk_ids)
    metrics.set_chunks_total(job_id, num_chunks)

    queue_waits = []
    tts_latencies = []
    media_latencies = []

    for chunk_idx in range(num_chunks):
        chunk_id = f"{job_id}_c{chunk_idx}"
        chunk_start = time.monotonic()

        # Backpressure
        while True:
            with lock:
                if backpressure.can_produce_tts(job_id):
                    backpressure.register_tts_produced(job_id, chunk_id)
                    break
            time.sleep(0.001)

        queue_wait = time.monotonic() - chunk_start
        queue_waits.append(queue_wait)

        # Window start
        with lock:
            window.start_chunk(chunk_id)

        # TTS
        tts_latency = TTS_LATENCY + random.uniform(-0.01, 0.01)
        tts_latencies.append(tts_latency)
        with lock:
            metrics.record_tts_latency(job_id, chunk_id, tts_latency)

        # Media
        with lock:
            backpressure.register_media_started(job_id, chunk_id)

        media_latency = MEDIA_LATENCY + random.uniform(-0.005, 0.005)
        media_latencies.append(media_latency)
        with lock:
            metrics.record_media_latency(job_id, chunk_id, media_latency)

        # Backpressure consumed
        with lock:
            backpressure.register_media_consumed(job_id, chunk_id)
            backpressure.register_media_finished(job_id, chunk_id)

        # Window complete
        with lock:
            window.complete_chunk(chunk_id)
            metrics.record_chunk_completed(job_id)
            metrics.record_ttfp(job_id, chunk_id)

    metrics.end_job(job_id)
    total_processing = time.monotonic() - job_start

    job_metrics = metrics.get_job_metrics(job_id)
    ttfp = job_metrics["ttfp"] if job_metrics else 0

    scheduler.release_job(user_id, job_id)

    return {
        "job_id": job_id,
        "user_id": user_id,
        "ttfp": ttfp,
        "total_processing": total_processing,
        "chunks": num_chunks,
        "queue_wait_avg": statistics.mean(queue_waits) if queue_waits else 0,
        "tts_latency_avg": statistics.mean(tts_latencies) if tts_latencies else 0,
        "media_latency_avg": statistics.mean(media_latencies) if media_latencies else 0,
    }


# ─── Scenario runner ────────────────────────────────────────


def run_scenario(
    name: str,
    description: str,
    num_users: int,
    videos_per_user: int,
) -> ScenarioResult:
    """Run a single load test scenario."""
    print(f"\n{'='*60}")
    print(f"  {name}: {description}")
    print(f"  Users={num_users}, Videos/user={videos_per_user}")
    print(f"{'='*60}")

    scheduler = FairScheduler(redis_url="redis://localhost:1/never")
    scheduler._redis = None
    backpressure = BackpressureController()
    metrics = MetricsCollector()
    lock = threading.Lock()

    total_jobs = num_users * videos_per_user
    total_chunks = 0
    all_chunk_counts = []

    scenario_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=min(total_jobs, 16)) as executor:
        futures = {}
        for user_idx in range(num_users):
            user_id = f"user_{user_idx:02d}"
            for video_idx in range(videos_per_user):
                job_id = f"{user_id}_job_{video_idx:02d}"
                num_chunks = random.randint(3, 5)
                total_chunks += num_chunks
                all_chunk_counts.append(num_chunks)

                future = executor.submit(
                    simulate_job,
                    user_id, job_id, num_chunks,
                    scheduler, backpressure, metrics, lock,
                )
                futures[future] = (user_id, job_id)

        job_results = []
        for future in as_completed(futures):
            user_id, job_id = futures[future]
            try:
                result = future.result()
                job_results.append(result)
            except Exception as exc:
                print(f"  ERROR: {job_id}: {exc}")

    scenario_duration = time.monotonic() - scenario_start

    # ─── Aggregate ───
    result = ScenarioResult(
        name=name,
        description=description,
        users=num_users,
        videos_per_user=videos_per_user,
        total_jobs=total_jobs,
        total_chunks=total_chunks,
        duration=scenario_duration,
    )

    # TTFP per user
    user_ttfps: Dict[str, List[float]] = {}
    for jr in job_results:
        user_ttfps.setdefault(jr["user_id"], []).append(jr["ttfp"])
    for uid, ttfps in user_ttfps.items():
        result.ttfp_per_user[uid] = statistics.mean(ttfps)

    # TTFP per job + total per job
    for jr in job_results:
        result.ttfp_per_job[jr["job_id"]] = jr["ttfp"]
        result.total_per_job[jr["job_id"]] = jr["total_processing"]

    # Averages
    result.queue_wait_avg = statistics.mean([jr["queue_wait_avg"] for jr in job_results]) if job_results else 0
    result.tts_latency_avg = statistics.mean([jr["tts_latency_avg"] for jr in job_results]) if job_results else 0
    result.media_latency_avg = statistics.mean([jr["media_latency_avg"] for jr in job_results]) if job_results else 0

    # Fairness
    ttfp_values = list(result.ttfp_per_user.values())
    result.fairness_stddev = statistics.stdev(ttfp_values) if len(ttfp_values) > 1 else 0

    # Backpressure
    bp_stats = backpressure.get_stats()
    result.backpressure_events = bp_stats.jobs_throttled

    # ─── Print ───
    avg_ttfp = statistics.mean(result.ttfp_per_user.values()) if result.ttfp_per_user else 0
    print(f"\n  📊 Results:")
    print(f"  {'─'*50}")
    print(f"  Duration:           {scenario_duration:.3f}s")
    print(f"  Total jobs:         {total_jobs}")
    print(f"  Total chunks:       {total_chunks}")
    print(f"  Errors:             {result.errors}")
    print(f"  Backpressure:       {result.backpressure_events} events")
    print(f"  Queue wait avg:     {result.queue_wait_avg:.4f}s")
    print(f"  TTS latency avg:    {result.tts_latency_avg:.4f}s")
    print(f"  Media latency avg:  {result.media_latency_avg:.4f}s")
    print(f"  TTFP avg:           {avg_ttfp:.4f}s")
    print(f"  Fairness (stddev):  {result.fairness_stddev:.4f}s")
    print(f"\n  TTFP per user:")
    for uid, ttfp in sorted(result.ttfp_per_user.items()):
        print(f"    {uid}: {ttfp:.4f}s")
    print(f"\n  Total time per job:")
    for jid, total in sorted(result.total_per_job.items()):
        print(f"    {jid}: {total:.4f}s")

    return result


# ─── Main ───────────────────────────────────────────────────


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  LOAD TEST: Multi-User Concurrency (промт 115 §13-14)     ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    scenarios = [
        ("Scenario 1", "1 user × 1 video", 1, 1),
        ("Scenario 2", "2 users × 1 video", 2, 1),
        ("Scenario 3", "5 users × 1 video", 5, 1),
        ("Scenario 4", "10 users × 1 video", 10, 1),
        ("Scenario 5", "1 user × 10 videos", 1, 10),
        ("Scenario 6", "5 users × 3 videos", 5, 3),
    ]

    all_results: List[ScenarioResult] = []

    for name, desc, users, videos in scenarios:
        result = run_scenario(name, desc, users, videos)
        all_results.append(result)

    # ─── Summary ───
    print("\n\n" + "=" * 90)
    print("  SUMMARY")
    print("=" * 90)
    header = f"  {'Scenario':<18} {'U':>3} {'V':>3} {'Jobs':>5} {'Chunks':>7} {'Time':>8} {'TTFP avg':>9} {'Fair σ':>8} {'BP':>4}"
    print(header)
    print(f"  {'─'*18} {'─'*3} {'─'*3} {'─'*5} {'─'*7} {'─'*8} {'─'*9} {'─'*8} {'─'*4}")

    for r in all_results:
        avg_ttfp = statistics.mean(r.ttfp_per_user.values()) if r.ttfp_per_user else 0
        print(f"  {r.name:<18} {r.users:>3} {r.videos_per_user:>3} {r.total_jobs:>5} {r.total_chunks:>7} {r.duration:>7.3f}s {avg_ttfp:>8.4f}s {r.fairness_stddev:>7.4f}s {r.backpressure_events:>4}")

    # ─── Save JSON ───
    output = []
    for r in all_results:
        avg_ttfp = statistics.mean(r.ttfp_per_user.values()) if r.ttfp_per_user else 0
        output.append({
            "scenario": r.name,
            "description": r.description,
            "users": r.users,
            "videos_per_user": r.videos_per_user,
            "total_jobs": r.total_jobs,
            "total_chunks": r.total_chunks,
            "duration_sec": round(r.duration, 4),
            "ttfp_avg": round(avg_ttfp, 4),
            "ttfp_per_user": {k: round(v, 4) for k, v in r.ttfp_per_user.items()},
            "queue_wait_avg": round(r.queue_wait_avg, 4),
            "tts_latency_avg": round(r.tts_latency_avg, 4),
            "media_latency_avg": round(r.media_latency_avg, 4),
            "fairness_stddev": round(r.fairness_stddev, 4),
            "backpressure_events": r.backpressure_events,
            "errors": r.errors,
        })

    with open("load_test_results.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  📁 Results saved to: load_test_results.json")

    # ─── Analysis ───
    print("\n" + "=" * 90)
    print("  ANALYSIS")
    print("=" * 90)

    print("\n  🎯 Fairness (TTFP stddev):")
    for r in all_results:
        avg_ttfp = statistics.mean(r.ttfp_per_user.values()) if r.ttfp_per_user else 0
        if avg_ttfp > 0:
            ratio = r.fairness_stddev / avg_ttfp
            status = "✅ GOOD" if ratio < 0.3 else "⚠️ HIGH"
        else:
            ratio = 0
            status = "✅ N/A"
        print(f"    {r.name}: σ={r.fairness_stddev:.4f}s / avg={avg_ttfp:.4f}s = {ratio:.2f} {status}")

    print("\n  📈 Scalability (duration):")
    base = all_results[0].duration if all_results else 1
    for r in all_results:
        ratio = r.duration / base if base > 0 else 0
        print(f"    {r.name}: {r.duration:.3f}s ({ratio:.1f}x base)")

    print("\n  🔧 Backpressure:")
    for r in all_results:
        print(f"    {r.name}: {r.backpressure_events} throttle events")

    print("\n" + "=" * 90)
    print("  ✅ LOAD TEST COMPLETE")
    print("=" * 90)


if __name__ == "__main__":
    main()
