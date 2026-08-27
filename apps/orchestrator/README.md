# apps/orchestrator

Backend FastAPI: gateway WebSocket, STT (faster-whisper + Silero VAD), TTS (Piper), cliente de Ollama (streaming + tool calling), y ejecución de tools contra el vault.

Owners: `backend-engineer`, `lead-ai-engineer` (llm/rag), `integration-engineer` (tools). Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS.

## Estado actual (Fase 1 del roadmap)

Solo chat de texto en streaming sobre Ollama, vía WebSocket. Sin STT/TTS, sin RAG, sin tool calling todavía (ver [docs/ROADMAP.md](../../docs/ROADMAP.md)).

## Cómo correr en local (sin Docker)

```bash
cd apps/orchestrator
python -m venv .venv && source .venv/bin/activate   # en Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp ../../.env.example .env                          # ajustar OLLAMA_HOST si Ollama no corre en localhost
uvicorn app.main:app --reload
```

Requiere Ollama corriendo (local o vía `docker compose -f ../../docker/docker-compose.yml up -d ollama`) con el modelo de `OLLAMA_LLM_MODEL` ya descargado (`scripts/setup.sh` / `setup.ps1`).

## Cómo probar (criterio de "hecho" de la Fase 1)

Con el servidor arriba (`http://localhost:8000/health` debe responder `{"status": "ok"}`):

```bash
python ../../scripts/test_ws_chat.py
```

Escribe un mensaje y deberías ver la respuesta del LLM apareciendo token por token en la terminal.

## Tests

```bash
pytest
```

