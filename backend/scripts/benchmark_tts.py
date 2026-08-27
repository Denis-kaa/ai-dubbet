"""TTS Provider Benchmark — barcha provayderlarni taqqoslaydi.

Ishlatish:
    PYTHONPATH=. python -m backend.scripts.benchmark_tts
    PYTHONPATH=. python -m backend.scripts.benchmark_tts --providers uzbekvoice,azure,edge
    PYTHONPATH=. python -m backend.scripts.benchmark_tts --text "O'z matnni kiriting"
    PYTHONPATH=. python -m backend.scripts.benchmark_tts --runs 3        # failure rate uchun
    PYTHONPATH=. python -m backend.scripts.benchmark_tts --qa            # STT round-trip QA bilan
"""
import argparse
import json
import os
import sys
import time
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Spec §7 sinov matni: sana(ordinal)/valyuta/qisqartma/yil-oralig'ini bitta
# matnda birlashtiradi — normalizer + provider'ni birgalikda sinaydi (haqiqiy
# oxir-oqibat sifat savoli shu, alohida normalizer unit-testi emas).
TEST_TEXT_UZ = (
    "1947-yil 12-mart kuni O'zbekiston tarixida muhim voqealardan biri yuz berdi. "
    "125 000 so'm qiymatidagi mahsulot uchun API orqali ma'lumot yuboramiz. "
    "Sun'iy intellekt, GPT, API va YouTube texnologiyalari haqida gaplashamiz. "
    "O'zbekistonning iqtisodiy rivojlanishi 2020-2025-yillarda sezilarli darajada o'zgardi."
)

# uzbekvoice UZS'da narxlanadi, qolganlari USD'da — tts_cost.py bilan bir xil ro'yxat.
_UZS_PROVIDERS = {"uzbekvoice"}


@dataclass
class BenchmarkResult:
    provider: str
    success: bool
    latency_ms: float
    audio_duration_ms: float
    audio_size_bytes: int
    chars: int
    cost: float
    currency: str
    cost_per_1k_chars: float
    chars_per_second: float
    error: str = ""
    qa_score: float | None = None
    qa_flags: list[str] = field(default_factory=list)


@dataclass
class ProviderSummary:
    provider: str
    currency: str
    runs: int
    successes: int
    failure_rate: float
    avg_latency_ms: float
    avg_cost: float
    avg_qa_score: float | None
    results: list[BenchmarkResult]


def _get_audio_duration_ms(wav_path: str) -> float:
    """ffprobe bilan audio davomiyligini aniqlash."""
    try:
        import subprocess, json
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json", wav_path,
            ],
            capture_output=True, text=True, check=True,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"]) * 1000
    except Exception:
        return 0.0


def benchmark_provider(provider_name: str, text: str, run_qa: bool = False) -> BenchmarkResult:
    from backend.services.tts.factory import get_provider

    currency = "UZS" if provider_name in _UZS_PROVIDERS else "USD"

    try:
        provider = get_provider(provider_name)
    except Exception as e:
        return BenchmarkResult(
            provider=provider_name, success=False,
            latency_ms=0, audio_duration_ms=0,
            audio_size_bytes=0, chars=len(text),
            cost=0, currency=currency, cost_per_1k_chars=0, chars_per_second=0,
            error=f"Provider yuklashda xatolik: {e}",
        )

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        output_path = tmp.name

    try:
        t0 = time.perf_counter()
        try:
            success = provider.synthesize(text, output_path, voice_name="uz-UZ-SardorNeural")
        except Exception as synth_exc:
            # PermanentTTSError va boshqa kutilmagan xatolar — benchmark
            # to'xtamasin, xatolik matn sifatida yozib qolinsin.
            latency_ms = (time.perf_counter() - t0) * 1000
            return BenchmarkResult(
                provider=provider_name, success=False,
                latency_ms=round(latency_ms, 1), audio_duration_ms=0,
                audio_size_bytes=0, chars=len(text),
                cost=0, currency=currency, cost_per_1k_chars=provider.cost_per_1k, chars_per_second=0,
                error=str(synth_exc),
            )
        latency_ms = (time.perf_counter() - t0) * 1000

        if not success or not os.path.exists(output_path):
            return BenchmarkResult(
                provider=provider_name, success=False,
                latency_ms=latency_ms, audio_duration_ms=0,
                audio_size_bytes=0, chars=len(text),
                cost=0, currency=currency, cost_per_1k_chars=provider.cost_per_1k, chars_per_second=0,
                error="synthesize() False qaytardi yoki fayl yaratilmadi",
            )

        audio_size = os.path.getsize(output_path)
        audio_duration_ms = _get_audio_duration_ms(output_path)
        cost = provider.estimate_cost(len(text))
        cps = (len(text) / latency_ms * 1000) if latency_ms > 0 else 0

        qa_score, qa_flags = None, []
        if run_qa:
            try:
                from backend.services.audio_qa import check_audio_quality
                qa = check_audio_quality(output_path, text)
                qa_score, qa_flags = qa["score"], qa["flags"]
            except Exception as qa_exc:
                qa_flags = [f"qa_error: {qa_exc}"]

        return BenchmarkResult(
            provider=provider_name,
            success=True,
            latency_ms=round(latency_ms, 1),
            audio_duration_ms=round(audio_duration_ms, 1),
            audio_size_bytes=audio_size,
            chars=len(text),
            cost=round(cost, 4),
            currency=currency,
            cost_per_1k_chars=provider.cost_per_1k,
            chars_per_second=round(cps, 1),
            qa_score=qa_score,
            qa_flags=qa_flags,
        )
    finally:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass


