import subprocess
import logging
from pathlib import Path

from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_MIX_SAMPLE_RATE = 44100


def _get_duration(file_path: str) -> float:
    """FFprobe orqali fayl davomiyligini olish (soniyada)."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _build_ducked_mix_filtergraph() -> str:
    """
    Original audio (musiqa/SFX/ambient) va o'zbekcha dublyajni professional
    kino-dublyaji uslubida aralashtiradi — original TO'LIQ o'chirilmaydi.

    [0:a] (original) va [1:a] (dublyaj) bir xil formatga keltiriladi, so'ng:
    - sidechaincompress: dublyaj trekining o'zi "trigger" bo'lib, original
      FAQAT dub gapirayotgan joyda pasayadi — moslashuvchan (baland original
      ko'proq, past original kamroq pasayadi), tekis fade bilan (attack/
      release), gap-gap qo'lda hisoblangan oraliqlar emas. IKKI marta ketma-
      ket qo'llaniladi (2026-08-14, real production videosini tinglab
      tasdiqlangan muammo: bitta bosqich original ovozni yetarlicha
      bosolmadi, dublyaj ovozi eshitilmay qolgan edi) — ffmpeg bitta
      sidechaincompress chaqiruvida ratio'ni 20dan oshirishga ruxsat
      bermaydi, shuning uchun ikkinchi bosqich effektiv bosishni
      chuqurlashtiradi.
    - dublyaj eshittirishdan oldin ovoz protsessing zanjiridan o'tadi (xirillash
      kesiladi, aniqlik uchun subtle EQ, dinamika siqiladi, "s" tovushlari
      yumshatiladi, keyin baland qilinadi — VOICE_GAIN_BOOST_DB — va nihoyat
      limiter cho'qqilarni xavfsiz ushlab qoladi) — shunda "TTS videoning
      ustiga yopishtirilgandek" emas, videoning o'z ovoz treki kabi eshitiladi
      va fondan sezilarli darajada ajralib turadi.
    - Yakuniy aralashma EBU R128 bo'yicha normallashtiriladi.
    """
    s = settings
    # ffmpeg'ning sidechaincompress filtri ratio uchun faqat [1, 20] oralig'ini
    # qabul qiladi — chegaradan tashqari qiymat butun ffmpeg jarayonini xato
    # bilan to'xtatadi (2026-08-12 productionda haqiqiy job orqali aniqlangan:
    # "Value 30.0 for parameter 'ratio' out of range [1 - 20]"). Config'dagi
    # qiymat noto'g'ri sozlansa ham job qulamasligi uchun shu yerda cheklanadi.
    ducking_ratio = max(1.0, min(20.0, s.DUCKING_RATIO))
    duck_stage = (
        f"sidechaincompress=threshold={s.DUCKING_THRESHOLD}:ratio={ducking_ratio}:"
        f"attack={s.DUCKING_ATTACK_MS}:release={s.DUCKING_RELEASE_MS}:makeup=1"
    )
    return (
        f"[0:a]aformat=sample_rates={_MIX_SAMPLE_RATE}:channel_layouts=stereo[orig];"
        f"[1:a]aformat=sample_rates={_MIX_SAMPLE_RATE}:channel_layouts=stereo,"
        f"asplit=3[dubsc1][dubsc2][dubdsp];"
        f"[orig][dubsc1]{duck_stage}[duck1];"
        f"[duck1][dubsc2]{duck_stage}[ducked];"
        f"[dubdsp]highpass=f={s.VOICE_HIGHPASS_HZ},"
        f"equalizer=f={s.VOICE_EQ_FREQ_HZ}:width_type=q:width=1:g={s.VOICE_EQ_GAIN_DB},"
        f"acompressor=threshold=0.1:ratio={s.VOICE_COMPRESSOR_RATIO}:attack=20:release=250:makeup=1,"
        f"deesser=i=0.2:m=0.5:f=0.5,"
        f"volume={s.VOICE_GAIN_BOOST_DB}dB,"
        f"alimiter=limit={s.VOICE_LIMITER_LIMIT}:attack=5:release=50[dubproc];"
        f"[ducked][dubproc]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[mixed];"
        f"[mixed]loudnorm=I={s.FINAL_LOUDNORM_I}:TP={s.FINAL_LOUDNORM_TP}:LRA={s.FINAL_LOUDNORM_LRA}[final]"
    )


def _build_dubbed_only_filtergraph() -> str:
    """Process the TTS track without feeding the original speech into the mix."""
    s = settings
    return (
        f"[1:a]aformat=sample_rates={_MIX_SAMPLE_RATE}:channel_layouts=stereo,"
        f"highpass=f={s.VOICE_HIGHPASS_HZ},"
        f"equalizer=f={s.VOICE_EQ_FREQ_HZ}:width_type=q:width=1:g={s.VOICE_EQ_GAIN_DB},"
        f"acompressor=threshold=0.1:ratio={s.VOICE_COMPRESSOR_RATIO}:attack=20:release=250:makeup=1,"
        f"deesser=i=0.2:m=0.5:f=0.5,"
        f"volume={s.VOICE_GAIN_BOOST_DB}dB,"
        f"alimiter=limit={s.VOICE_LIMITER_LIMIT}:attack=5:release=50,"
        f"loudnorm=I={s.FINAL_LOUDNORM_I}:TP={s.FINAL_LOUDNORM_TP}:LRA={s.FINAL_LOUDNORM_LRA}[final]"
    )


def _build_audio_filtergraph(audio_mix_mode: str | None = None) -> str:
    """Build a per-job audio graph, falling back to the global default."""
    mode = audio_mix_mode or settings.AUDIO_MIX_MODE
    if mode == "ducked_mix":
        return _build_ducked_mix_filtergraph()
    return _build_dubbed_only_filtergraph()


def merge_video_audio(
    video_path: str,
    dubbed_audio_path: str,
    output_path: str,
    audio_mix_mode: str | None = None,
) -> str:
    """
    Original video + O'zbekcha dublyaj → Tayyor video.

    ``AUDIO_MIX_MODE=dubbed_only`` (default) exports the processed Uzbek TTS
    track as the only output audio, so the original speech cannot mask it.
    ``AUDIO_MIX_MODE=ducked_mix`` keeps the legacy original+TTS ducking mix.

    Agar o'zbekcha dublyaj video dan uzunroq bo'lsa:
    → Video oxirgi kadri "freeze" qilinadi (qora ekran emas, tabiiy tugatish)

    Agar video uzunroq bo'lsa:
    → Original video TO'LIQ uzunligida saqlanadi (avval dub tugagach video
      kesib tashlanardi — bu endi original fon ovozini dub tugagandan keyin
      ham tinglash imkoniyatini yo'qqa chiqarardi).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    video_dur = _get_duration(video_path)
    audio_dur = _get_duration(dubbed_audio_path)

    audio_filter = _build_audio_filtergraph(audio_mix_mode)

    if audio_dur <= video_dur:
        filter_complex = audio_filter
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dubbed_audio_path,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[final]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        # Dublyaj uzunroq — video oxirgi kadrini "freeze" qilib audio ga
        # uzaytirish. Original audio o'z tabiiy uzunligida tugaydi (undan
        # keyin fon ovozi yo'q — amix duration=longest shu qismni jim
        # to'ldiradi), dub esa oxirigacha eshitiladi.
        extra = audio_dur - video_dur
        filter_complex = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={extra:.3f}[v];"
            f"{audio_filter}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", dubbed_audio_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[final]",
            "-c:v", "libx264", "-crf", "22", "-preset", "ultrafast", "-tune", "zerolatency", "-threads", "0",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

    # timeout=8000 (2s13m) edi — Celery hard time_limit=3600c (1 soat) dan
    # katta edi: uzun video merge'da task o'ldirilar, job 5x retry qilib
    # abadiy siklik qayta ishga tushardi. 2800 c (46m) — hard limit ichida
    # bajariladi (AUDIT_STABILITY.md §3 P1-3).
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=2800)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg xatoligi:\n{result.stderr[-1500:]}")

    return output_path


