# Guía de testing y cierre — offline-personal-assistance

## 1. Qué existe hoy

| Fase | Estado | Qué hace |
|---|---|---|
| 0 — Bootstrap & Infra | ✅ | `docker-compose` (Ollama + Qdrant + orchestrator), scripts de setup |
| 1 — Backend esqueleto + chat de texto | ✅ | FastAPI + WS, streaming de Ollama |
| 2 — RAG sobre el vault | ✅ | Qdrant + `nomic-embed-text`, indexado manual, citación de notas |
| 3 — Tool calling | ✅ | `buscar_nota`, `crear_nota`, `actualizar_nota` (con confirmación), `listar_tareas` |
| 4 — STT (oídos) | 🔧 implementado, falta que lo pruebes con tu mic real | webrtcvad + faster-whisper (CPU), transcripción alimenta el mismo pipeline de texto |
| 5 — TTS (boca) | ⬜ | Falta |
| 6 — Frontend Tauri + Next.js | ⬜ | Falta |
| 7 — Hardening / observabilidad | ⬜ | Falta |
| 8 — Empaquetado y distribución | ⬜ | Falta |

Detalle completo de cada fase: `docs/ROADMAP.md` en el repo — incluye una sección de "posibles incorporaciones futuras" con las mejoras que fuimos dejando pasar a propósito en cada fase (reindexado incremental, confirmación asíncrona, transcripción parcial, CI, observabilidad, MCP externo, etc.), agrupadas por área. Ninguna está implementada; están anotadas para decidir con su propio ADR más adelante. Arquitectura y protocolo WS: `docs/ARCHITECTURE.md`.

## 2. Requisitos antes de empezar

- Docker + Docker Compose v2 (`docker compose version`).
- Si vas a usar GPU: NVIDIA Container Toolkit instalado y funcionando en el host (Linux/WSL2). En Windows puro sin WSL2, Ollama en Docker **no** va a ver la GPU — o corrés Ollama nativo en Windows (con su propio soporte CUDA) y apuntás `OLLAMA_HOST` a ese proceso, o usás WSL2.
- **Python 3.11 o 3.12** para el venv de `apps/orchestrator` (prudencia general de compatibilidad con `ctranslate2`, no una certeza de que arregle nada por sí solo). Si te aparece `ModuleNotFoundError: pkg_resources` al levantar el server, **no es un tema de versión de Python** — ver la nota en 3.6 y `docs/adr/0005-pkg-resources-pin-setuptools.md` para el diagnóstico real (falta `setuptools` en el venv).

## 3. Walkthrough completo: de cero hasta validar lo que está hecho

Todo esto asume una máquina limpia, sin nada corriendo todavía. Los checkpoints (`✔ Fase N`) son literalmente los criterios de "hecho" de `docs/ROADMAP.md` — si alguno falla, no tiene sentido seguir al siguiente paso.

### 3.1 Clonar y configurar

```bash
cd offline-personal-assistance
cp .env.example .env
```

Revisá `.env`: si Ollama corre nativo en Windows/host (no en Docker) y el orchestrator sí corre en Docker, `OLLAMA_HOST` va a necesitar la IP del host en vez de `localhost`.

### 3.2 Levantar la infraestructura (✔ Fase 0)

```bash
docker compose -f docker/docker-compose.yml up -d ollama qdrant
# con GPU (Linux/WSL2 + NVIDIA Container Toolkit): agregar -f docker/docker-compose.gpu.yml

./scripts/setup.sh      # o scripts\setup.ps1 en Windows
# descarga el modelo LLM + nomic-embed-text, e inicializa la colección de Qdrant

docker compose -f docker/docker-compose.yml exec ollama ollama run qwen2.5:7b-instruct-q4_K_M
```

**✔ Fase 0 si:** el modelo responde en esa última línea (Ctrl+D o `/bye` para salir). Si usaste `-f docker-compose.gpu.yml`, confirmá que usó GPU (en el host: `nvidia-smi` debería mostrar el proceso de `ollama` mientras responde).

### 3.3 Backend + chat de texto (✔ Fase 1)

