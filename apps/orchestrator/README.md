# apps/orchestrator

Backend FastAPI: gateway WebSocket, STT (faster-whisper + webrtcvad), TTS (Piper), cliente de Ollama (streaming + tool calling), y ejecución de tools contra el vault.

Owners: `backend-engineer`, `lead-ai-engineer` (llm/rag), `integration-engineer` (tools). Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS.

## Estado actual (Fase 7 del roadmap)

Chat de texto en streaming sobre Ollama vía WebSocket, con RAG sobre el vault (Qdrant + `nomic-embed-text`), tool calling (`buscar_nota`, `crear_nota`, `actualizar_nota`, `listar_tareas`) con confirmación explícita para la operación destructiva, oídos (webrtcvad + faster-whisper) y boca (Piper-TTS, sentence-buffered, audio incremental por WS). Todo dispara el mismo pipeline sin importar si el turno vino por texto o por voz. Además: reconexión automática del lado del cliente, logging estructurado en JSON, y `GET /metrics` (TTFB del LLM, latencia STT/TTS). Frontend real en `apps/desktop` (Fase 6). Falta empaquetado (Fase 8, ver [docs/ROADMAP.md](../../docs/ROADMAP.md)).

## Cómo correr en local (sin Docker)

Entorno de referencia: **WSL2 con Ubuntu** (ver [docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md](../../docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md)). Ollama, el venv y `uvicorn` corren todos dentro de la misma WSL2 — no mezclar con un Ollama nativo de Windows, ver ese ADR para el porqué.

```bash
cd apps/orchestrator
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp ../../.env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` es necesario si algo fuera de esta WSL2 (el frontend en Windows nativo, Fase 6) necesita conectarse — con el bind default (`127.0.0.1`) eso no es confiable. Ver `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md`.

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

## Cómo probar STT (criterio de "hecho" de la Fase 4)

```bash
python ../../scripts/test_stt_mic.py
```

Hablá una frase, hacé una pausa (~300ms) — debería aparecer `[transcripción] ...` y seguir con el turno normal, igual que si lo hubieras escrito.

## Cómo probar TTS (criterio de "hecho" de la Fase 5)

Requiere el binario `piper` y una voz descargados (ver [models/README.md](../../models/README.md)) — si no están, el servidor falla al arrancar con un error explícito, no recién al hablar.

Con `python ../../scripts/test_ws_chat.py` (o `test_stt_mic.py`, ambos reproducen audio): escribí (o hablá) cualquier mensaje y deberías escuchar la respuesta sintetizada, empezando a sonar por oraciones antes de que el LLM termine de generar el mensaje completo — no esperes a que termine todo el texto para que arranque el audio.

## Observabilidad (Fase 7)

```bash
curl http://localhost:8000/metrics
```

TTFB del LLM, latencia de STT y de TTS (últimas 200 muestras de cada una, no persiste entre reinicios). Los logs del proceso salen en JSON, una línea por evento.

## Tests

```bash
pytest
```

Incluye tests de integración end-to-end (`tests/test_integration_turno.py`) que ejercitan `/ws/chat` completo con Ollama/Piper/Qdrant mockeados.