def summarize(provider_name: str, results: list[BenchmarkResult]) -> ProviderSummary:
    successes = [r for r in results if r.success]
    qa_scores = [r.qa_score for r in successes if r.qa_score is not None]
    return ProviderSummary(
        provider=provider_name,
        currency=results[0].currency if results else "USD",
        runs=len(results),
        successes=len(successes),
        failure_rate=round(1 - len(successes) / len(results), 3) if results else 1.0,
        avg_latency_ms=round(sum(r.latency_ms for r in successes) / len(successes), 1) if successes else 0.0,
        avg_cost=round(sum(r.cost for r in successes) / len(successes), 4) if successes else 0.0,
        avg_qa_score=round(sum(qa_scores) / len(qa_scores), 3) if qa_scores else None,
        results=results,
    )


def print_report(summaries: list[ProviderSummary]) -> None:
    print("\n" + "=" * 90)
    print("TTS BENCHMARK NATIJASI")
    print("=" * 90)
    header = f"{'Provider':<14} {'Muvaff.':<10} {'O`rt. latency':>14} {'O`rt. narx':>16} {'QA ball':>10}"
    print(header)
    print("-" * 90)

    for s in summaries:
        success_str = f"{s.successes}/{s.runs}"
        lat = f"{s.avg_latency_ms:.0f}ms" if s.successes else "-"
        cost = f"{s.avg_cost:.4f} {s.currency}" if s.successes else "-"
        qa = f"{s.avg_qa_score:.2f}" if s.avg_qa_score is not None else "-"
        print(f"{s.provider:<14} {success_str:<10} {lat:>14} {cost:>16} {qa:>10}")
        if s.failure_rate > 0:
            print(f"  ⚠ failure rate: {s.failure_rate*100:.0f}%")
        for r in s.results:
            if not r.success:
                print(f"    ✗ {r.error[:80]}")
            elif r.qa_flags:
                print(f"    ⚠ QA flags: {', '.join(r.qa_flags)}")

    print("-" * 90)

    successful_summaries = [s for s in summaries if s.successes > 0]
    if not successful_summaries:
        print("Hech bir provider muvaffaqiyatli bo'lmadi!")
        return

    fastest = min(successful_summaries, key=lambda s: s.avg_latency_ms)
    print(f"\n🏆 Eng tez:    {fastest.provider} ({fastest.avg_latency_ms:.0f}ms)")

    # Narxni faqat bir xil valyutadagilar orasida solishtiramiz.
    for currency in {"USD", "UZS"}:
        same_currency = [s for s in successful_summaries if s.currency == currency]
        if len(same_currency) >= 1:
            cheapest = min(same_currency, key=lambda s: s.avg_cost)
            print(f"💰 Eng arzon ({currency}): {cheapest.provider} ({cheapest.avg_cost:.4f} {currency}/{len(TEST_TEXT_UZ)} belgi)")

    print("=" * 90 + "\n")


def main():
    parser = argparse.ArgumentParser(description="TTS Benchmark")
    parser.add_argument(
        "--providers", default="elevenlabs,azure,edge",
        help="Vergul bilan ajratilgan provider nomlari (default: elevenlabs,azure,edge)"
    )
    parser.add_argument("--text", default=TEST_TEXT_UZ, help="Sinov matni")
    parser.add_argument("--runs", type=int, default=1, help="Har bir provider uchun necha marta ishga tushirish (failure rate uchun)")
    parser.add_argument("--qa", action="store_true", help="Har bir muvaffaqiyatli sintezdan keyin STT round-trip QA ishga tushirish")
    parser.add_argument("--json", action="store_true", help="JSON formatda chiqarish")
    args = parser.parse_args()

    providers = [p.strip() for p in args.providers.split(",")]
    text = args.text

    print(f"\nSinov matni ({len(text)} belgi):\n  \"{text[:100]}...\"")
    print(f"\nTestlanayotgan provayderlar: {providers} | runs={args.runs} | qa={args.qa}")
    print("Iltimos kuting...\n")

    summaries = []
    for p in providers:
        print(f"  [{p}] {args.runs} marta sinov boshlandi...")
        results = []
        for i in range(args.runs):
            r = benchmark_provider(p, text, run_qa=args.qa)
            results.append(r)
            status = "✅" if r.success else "❌"
            print(f"    urinish {i+1}/{args.runs}: {status} {r.latency_ms:.0f}ms" + (f" | QA={r.qa_score}" if r.qa_score is not None else ""))
        summaries.append(summarize(p, results))

    if args.json:
        print(json.dumps([
            {**asdict(s), "results": [asdict(r) for r in s.results]}
            for s in summaries
        ], indent=2, ensure_ascii=False))
    else:
        print_report(summaries)

    return 0 if any(s.successes > 0 for s in summaries) else 1


if __name__ == "__main__":
    sys.exit(main())