```bash
cd apps/orchestrator
# Windows, si tu "python"/"py" por defecto es 3.13+: instalá 3.12 aparte y usá el launcher
# para elegirlo explícitamente. Confirmá qué versiones tenés con `py -0p`.
py -3.12 -m venv .venv && .venv\Scripts\activate
# Linux/WSL2 equivalente: python3.12 -m venv .venv && source .venv/bin/activate

pip install -e ".[dev]"
cp ../../.env.example .env

uvicorn app.main:app --reload
```

Si abrís `http://127.0.0.1:8000/` en el navegador para chequear que levantó, vas a ver `404 Not Found` para `GET /` y `GET /favicon.ico` en los logs — es esperado, no un bug: la app no tiene página raíz ni favicon, solo expone `GET /health` y el WebSocket `/ws/chat`. Para confirmar que está sano, entrá a `http://127.0.0.1:8000/health` (debería responder `{"status":"ok"}`).

En otra terminal, desde la raíz del repo:

```bash
python scripts/test_ws_chat.py
```

Escribí cualquier mensaje.

**✔ Fase 1 si:** ves la respuesta del LLM apareciendo token por token en la terminal.

### 3.4 RAG sobre el vault (✔ Fase 2)

Con el servidor todavía arriba, en otra terminal (con el venv de `apps/orchestrator` activado):

```bash
cd apps/orchestrator
python -m app.rag.indexer
```

Es un reindexado completo (recrea la colección de Qdrant desde cero cada vez — no incremental, ver `docs/adr/0001-reindex-completo-vs-incremental.md`). Corré esto de nuevo cada vez que cambies el contenido del vault y quieras que la búsqueda semántica se entere.

Volvé a `scripts/test_ws_chat.py` (podés seguir usando la misma sesión) y preguntá:

> ¿cuál es el nombre en clave del proyecto?

**✔ Fase 2 si:** la respuesta se basa en `notas-de-prueba.md` (el vault de prueba que trae el repo) y la cita explícitamente.

### 3.5 Tool calling (✔ Fase 3)

Seguí en la misma sesión de `test_ws_chat.py`:

1. *"Creame una nota en `pruebas/nota-tool.md` que diga 'hola desde el asistente'"* → invoca `crear_nota` sin pedir confirmación (no sobrescribe nada). Verificá que aparezca `vault/pruebas/nota-tool.md`.
2. *"Cambiá el contenido de `notas-de-prueba.md` a algo distinto"* → el cliente va a mostrar `[confirmación requerida]` y te pide `s`/`n` por consola.
   - Si aprobás: se sobrescribe y queda un backup en `vault/.asistente/backups/`.
   - Si rechazás: el archivo no cambia y el asistente te lo cuenta en su respuesta.
3. Pedile que liste tareas pendientes ("¿qué tareas tengo pendientes?") → invoca `listar_tareas`, que lee cualquier `- [ ]`/`- [x]` de las notas del vault (si el vault de prueba no tiene ninguna todavía, agregá una a mano en `notas-de-prueba.md` antes de probar esto).
4. Revisá `vault/.asistente/audit.jsonl` — debería tener una línea por cada `crear_nota`/`actualizar_nota` que ejecutaste en los pasos 1 y 2.

**✔ Fase 3 si:** el paso 2 efectivamente te pidió confirmación antes de tocar el archivo (no lo hizo directo), y el audit log tiene las entradas esperadas.

### 3.6 STT por micrófono (✔ Fase 4)

El paquete `webrtcvad` compila una extensión en C al instalarse — si `pip install -e ".[dev]"` falla en Windows con un error de compilador (`Microsoft Visual C++ ... required`), probá con el fork que publica wheels precompiladas para Windows (`pip install webrtcvad-wheels` en vez de `webrtcvad`) antes de instalar Build Tools.

La primera vez que arranques el servidor después de este cambio, va a tardar más en levantar: descarga el modelo de whisper (`WHISPER_MODEL_SIZE=base` por default) desde Hugging Face si no lo tenías cacheado — necesita red esa primera vez, después queda en caché local y arranca offline.

Si `uvicorn app.main:app` falla con `ModuleNotFoundError: pkg_resources` (con o sin `--reload`, y persiste incluso con Python 3.12): **no es un problema de versión de Python** (eso lo descartamos — ver `docs/adr/0004-python-311-312-por-ctranslate2.md`, actualizado). Es que el venv no tiene `setuptools` instalado (el módulo `venv` de Python ya no lo instala solo desde hace un tiempo) y `faster-whisper`/`ctranslate2` todavía necesita `pkg_resources` en tiempo de ejecución. Diagnóstico y fix completo en `docs/adr/0005-pkg-resources-pin-setuptools.md`; en resumen, con un venv **recién recreado desde cero** (no reusado):

