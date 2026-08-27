"""Azure TTS Provider — mavjud Azure SDK implementatsiyasini class ga o'ragan."""
import logging
import time
import xml.sax.saxutils as saxutils
import re

import azure.cognitiveservices.speech as speechsdk

from backend.services.tts.base import TTSProvider
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_AUDIO_FORMAT = speechsdk.SpeechSynthesisOutputFormat.Riff24Khz16BitMonoPcm


# Tabiiy urg'u beriladigan so'zlar — raqamlar va inkor iboralari (odatda
# gapning eng muhim, "eshitilishi shart" qismi). Apostrof variantlari
# (', ʻ, ') hisobga olingan, chunki tarjima/optimallash bosqichlaridan
# qaysi biri ishlatilgani oldindan noma'lum.
_EMPHASIS_NUMBER_RE = re.compile(r"\b\d+([.,]\d+)?\b")
_EMPHASIS_NEGATION_RE = re.compile(
    r"\b(yo['ʻ‘]?q|hech qachon|hech kim|hech narsa|hech qanday|aslo|mumkin emas)\b",
    re.IGNORECASE,
)


def _emphasize(escaped_text: str) -> str:
    """Raqamlar va inkor so'zlarini <emphasis> bilan o'raydi.

    Matn AVVAL XML-escape qilingan bo'lishi kerak — raqamlar/o'zbekcha
    so'zlarda &/</>/" belgilari bo'lmagani uchun bu tartib xavfsiz va
    qo'shilayotgan teglarni ikki marta escape qilib qo'ymaydi.
    """
    escaped_text = _EMPHASIS_NUMBER_RE.sub(
        lambda m: f'<emphasis level="moderate">{m.group(0)}</emphasis>', escaped_text
    )
    escaped_text = _EMPHASIS_NEGATION_RE.sub(
        lambda m: f'<emphasis level="strong">{m.group(0)}</emphasis>', escaped_text
    )
    return escaped_text


def _build_sentence_body(sentence: str) -> str:
    """Bitta gap ichida vergul bo'yicha tabiiy pauza (<break>) qo'shadi va
    raqam/inkor so'zlarga urg'u beradi — Azure'ning standart, bir xilda
    o'qiydigan ovozidan farqli, kishi nutqiga yaqinroq ohang uchun."""
    clauses = sentence.split(",")
    parts = [_emphasize(saxutils.escape(clause.strip())) for clause in clauses if clause.strip()]
    return '<break time="150ms"/>'.join(parts)


def _build_ssml(text: str, voice_name: str) -> str:
    is_female = "Madina" in voice_name
    # Avval -4%/-8%, keyin -2%/-3% edi — real tinglovda ovoz hali ham
    # original ovozdan "sekinroq" his qilindi (2026-08-12). To'liq neytral
    # (0%) qilindi — Azure'ning o'z tabiiy tezligi eng yaxshi boshlang'ich
    # nuqta, sun'iy o'zgartirishsiz.
    rate   = "0%"
    pitch  = "+2%" if is_female else "0%"

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    ssml_sentences = []
    for sent in sentences:
        body = _build_sentence_body(sent)
        if sent.rstrip().endswith("?"):
            ssml_sentences.append(f'<p><prosody pitch="+4%">{body}</prosody></p>')
        elif sent.rstrip().endswith("!"):
            ssml_sentences.append(f'<p><prosody pitch="+2%">{body}</prosody></p>')
        else:
            ssml_sentences.append(f'<p>{body}</p>')

    inner = "\n".join(ssml_sentences)
    return (
        '<speak version="1.0" '
        'xmlns="http://www.w3.org/2001/10/synthesis" '
        'xmlns:mstts="http://www.w3.org/2001/mstts" '
        f'xml:lang="uz-UZ">'
        f'<voice name="{voice_name}">'
        f'<prosody rate="{rate}" pitch="{pitch}" volume="0%">'
        f'{inner}'
        f'</prosody>'
        f'</voice>'
        f'</speak>'
    )


class AzureProvider(TTSProvider):
    """Azure Cognitive Services TTS — native Uzbek ovozlar."""

    DEFAULT_VOICE_MALE   = "uz-UZ-SardorNeural"
    DEFAULT_VOICE_FEMALE = "uz-UZ-MadinaNeural"

    @property
    def name(self) -> str:
        return "azure"

    @property
    def cost_per_1k(self) -> float:
        # Azure Neural TTS: ~$16 per 1M chars = $0.016 per 1K chars
        return 0.016

    def synthesize(
        self,
        text: str,
        output_path: str,
        voice_name: str | None = None,
        retries: int = 3,
    ) -> bool:
        key = settings.AZURE_SPEECH_KEY
        if not key or key in ("", "your-azure-key"):
            logger.warning("AZURE_SPEECH_KEY topilmadi — Azure o'tkazib yuborildi.")
            return False

        chosen_voice = voice_name or (
            self.DEFAULT_VOICE_FEMALE if self._is_female(voice_name) else self.DEFAULT_VOICE_MALE
        )

        try:
            speech_config = speechsdk.SpeechConfig(
                subscription=key,
                region=settings.AZURE_SPEECH_REGION or "eastus",
            )
            speech_config.speech_synthesis_voice_name = chosen_voice
            speech_config.set_speech_synthesis_output_format(_AUDIO_FORMAT)

            audio_config = speechsdk.audio.AudioOutputConfig(filename=output_path)
            synth = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, audio_config=audio_config
            )
            ssml = _build_ssml(text, chosen_voice)

            for attempt in range(retries):
                result = synth.speak_ssml_async(ssml).get()
                if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                    logger.info(f"Azure TTS: voice={chosen_voice}, chars={len(text)}")
                    return True

                # SDK bu holatda exception ko'tarmaydi — result.reason shunchaki
                # Canceled bo'ladi. cancellation_details loglanmasa, nima uchun
                # muvaffaqiyatsiz bo'lgani butunlay ko'rinmas bo'lib qoladi
                # (productionda 2026-08-12 shu sababli sokin Edge'ga tushib
                # ketgan — loglarda hech qanday xato ko'rinmagan edi).
                cd = result.cancellation_details
                logger.warning(
                    f"Azure TTS bekor qilindi: reason={cd.reason}, "
                    f"error_code={cd.error_code}, details={cd.error_details}"
                )
                # Autentifikatsiya/kvota xatosi qayta urinish bilan tuzatilmaydi —
                # har bir urinish bir xil natija beradi, shuning uchun darhol
                # to'xtatiladi (aks holda har segment uchun keraksiz 2x2s kutish).
                if cd.error_code == speechsdk.CancellationErrorCode.AuthenticationFailure:
                    break
                if attempt < retries - 1:
                    time.sleep(2)

        except Exception as exc:
            logger.warning(f"Azure TTS xato: {exc}")

        return False
