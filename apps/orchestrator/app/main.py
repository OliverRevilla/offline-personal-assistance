import logging

from fastapi import FastAPI

from app.api.ws import router as ws_router
from app.core.config import settings

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(title="offline-personal-assistance orchestrator")
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