```powershell
cd apps/orchestrator
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.venv\Scripts\activate
python -c "import sys; print(sys.executable)"   # confirmá que apunta DENTRO de .venv, no a otro Python
pip install -e ".[dev]" -v
python -c "import pkg_resources; print('setuptools ok')"   # smoke test ANTES de probar uvicorn
uvicorn app.main:app
```

Si el smoke test (`import pkg_resources`) ya falla ahí, es un problema del Python/venv de esa máquina, no del código del repo — no tiene sentido seguir tocando dependencias del proyecto hasta que ese import aislado funcione.

```bash
cd apps/orchestrator
uvicorn app.main:app --reload
```

En otra terminal, desde la raíz del repo:

```bash
python scripts/test_stt_mic.py
```

Hablá una frase corta y hacé una pausa. El VAD necesita ~300ms de silencio para decidir que terminaste de hablar antes de mandar el audio a transcribir — no es instantáneo apenas dejás de hablar.

Si no detecta que empezaste a hablar, o corta el audio en medio de la frase: revisá el micrófono que `sounddevice` está usando por default (`python -m sounddevice` lista los dispositivos) y probá subir/bajar `VAD_AGGRESSIVENESS` (0-3) en tu `.env`.

**Checklist de cumplimiento de la Fase 4:**

Prerrequisitos
- [ ] El servidor arrancó sin errores (la primera vez tarda más: está descargando/cargando el modelo de whisper).
- [ ] `GET http://localhost:8000/health` responde `{"status": "ok"}`.

Funcional (criterio de "hecho" del roadmap)
- [ ] `scripts/test_stt_mic.py` conecta sin errores y queda escuchando.
- [ ] Hablando, **no** aparece nada hasta que hacés una pausa de ~300ms — si transcribe a mitad de frase, el VAD está cortando muy agresivo.
- [ ] Al pausar, aparece `[transcripción] ...` con texto razonablemente fiel a lo que dijiste.
- [ ] Después de la transcripción, el turno sigue solo (`[pensando...]`, tokens de respuesta, tool_call si corresponde) sin que hayas escrito nada a mano.
- [ ] Una pregunta que dependa de una nota del vault (ej. "¿cuál es el nombre en clave del proyecto?") responde citándola igual que por texto — confirma que Fase 2 sigue funcionando disparada por voz.
- [ ] Un pedido de crear/actualizar una nota dispara la tool correspondiente igual que por texto, incluida la confirmación si es `actualizar_nota` — confirma que Fase 3 sigue funcionando disparada por voz.

Robustez razonable para esta fase
- [ ] Silencio prolongado sin hablar no genera transcripciones falsas ni tira errores en el server.
- [ ] Frases cortas (una o dos palabras) se transcriben sin romper el flujo.
- [ ] Cortar la conexión (Ctrl+C en el cliente) a mitad de una frase no deja una excepción sin manejar en los logs del backend.

Fuera de alcance de esta fase (no busques esto todavía)
- [ ] No hay transcripción parcial en tiempo real, solo `transcript_final` al terminar el turno — está anotado como mejora futura en `docs/ROADMAP.md`, no es un bug.
- [ ] No hay voz de respuesta (Fase 5) ni interfaz gráfica (Fase 6) todavía.

### 3.7 Correr los tests automatizados

```bash
cd apps/orchestrator
pytest
```

Son tests unitarios (chunking, sandboxing de tools, registry) — no reemplazan la validación manual de arriba, pero conviene correrlos antes de dar por cerrada una sesión de trabajo.

## 4. Observaciones importantes mientras testeás