def merge_video_audio_chunk(
    video_chunk_path: str,
    dubbed_audio_path: str,
    output_path: str,
    audio_mix_mode: str | None = None,
    chunk_index: int = 0,
) -> str:
    """
    Bitta video chunk'ni dublyaj audiosi bilan birlashtirish.

    Chunked pipeline uchun ishlatiladi — har bir chunk mustaqil ravishda
    qayta ishlanadi, keyin barcha chunk'lar birlashtiriladi.

    Args:
        video_chunk_path: Video chunk fayl yo'li (3-5 daqiqa)
        dubbed_audio_path: Dublyaj audio fayl yo'li (shu chunk uchun)
        output_path: Chiqish fayl yo'li
        audio_mix_mode: Audio aralashtirish rejimi (default: config'dan)
        chunk_index: Chunk raqami (logging uchun)

    Returns:
        Chiqish fayl yo'li
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    video_dur = _get_duration(video_chunk_path)
    audio_dur = _get_duration(dubbed_audio_path)

    # Agar audio chunkdan uzunroq — video oxirgi kadrini freeze qilish
    if audio_dur > video_dur:
        extra = audio_dur - video_dur
        video_dur = audio_dur  # tpad bilan uzaytiramiz

    audio_filter = _build_audio_filtergraph(audio_mix_mode)

    if audio_dur <= _get_duration(video_chunk_path):
        # Oddiy holat: audio qisqa yoki teng
        filter_complex = audio_filter
        cmd = [
            "ffmpeg", "-y",
            "-i", video_chunk_path,
            "-i", dubbed_audio_path,
            "-filter_complex", filter_complex,
            "-map", "0:v:0",
            "-map", "[final]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
    else:
        # Audio uzunroq — video freeze
        extra = audio_dur - _get_duration(video_chunk_path)
        filter_complex = (
            f"[0:v]tpad=stop_mode=clone:stop_duration={extra:.3f}[v];"
            f"{audio_filter}"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", video_chunk_path,
            "-i", dubbed_audio_path,
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "[final]",
            "-c:v", "libx264", "-crf", "22", "-preset", "ultrafast",
            "-tune", "zerolatency", "-threads", "0",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)

    if result.returncode != 0:
        raise RuntimeError(f"Chunk {chunk_index} FFmpeg xatoligi:\n{result.stderr[-1000:]}")

    return output_path
