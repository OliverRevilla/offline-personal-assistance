import numpy as np
from faster_whisper import WhisperModel

from app.core.config import settings


def load_whisper_model() -> WhisperModel:
    return WhisperModel(
        settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe_pcm16(model: WhisperModel, pcm16: bytes) -> str:
    """Transcribe una utterance completa en PCM16 mono @16kHz (llamada bloqueante: correr
    con asyncio.to_thread, no directo en el loop de eventos)."""
    audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = model.transcribe(audio, language=settings.whisper_language, vad_filter=False)
    return "".join(segment.text for segment in segments).strip()