- **El reindexado RAG es manual y completo**, no incremental ni automático (no hay watcher de archivos). El tool calling sí opera sobre el archivo real al instante; es solo la búsqueda semántica automática la que queda desactualizada hasta el próximo `python -m app.rag.indexer`.
- **`VAULT_PATH` apunta al vault de prueba del repo por default** (`../../vault` desde `apps/orchestrator`). Para tu vault real de Obsidian, cambiá `VAULT_PATH` en tu `.env` local a la ruta absoluta real — y no la commitees, `.env` ya está en `.gitignore`.
- **Si corrés el orchestrator vía Docker**: el `docker-compose.yml` monta `../vault` como `/vault` **en lectura/escritura** (desde la Fase 3 el asistente necesita poder crear/editar notas ahí). Para tu vault real, un `docker-compose.override.yml` local (no versionado) sobreescribiendo ese volumen.
- **Sandboxing de las tools**: `crear_nota`/`actualizar_nota` no pueden escribir fuera del vault (path traversal bloqueado) ni dentro de `vault/.asistente/` (reservado para el audit log y los backups). Un error de "ruta fuera del vault" o "ruta reservada" es este chequeo funcionando, no un bug.
- **La confirmación de `actualizar_nota` es síncrona**: mientras el servidor espera tu `s`/`n`, ese turno de WS queda bloqueado. Documentado en `docs/adr/0002-confirmacion-sincrona-para-tools-destructivas.md` — limitación conocida, no algo para "arreglar" sin pensar el trade-off primero.
- **Presupuesto de VRAM (8GB)**: solo el LLM usa GPU sostenida; STT/TTS (fases 4-5) y los embeddings corren en CPU. No muevas nada a GPU sin pasar por un ADR.
- **VAD es webrtcvad, no Silero** (que era lo pedido originalmente): se cambió a propósito para no meter `torch` como dependencia — te pregunté antes de decidirlo, ver `docs/adr/0003-webrtcvad-en-vez-de-silero-vad.md`. Si en la práctica el reconocimiento de "cuándo empezaste/terminaste de hablar" anda mal (mucho ruido de fondo, etc.), ese ADR es el lugar para reabrir la decisión con evidencia real, no antes.
- **El modelo de whisper se descarga la primera vez que arranca el servidor** (necesita red esa vez; después queda cacheado y corre offline) — mismo patrón que `ollama pull` para el LLM, no es una excepción al diseño offline, es el costo de setup inicial.
- **Transcribir es una llamada bloqueante** (`asyncio.to_thread`): mientras faster-whisper procesa una utterance, ese turno particular no avanza más rápido por tener más CPU libre — es CPU-bound, un modelo `base` en CPU tarda razonablemente poco para frases cortas pero no es instantáneo.
- **`OLLAMA_KEEP_ALIVE`** (default `5m`): si cada mensaje después de una pausa tarda por recarga del modelo, subilo; si la VRAM anda justa, bajalo.
- **`packages/rag-engine/` sigue vacío a propósito** — la lógica vive en `apps/orchestrator/app/rag/` hasta que exista un segundo consumidor real.
- **Convención de nombres**: el código evita prefijos con guion bajo (`_nombre`) para "privado" — si ves uno en algo nuevo que se agregue, no es intencional, avisá para corregirlo.
- **Conexión a un MCP externo**: quedó anotada en `docs/ROADMAP.md` como incorporación futura, no implementada — tensiona con el diseño "100% offline" del proyecto, así que no se agrega sin un ADR que resuelva toggle offline/online, degradación sin red, y qué datos pueden salir de la máquina.

## 5. Pendiente para "finalizar" (no hacer todavía sin criterio)

- No hay tests de integración end-to-end reales todavía (trabajo explícito de la Fase 7, agente `integration-engineer`). Lo que hay son tests unitarios sueltos (`test_health.py`, `test_chunking.py`, `test_vault_tools.py`, `test_tool_registry.py`, `test_vad_segmenter.py`).
- El resto de las mejoras conocidas y deliberadamente pospuestas (reindexado incremental, confirmación asíncrona, CI, observabilidad, etc.) están en la sección "Posibles incorporaciones futuras" de `docs/ROADMAP.md` — revisar ahí antes de decidir qué atacar después de la Fase 8, no reinventar la lista acá.
- Nada de esto está pensado para multi-usuario ni exposición fuera de tu máquina — si aparece la tentación de "exponerlo en la red" o "agregar login", eso es scope creep respecto al roadmap actual.
- Los agentes de desarrollo (`.claude/agents/` en el repo) tienen la responsabilidad de cada área — si estás retomando esto después de un tiempo, es más rápido pedirle a `software-architect` que audite el estado contra `docs/ARCHITECTURE.md` que releer todo el código de cero.