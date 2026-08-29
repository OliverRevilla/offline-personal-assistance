import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ws import router as ws_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.metrics import metrics
from app.rag.store import get_client
from app.stt.whisper_client import load_whisper_model
from app.tts.piper_client import load_voice_sample_rate, verify_piper_available

configure_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Un único cliente de Qdrant y un único modelo de whisper compartidos por todas las
    # conexiones WS, en vez de recrearlos por turno/conexión (cargar el modelo es lento).
    app.state.qdrant = get_client()
    app.state.whisper_model = await asyncio.to_thread(load_whisper_model)
    # Piper corre como subproceso por oración (no hay "modelo" que cargar acá), pero sí
    # falla rápido si el binario/la voz no están disponibles, en vez de recién al hablar.
    verify_piper_available()
    app.state.piper_sample_rate = load_voice_sample_rate()
    yield
    await app.state.qdrant.close()


app = FastAPI(title="offline-personal-assistance orchestrator", lifespan=lifespan)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint() -> dict:
    """Latencias mínimas (Fase 7): TTFB del LLM, latencia de STT y de TTS, últimas 200 muestras
    de cada una. Sin Prometheus — ver app/core/metrics.py."""
    return metrics.snapshot()
