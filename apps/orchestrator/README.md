# apps/orchestrator

Backend FastAPI: gateway WebSocket, STT (faster-whisper + webrtcvad), TTS (Piper), cliente de Ollama (streaming + tool calling), y ejecución de tools contra el vault.

Owners: `backend-engineer`, `lead-ai-engineer` (llm/rag), `integration-engineer` (tools). Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS.

## Estado actual (Fase 3 del roadmap)

Chat de texto en streaming sobre Ollama vía WebSocket, con RAG sobre el vault (Qdrant + `nomic-embed-text`) y tool calling (`buscar_nota`, `crear_nota`, `actualizar_nota`, `listar_tareas`) con confirmación explícita para la operación destructiva. Sin STT/TTS todavía (ver [docs/ROADMAP.md](../../docs/ROADMAP.md)).

## Cómo correr en local (sin Docker)

Entorno de referencia: **WSL2 con Ubuntu** (ver [docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md](../../docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md)). Ollama, el venv y `uvicorn` corren todos dentro de la misma WSL2 — no mezclar con un Ollama nativo de Windows, ver ese ADR para el porqué.

```bash
cd apps/orchestrator
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example .env
uvicorn app.main:app --reload
```

Requiere Ollama y Qdrant corriendo dentro de la misma WSL2 (local o vía `docker compose -f ../../docker/docker-compose.yml up -d ollama qdrant`, corrido también desde WSL2), con el modelo LLM y el de embeddings ya descargados y la colección de Qdrant creada (`scripts/setup.sh`, ver [docker/README.md](../../docker/README.md)).

## Indexar el vault (RAG)

Con Ollama y Qdrant arriba y `.env` apuntando a `VAULT_PATH` correctamente (por defecto, el vault de prueba del repo):

```bash
python -m app.rag.indexer
```

Es un reindexado completo (recrea la colección desde cero cada vez — ver [docs/adr/0001-reindex-completo-vs-incremental.md](../../docs/adr/0001-reindex-completo-vs-incremental.md)), hay que correrlo de nuevo cada vez que cambie el contenido del vault.

## Cómo probar (criterio de "hecho" de la Fase 2)

Con el servidor arriba y el vault ya indexado:

```bash
python ../../scripts/test_ws_chat.py
```

Preguntá algo cuya respuesta esté en una nota real del vault (con el vault de prueba que trae el repo: "¿cuál es el nombre en clave del proyecto?") — la respuesta debe basarse en esa nota y citarla explícitamente.

## Cómo probar tool calling (criterio de "hecho" de la Fase 3)

Con el mismo cliente (`python ../../scripts/test_ws_chat.py`):

- *"Creame una nota en `pruebas/nota-tool.md` que diga 'hola desde el asistente'"* → debería invocar `crear_nota` sin pedir confirmación (no es destructiva) y el archivo debería aparecer en `vault/pruebas/nota-tool.md`.
- *"Cambiá el contenido de `notas-de-prueba.md` a 'contenido de prueba actualizado'"* → el cliente va a mostrar `[confirmación requerida]`; respondé `s` o `n` cuando lo pida. Si aprobás, el archivo se sobrescribe y queda un backup en `vault/.asistente/backups/`; si rechazás, el archivo no cambia y el asistente te lo cuenta.
- Revisá `vault/.asistente/audit.jsonl` — debería tener una entrada por cada `crear_nota`/`actualizar_nota` ejecutada, con timestamp y ruta.

## Tests

```bash
pytest
```

