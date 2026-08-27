import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ws import router as ws_router
from app.core.config import settings
from app.rag.store import get_client

logging.basicConfig(level=settings.log_level.upper())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Un único cliente de Qdrant compartido por todas las conexiones WS, en vez de abrir
    # una conexión nueva por turno de conversación.
    app.state.qdrant = get_client()
    yield
    await app.state.qdrant.close()


app = FastAPI(title="offline-personal-assistance orchestrator", lifespan=lifespan)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
