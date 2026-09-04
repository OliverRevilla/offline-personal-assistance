# Guía de testing y cierre — offline-personal-assistance

## 1. Qué existe hoy

| Fase | Estado | Qué hace |
|---|---|---|
| 0 — Bootstrap & Infra | ✅ | `docker-compose` (Qdrant + orchestrator; Ollama nativo por default, ver `docker/README.md`), scripts de setup |
| 1 — Backend esqueleto + chat de texto | ✅ | FastAPI + WS, streaming de Ollama |
| 2 — RAG sobre el vault | ✅ | Qdrant + `nomic-embed-text`, indexado manual, citación de notas |
| 3 — Tool calling | ✅ | `buscar_nota`, `crear_nota`, `actualizar_nota` (con confirmación), `listar_tareas` |
| 4 — STT (oídos) | ✅ (probado, "medianamente correcto" — precisión anotada como mejora futura) | webrtcvad + faster-whisper (CPU), transcripción alimenta el mismo pipeline de texto |
| 5 — TTS (boca) | 🔧 implementado, falta que lo pruebes | Piper-TTS (subproceso CLI), sentence-buffering, audio incremental por WS |
| 6 — Frontend Tauri + Next.js | 🔧 implementado, falta que lo pruebes | Tauri nativo en Windows + Next.js estático, WS + AudioWorklet |
| 7 — Hardening / observabilidad | 🔧 implementado, falta que lo pruebes | Reconexión automática, logging JSON, `GET /metrics`, tests de integración end-to-end |
| 8 — Empaquetado y distribución | ⬜ | Falta |

Detalle completo de cada fase: `docs/ROADMAP.md` en el repo — incluye una sección de "posibles incorporaciones futuras" con las mejoras que fuimos dejando pasar a propósito en cada fase (reindexado incremental, confirmación asíncrona, transcripción parcial, CI, observabilidad, MCP externo, etc.), agrupadas por área. Ninguna está implementada; están anotadas para decidir con su propio ADR más adelante. Arquitectura y protocolo WS: `docs/ARCHITECTURE.md`.

## 2. Requisitos antes de empezar

- **Todo corre dentro de WSL2 con Ubuntu — sin excepciones ni mezclas.** No "un poco en PowerShell y un poco en WSL": Ollama, el venv de Python, `uvicorn`, y los comandos de `docker compose` corren *todos* desde la misma terminal de WSL2. Ver `docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md` — mezclar Windows nativo y WSL2 para piezas que necesitan hablarse entre sí (típicamente Ollama) hizo perder una sesión entera de debugging por tener **dos Ollamas distintos** escuchando en el mismo `localhost:11434`, cada uno desde su propio namespace de red, con modelos descargados de un solo lado.
- Docker + Docker Compose v2 (`docker compose version`), con la integración de Docker Desktop con WSL2 activada (o el Docker Engine instalado directo dentro de la distro).
- GPU: con Ollama nativo (caso por defecto), alcanza con los drivers NVIDIA/CUDA de WSL2 — confirmá con `nvidia-smi` corrido *desde dentro de WSL2*. El NVIDIA Container Toolkit (`docker-compose.gpu.yml`) solo hace falta si usás el escenario alternativo de Ollama containerizado (ver `docker/README.md`).
- **Python 3.11 o 3.12** para el venv de `apps/orchestrator` (prudencia de compatibilidad con `ctranslate2`; instalable en Ubuntu con `sudo apt install python3.12 python3.12-venv` si no viene por default). Si te aparece `ModuleNotFoundError: pkg_resources` al levantar el server, **no es un tema de versión de Python** — ver `docs/adr/0005-pkg-resources-pin-setuptools.md`.
- **Node.js LTS + Rust/Cargo, instalados en Windows nativo** (no en WSL2) para `apps/desktop` — a diferencia de todo lo demás, el frontend Tauri corre nativo en Windows a propósito (ver `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md`). El backend en WSL2 no se toca. Además, **el repo está clonado dos veces** (uno en WSL2, otro en NTFS nativo de Windows solo para el frontend) — no es el mismo checkout accedido desde los dos lados, ver la adenda 3 del ADR 0008 antes de intentar "simplificarlo" a un solo checkout.

## 3. Walkthrough completo: de cero hasta validar lo que está hecho

Todo esto asume una máquina limpia, sin nada corriendo todavía. Los checkpoints (`✔ Fase N`) son literalmente los criterios de "hecho" de `docs/ROADMAP.md` — si alguno falla, no tiene sentido seguir al siguiente paso.

### 3.1 Clonar y configurar

```bash
cd offline-personal-assistance
cp .env.example .env
```

`OLLAMA_HOST=http://localhost:11434` del `.env.example` asume que Ollama corre dentro de la misma WSL2 (nativo ahí, o vía Docker con la integración de WSL2) — no lo cambies para apuntar a un Ollama de Windows nativo, esa mezcla es justamente la que causó el incidente documentado en `docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md`.

### 3.2 Levantar la infraestructura (✔ Fase 0)

Todo esto, desde una terminal de WSL2 (no PowerShell). Asume que **ya tenés Ollama instalado nativo** en tu distro (el caso por defecto de este repo — ver `docker/README.md` si en cambio no lo tenés y preferís todo containerizado, escenario B ahí):

```bash
docker compose -f docker/docker-compose.yml up -d qdrant

./scripts/setup.sh
# pullea el modelo LLM + nomic-embed-text con el `ollama` nativo, e inicializa la colección de Qdrant

ollama run qwen2.5:7b-instruct-q4_K_M
```

Si en cambio NO tenés Ollama nativo y preferís containerizarlo también (escenario B de `docker/README.md`):

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.ollama.yml up -d ollama qdrant
# con GPU: agregar también -f docker/docker-compose.gpu.yml

docker compose -f docker/docker-compose.yml -f docker/docker-compose.ollama.yml exec ollama ollama run qwen2.5:7b-instruct-q4_K_M
```

(`scripts/setup.ps1` existe solo para el caso de correr *todo* — Ollama incluido — nativo en Windows sin WSL2 en absoluto. No lo mezcles con pasos corridos en WSL2.)

**✔ Fase 0 si:** el modelo responde en esa última línea (Ctrl+D o `/bye` para salir). Si usaste `-f docker-compose.gpu.yml`, confirmá que usó GPU (en el host: `nvidia-smi` debería mostrar el proceso de `ollama` mientras responde).

### 3.3 Backend + chat de texto (✔ Fase 1)

Desde WSL2 (si tu `python3` por defecto no es 3.11/3.12: `sudo apt install python3.12 python3.12-venv` primero):

```bash
cd apps/orchestrator
python3.12 -m venv .venv && source .venv/bin/activate

pip install -e ".[dev]"
cp ../../.env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` no es opcional acá: `uvicorn` sin `--host` bindea solo a `127.0.0.1` **dentro de WSL2**, y aunque WSL2 reenvía casi todo a Windows como `localhost` (localhost forwarding), no vale la pena depender de que esa magia cubra también el caso de bind-solo-loopback-dentro-de-la-VM — con `0.0.0.0` no hay ambigüedad, el puerto 8000 escucha en todas las interfaces de la VM y WSL2 lo expone a Windows sin duda. Vas a necesitar esto para la Fase 6 (frontend en Windows) y para la guía de testeo end-to-end (3.11).

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

El paquete `webrtcvad` compila una extensión en C al instalarse — en Ubuntu/WSL2, si `pip install -e ".[dev]"` falla compilándolo, instalá las herramientas de build primero: `sudo apt install build-essential python3.12-dev` y reintentá.

La primera vez que arranques el servidor después de este cambio, va a tardar más en levantar: descarga el modelo de whisper (`WHISPER_MODEL_SIZE=base` por default) desde Hugging Face si no lo tenías cacheado — necesita red esa primera vez, después queda en caché local y arranca offline.

Si `uvicorn app.main:app` falla con `ModuleNotFoundError: pkg_resources` (con o sin `--reload`, y persiste incluso con Python 3.12): **no es un problema de versión de Python** (ver `docs/adr/0004-python-311-312-por-ctranslate2.md`, actualizado). Es que el venv no tiene `setuptools` instalado y `faster-whisper`/`ctranslate2` todavía necesita `pkg_resources` en tiempo de ejecución. Diagnóstico y fix completo en `docs/adr/0005-pkg-resources-pin-setuptools.md`; en resumen, con un venv **recién recreado desde cero** (no reusado):

```bash
cd apps/orchestrator
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate
python -c "import sys; print(sys.executable)"   # confirmá que apunta DENTRO de .venv
pip install -e ".[dev]" -v
python -c "import pkg_resources; print('setuptools ok')"   # smoke test ANTES de probar uvicorn
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Si el smoke test (`import pkg_resources`) ya falla ahí, es un problema del Python/venv de esa máquina, no del código del repo — no tiene sentido seguir tocando dependencias del proyecto hasta que ese import aislado funcione.

Si en cambio el server levanta bien pero el chat responde `model '...' not found` aunque el modelo "esté pulleado": **confirmá desde la MISMA terminal de WSL2 donde corre uvicorn** (`curl http://localhost:11434/api/tags`) que el modelo aparece ahí — no alcanza con haberlo visto desde PowerShell/Windows. Ver `docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md`: es posible tener dos Ollama corriendo en paralelo (uno nativo en Windows, otro en WSL2), cada uno con sus propios modelos, ambos respondiendo en `localhost:11434` pero cada uno en su propio namespace de red.

En otra terminal (también dentro de WSL2), desde la raíz del repo:

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
- [ ] No hay interfaz gráfica (Fase 6) todavía.

### 3.7 TTS: la boca del asistente (✔ Fase 5)

Antes de nada, necesitás el binario `piper` y una voz descargados — no vienen con el repo (son binarios/modelos grandes). Ver [models/README.md](models/README.md) para los links y dónde dejarlos (`models/piper/`).

Con eso listo, arrancá el servidor de nuevo (si el binario/la voz no están, va a fallar acá mismo con un error explícito, no recién cuando le hables):

```bash
cd apps/orchestrator
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Y probá con cualquiera de los dos clientes (ambos reproducen audio ahora):

```bash
python scripts/test_ws_chat.py     # escribiendo
# o
python scripts/test_stt_mic.py     # hablando (Fases 4+5 combinadas)
```

Mandá un mensaje que genere una respuesta de varias oraciones (ej. "contame en detalle qué es este proyecto"). Deberías **escuchar** la respuesta, con el audio de la primera oración empezando a sonar mientras el LLM todavía está generando el resto del texto — no un silencio hasta que termine todo y recién ahí arranque el audio.

**Checklist de cumplimiento de la Fase 5:**

Prerrequisitos
- [ ] El servidor arrancó sin errores de Piper (si el binario o la voz no están, el error lo dice explícitamente al levantar, no al hablar).

Funcional (criterio de "hecho" del roadmap)
- [ ] Se escucha audio de la respuesta, no solo texto.
- [ ] Con una respuesta de varias oraciones, el audio de la primera empieza a sonar notablemente antes de que el texto completo termine de imprimirse en la terminal — esa es la prueba real de que el sentence-buffering funciona y no se está esperando al mensaje completo.
- [ ] La voz suena razonablemente inteligible (no tiene que ser perfecta, pero tiene que entenderse).

Robustez razonable para esta fase
- [ ] Un mensaje muy corto (una sola oración, o sin punto final) igual produce audio.
- [ ] Un turno con tool calling de por medio (ej. pedir que liste tareas) sigue generando audio de la respuesta final, no se rompe por los `tool_call`/`tool_result` intermedios.
- [ ] Si detenés el cliente a mitad de la síntesis (Ctrl+C), el servidor no queda con un proceso de Piper colgado ni una excepción sin manejar en los logs.

Fuera de alcance de esta fase (no busques esto todavía)
- [ ] No hay interrupción de la voz por parte del usuario ("barge-in") — si el asistente está hablando y el usuario escribe/habla de nuevo, no hay lógica especial de corte todavía.
- [ ] El empaquetado en Docker de Piper (binario + voz dentro de la imagen) queda para la Fase 8 — ver [docs/adr/0007](docs/adr/0007-piper-como-subproceso-cli.md).

### 3.8 Frontend: la app de escritorio (✔ Fase 6)

**El proceso corre en Windows nativo, no en WSL2** (ver `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md`). El backend (`apps/orchestrator`) tiene que seguir corriendo en WSL2 mientras probás esto.

**Ojo con esto:** hay **dos checkouts del repo**, no uno accedido desde dos lados. Se probó primero acceder al mismo checkout de WSL2 desde Windows vía `\\wsl.localhost\<distro>\...`, y se abandonó — `cmd.exe` en Windows rechaza estructuralmente una ruta UNC como directorio de trabajo de un proceso, y eso rompía `npm run tauri dev` sin un fix limpio (adendas 2 y 3 del ADR 0008). La solución final es un **segundo clon del repo en el filesystem nativo de Windows (NTFS)**, usado solo para `apps/desktop`. Instrucciones completas en [apps/desktop/README.md](apps/desktop/README.md#cómo-correr) — acá el resumen:

Requisitos en Windows (una sola vez): Node.js LTS, Rust vía [rustup.rs](https://rustup.rs), y el toolchain de C++ de Visual Studio (ver `apps/desktop/README.md` — sin esto, `cargo` falla con errores de linker). No hace falta instalar la Tauri CLI global, es una dependencia de npm.

```powershell
# una sola vez: clonar el repo en NTFS nativo (no en \\wsl.localhost\...)
cd C:\Users\tu-usuario\proyectos
git clone \\wsl.localhost\Ubuntu\home\tu-usuario\ruta\a\offline-personal-assistance offline-personal-assistance

cd C:\Users\tu-usuario\proyectos\offline-personal-assistance\apps\desktop
npm install
copy .env.local.example .env.local
npm run tauri dev
```

La primera vez, `cargo` va a compilar bastante (es la primera build de Tauri) — puede tardar varios minutos. Se abre una ventana nativa con la UI.

**De acá en adelante, cada cambio en `apps/desktop` necesita `git pull` en ESTE clon de Windows también** — no solo en el de WSL2. Son dos checkouts independientes.

**✔ Fase 6 si:** con el backend corriendo en WSL2, la ventana conecta ("Conectado" en la barra de estado), podés escribir un mensaje y ver la respuesta en pantalla + escucharla, y activando el micrófono (🎙️) podés hablarle y que responda por voz — el mismo flujo end-to-end de las fases 1-5, ahora con UI real en vez de scripts de consola.

**Checklist de cumplimiento de la Fase 6:**

- [ ] `npm install` no falla (si falla compilando algo de Rust, revisá que `cargo`/Visual Studio Build Tools estén bien instalados — Tauri en Windows los necesita).
- [ ] `npm run tauri dev` abre una ventana y la barra de estado dice "Conectado".
- [ ] Escribir un mensaje de texto y recibir la respuesta en pantalla, token por token.
- [ ] Se escucha la respuesta en el parlante (no solo texto).
- [ ] Activar el micrófono, hablar, y ver la transcripción aparecer como mensaje de usuario, seguida de la respuesta normal.
- [ ] Pedir crear/actualizar una nota dispara la tool y, si es `actualizar_nota`, aparece la barra de confirmación (Aprobar/Rechazar) en la UI — no en una consola.
- [ ] Cerrar la ventana no deja el backend en un estado raro (probá mandar otro mensaje desde `scripts/test_ws_chat.py` después de cerrar la app: debería seguir funcionando).

Fuera de alcance de esta fase (no busques esto todavía)
- [ ] Sin instalador/empaquetado (`tauri build`) — eso es la Fase 8. Los íconos ya existen como placeholders (un cuadrado azul con una "A") para que `tauri dev` compile en Windows — ver `src-tauri/icons/README.md` sobre por qué hacían falta antes de lo esperado, y por qué falta `icon.icns` (macOS) todavía.
- [ ] Sin indicador visual de "escuchando activamente vs. en silencio" durante la captura de mic — el botón solo indica on/off, no el estado del VAD en tiempo real.

### 3.9 Hardening y observabilidad (✔ Fase 7)

Con el backend arriba (WSL2):

```bash
curl http://localhost:8000/metrics
```

Debería devolver algo como:

```json
{"llm_ttfb": {"count": 0}, "stt_latency": {"count": 0}, "tts_latency": {"count": 0}}
```

`count: 0` es normal si todavía no mandaste ningún mensaje en esta corrida del server — las métricas no persisten entre reinicios. Mandá un par de mensajes (texto o voz) con cualquiera de los clientes y volvé a pedir `/metrics`: ahora `count` debería subir y aparecer `avg_ms`/`p50_ms`/`max_ms`.

**Probar la reconexión** (con la app de Tauri abierta y conectada):
1. Pará el backend (Ctrl+C en la terminal de WSL2 donde corre `uvicorn`).
2. En la UI, la barra de estado debería pasar a "Desconectado" en unos segundos.
3. Volvé a levantar el backend (`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`).
4. La UI debería reconectar sola (backoff exponencial: 1s, 2s, 4s... hasta 10s) y mostrar un mensaje de sistema tipo "Reconectado — el contexto de la conversación anterior se perdió".
5. Mandá un mensaje nuevo: debería responder normal (es una sesión nueva del lado del server, pero funcional).

**Probar que una desconexión a mitad de turno no rompe el server**: pedile a la app que actualice una nota (dispara `actualizar_nota`, que pide confirmación) y, con la barra de confirmación en pantalla, cerrá la ventana de la app de golpe (sin aprobar/rechazar) en vez de responder. Volvé a abrir la app (`npm run tauri dev` de nuevo si hace falta) y mandá un mensaje cualquiera — debería responder normal. Si el backend quedó vivo y responde bien a la conexión nueva, esto está probado (hay un test automatizado equivalente en `test_integration_turno.py` que ejercita exactamente este caso sin necesitar la UI).

**Checklist de cumplimiento de la Fase 7:**

- [ ] `GET /metrics` responde JSON válido, y los contadores suben después de usar el chat.
- [ ] Los logs del backend salen en JSON (una línea por evento), no en el formato de texto plano de antes.
- [ ] Parar y volver a levantar el backend con la app abierta: la UI reconecta sola y avisa que se perdió el contexto.
- [ ] Cerrar la app de golpe con una confirmación pendiente no deja el backend en mal estado — una conexión nueva después funciona normal.
- [ ] `pytest` (ver 3.10) pasa, incluido `test_integration_turno.py`.

Fuera de alcance de esta fase (no busques esto todavía)
- [ ] Sin CI — `pytest` se sigue corriendo a mano.
- [ ] Sin persistencia de la conversación entre reinicios — la reconexión es automática, pero el historial antes del corte se pierde (avisado en la UI, no recuperado).

**Medir el pico de VRAM (LLM + STT simultáneos) — esto es manual, en tu hardware real, no algo que se automatice:**

1. En una terminal de WSL2: `watch -n 1 nvidia-smi` (o `nvidia-smi -l 1`) para ver el uso de VRAM en vivo.
2. Con la app de Tauri conectada, escribí un mensaje que genere una respuesta larga (ej. "contame en detalle la arquitectura completa de este proyecto, con todos los componentes").
3. Mientras el LLM todavía está generando (vas a ver los tokens/audio llegando), activá el micrófono y hablale una frase — esto fuerza a que el LLM esté generando **y** faster-whisper esté transcribiendo al mismo tiempo, el peor caso real según `docs/ARCHITECTURE.md`.
4. Anotá el pico de VRAM que mostró `nvidia-smi` durante ese solapamiento. Si se acerca a tus 8GB totales, es una señal real para revisar `OLLAMA_KEEP_ALIVE` o el tamaño del modelo — no antes de tener este dato.

### 3.10 Correr los tests automatizados

```bash
cd apps/orchestrator
pytest
```

Incluye los unitarios (chunking, sandboxing de tools, registry, VAD, sentence buffer) y los de integración end-to-end (`test_integration_turno.py`, Fase 7) que ejercitan el WS completo con Ollama/Piper/Qdrant mockeados — no reemplazan la validación manual de arriba, pero conviene correrlos antes de dar por cerrada una sesión de trabajo.

### 3.11 Test end-to-end completo: todo el stack en su topología real (Windows + WSL2)

Esto es el capítulo que junta todo: backend completo en WSL2, frontend nativo en Windows, probado como topología real (dos "máquinas" hablándose por red), no como scripts sueltos.

**Mapa de la topología** (dos checkouts del repo, uno por lado — ver `docs/adr/0008`, adenda 3):

```
┌──────────── WSL2 (Ubuntu) — checkout #1 ─────────────┐
│  Ollama (nativo, :11434)                              │
│  Qdrant (Docker, :6333)                               │
│  orchestrator (uvicorn, :8000, bindeado a 0.0.0.0)     │
└───────────────────────────┬────────────────────────────┘
                             │ WSL2 localhost forwarding
                             │ (0.0.0.0:8000 dentro de WSL2 ≈ localhost:8000 en Windows)
┌────────────────────────────┴── Windows — checkout #2 ─┐
│  Tauri app (Next.js + WebView2) → ws://localhost:8000/ws/chat │
│  (clon separado en NTFS, ej. C:\Users\...\proyectos\...)       │
└─────────────────────────────────────────────────────────────┘
```

#### Secuencia de arranque (el orden importa)

**1. WSL2 — Ollama** (si no corre como servicio, en una terminal dedicada o de fondo):
```bash
pgrep -a ollama || ollama serve &
curl http://localhost:11434/api/tags   # confirmá que devuelve tus modelos
```

**2. WSL2 — Qdrant:**
```bash
docker compose -f docker/docker-compose.yml up -d qdrant
```

**3. WSL2 — orchestrator** (en su propia terminal, venv activado):
```bash
cd apps/orchestrator
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**4. Checkpoint crítico #1 — confirmá el backend DESDE DENTRO de WSL2:**
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

**5. Checkpoint crítico #2 — confirmá el backend DESDE WINDOWS, ANTES de abrir Tauri** (PowerShell):
```powershell
Invoke-RestMethod http://localhost:8000/health
```
Si esto falla acá, **no tiene sentido seguir con Tauri todavía** — andá directo a la sección de troubleshooting (A) más abajo. Si esto funciona, el 90% del riesgo de la topología cruzada ya está descartado.

**6. Windows — frontend** (en el clon separado de NTFS nativo, no en `\\wsl.localhost\...` — ver 3.8 y `apps/desktop/README.md`; recordá `git pull` ahí también si cambió algo):
```powershell
cd C:\Users\tu-usuario\proyectos\offline-personal-assistance\apps\desktop
npm run tauri dev
```

**7. En la ventana que se abre:** la barra de estado debe decir "Conectado" en los primeros segundos.

**8. Checklist funcional completo** (todo desde la UI, no desde scripts):
- [ ] Mensaje de texto → respuesta en pantalla + audio.
- [ ] Micrófono → transcripción aparece como mensaje de usuario → respuesta normal.
- [ ] Pedido de crear nota → se crea, sin confirmación.
- [ ] Pedido de actualizar una nota → aparece la barra de confirmación en la UI → aprobar → se actualiza y queda backup.
- [ ] `curl http://localhost:8000/metrics` (desde WSL2 o `Invoke-RestMethod` desde Windows) muestra `count` > 0 después de esas interacciones.
- [ ] Parar y levantar el backend de nuevo con la app abierta → reconecta sola, avisa que se perdió el contexto.

#### Troubleshooting — por síntoma

**(A) `Invoke-RestMethod`/el navegador en Windows no llega al backend, pero `curl` desde dentro de WSL2 sí funciona.**
1. **Primera sospecha, la más común: el bind.** Confirmá que arrancaste `uvicorn` con `--host 0.0.0.0` (no el default `127.0.0.1`). Si lo relanzaste, esperá a que termine de arrancar antes de reintentar.
2. **Segunda sospecha: WSL2 quedó en mal estado de red** (pasa después de suspender/hibernar la laptop, o updates de Windows). Fix genérico: cerrá todas las terminales de WSL2, `wsl --shutdown` desde PowerShell (esto apaga la VM entera, no solo la terminal), esperá ~10 segundos, y volvé a abrir la distro y levantar todo de nuevo desde el paso 1.
3. **Tercera sospecha: `localhostForwarding` deshabilitado a mano.** Revisá `%UserProfile%\.wslconfig` (si existe) por una línea `localhostForwarding=false` — el default es `true` (habilitado), así que si el archivo no existe o no tiene esa línea, no es esto. Si la encontrás, borrala o ponela en `true`, y `wsl --shutdown` para que tome efecto.
4. **Cuarta sospecha, más rara: firewall de terceros** (no el de Windows Defender estándar, que no suele bloquear esto). Probá `Test-NetConnection -ComputerName localhost -Port 8000` desde PowerShell — si dice `TcpTestSucceeded: False`, hay algo bloqueando a nivel de Windows, no de WSL2 ni del backend.
5. **Último recurso (no debería hacer falta, pero es el fallback real si nada de lo anterior funciona):** conseguí la IP de la VM de WSL2 con `hostname -I` (desde dentro de WSL2) y usá esa IP en vez de `localhost` en `apps/desktop/.env.local` (`NEXT_PUBLIC_WS_URL=ws://<esa-ip>:8000/ws/chat`). Esta IP puede cambiar entre reinicios de Windows en el modo de red NAT clásico de WSL2 — es un parche temporal, no una solución permanente; si termina siendo necesario de forma consistente, es señal de que algo en el punto 2 o 3 no se resolvió del todo.

**(B) La app de Tauri abre pero la barra de estado dice "Desconectado" y no cambia nunca.**
1. Repetí el checkpoint #2 (arriba) — si falla, es el problema (A), no de la app.
2. Revisá `apps/desktop/.env.local` (no `.env.local.example`) — tiene que existir y apuntar a la URL correcta. Si lo creaste/editaste con `npm run tauri dev` ya corriendo, paralo (Ctrl+C) y volvé a correrlo — Next.js relee `.env.local` al arrancar, no siempre en caliente.
3. Abrí las devtools de la ventana (clic derecho → "Inspeccionar", o F12) y mirá la consola: un error de WebSocket ahí (`ECONNREFUSED`, `Connection refused`, etc.) te dice más que la barra de estado sola.
4. Si el error en consola menciona CSP (Content-Security-Policy): revisá que `tauri.conf.json` tenga `"security": {"csp": null}` (ya viene así) — un CSP no-null mal configurado podría bloquear la conexión WS.

**(C) Conecta ("Conectado" en la barra), pero escribir un mensaje no genera ninguna respuesta.**
1. Mirá los logs del backend (ahora en JSON) buscando `"level": "ERROR"`.
2. Sospecha #1: Ollama no tiene el modelo pulleado, o `OLLAMA_HOST`/`OLLAMA_LLM_MODEL` en `apps/orchestrator/.env` no coinciden con lo que Ollama realmente tiene — repetí el diagnóstico de `curl http://localhost:11434/api/tags` que ya usamos antes.
3. Sospecha #2 (menos probable, degrada con gracia): Qdrant caído — no debería bloquear el chat (RAG falla en silencio y sigue sin contexto), pero si además ves errores de Qdrant en el log, confirmá `docker compose -f docker/docker-compose.yml ps`.

**(D) El botón de micrófono no capta nada, o tira un error al activarlo.**
1. **Windows Settings → Privacy & Security → Microphone**: confirmá que "Let apps access your microphone" está activado, Y que las "apps de escritorio" específicamente tienen permiso (Windows separa el permiso de apps de la Store del de apps de escritorio/Win32 — Tauri cae en esta segunda categoría). Sin esto, `getUserMedia` falla silenciosamente o con `NotAllowedError` aunque el webview no muestre ningún prompt.
2. Mirá la consola JS (devtools): `NotAllowedError` = permiso denegado (punto 1); `NotFoundError` = no hay ningún micrófono detectado por Windows — revisá el dispositivo de grabación default en la configuración de sonido de Windows.
3. Si captura pero el VAD nunca dispara transcripción: no es un problema de Windows/WSL2, es el ajuste de `VAD_AGGRESSIVENESS`/`VAD_WINDOW_MS` que ya vimos en la Fase 4.

**(E) Se ve el texto de la respuesta pero no se escucha nada.**
1. Confirmá que el backend arrancó sin error de Piper (si faltara el binario/voz, no llegaría a arrancar — así que si estás en este punto, Piper está bien del lado del server).
2. Los navegadores (WebView2 incluido) requieren un gesto del usuario antes de que un `AudioContext` pueda sonar — como la UI ya requiere tocar el botón de mic o el de enviar para generar cualquier turno, esto normalmente ya está cubierto, pero si el audio nunca arrancó ni una vez en toda la sesión, es la primera sospecha.
3. Revisá el volumen/dispositivo de salida default de Windows (algo tan tonto como esto pasa más seguido de lo que parece).

**(F) Todo anduvo bien un rato y después las respuestas se vuelven lentas o dejan de llegar.**
1. `curl http://localhost:8000/metrics` (o `Invoke-RestMethod` desde Windows) — si `llm_ttfb`/`stt_latency`/`tts_latency` muestran `max_ms` mucho más alto que `avg_ms`, hay algo puntual, no un problema sistemático.
2. Si pasó un rato sin usarlo y el primer mensaje después de la pausa tarda mucho: es `OLLAMA_KEEP_ALIVE` descargando el modelo de la VRAM y volviéndolo a cargar — normal, no un bug.
3. `nvidia-smi` (desde WSL2) para descartar que la VRAM esté al límite.

**(G) `npm install` o `npm run tauri dev` falla compilando la parte de Rust.**
Además de Node.js y Rust/Cargo (ya mencionados en la Fase 6): en Windows, Tauri necesita el **toolchain de compilación de C++ de Visual Studio** (Visual Studio Installer → workload "Desktop development with C++", o los "Build Tools for Visual Studio" standalone si no querés instalar el IDE completo). Sin esto, la compilación del binario Rust falla con errores de linker (`link.exe not found` o similares) — no es un error de nuestro código, es un prerequisito de la toolchain de Windows para cualquier proyecto Rust/Tauri.

**(H) `npm run tauri dev` tira `Couldn't recognize the current folder as a Tauri project`, o cualquier otra rareza corriendo el frontend desde `\\wsl.localhost\...`.**
No lo investigues más — **no se usa esa ruta**, se abandonó de raíz. La causa era estructural: `cmd.exe` en Windows rechaza una ruta UNC como directorio de trabajo de un proceso (lo confirmamos con evidencia directa: el propio `cmd.exe` avisa *"No se permiten rutas UNC. Regresando de manera predeterminada al directorio Windows."* y el proceso hijo hereda `C:\Windows` en vez de `apps\desktop`), y ni mapear una letra de unidad con `net use` ni forzar `script-shell=powershell.exe` en npm lo resolvieron del todo (ver adendas 2 y 3 de `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md`).

**Si estás viendo este error, es porque estás corriendo desde el checkout equivocado.** El frontend corre desde un **segundo clon del repo en NTFS nativo de Windows** (ej. `C:\Users\...\proyectos\offline-personal-assistance`), no desde `\\wsl.localhost\...` — ver 3.8 más arriba y `apps/desktop/README.md`. Si ya estás en ese clon nativo y el error persiste, ahí sí es otra cosa (revisá que `git clone` haya traído todo bien, `dir src-tauri` para confirmar que `tauri.conf.json` existe en ese clon).

## 4. Observaciones importantes mientras testeás

- **El frontend (Fase 6) es la única pieza que corre nativo en Windows, a propósito** — el backend sigue 100% en WSL2. No es una contradicción del ADR 0006 (ese ADR habla de no duplicar el *mismo servicio* entre los dos lados, típicamente Ollama); acá son dos procesos distintos hablándose por WebSocket. Ver `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md`.
- **Corré el frontend desde el clon de NTFS nativo, nunca desde `\\wsl.localhost\...`** — ya se probó esa vía y se abandonó por un problema estructural de Windows (`cmd.exe` rechazando rutas UNC como directorio de proceso), no un bug de nuestro código. Ver la adenda 3 de `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md` y el punto (H) del troubleshooting de 3.11 si volvés a ver ese error.
- **Sin `packages/shared-contracts/` todavía**: el contrato del protocolo WS está duplicado a mano en `apps/desktop/src/lib/protocol.ts` (TypeScript) y `apps/orchestrator/app/api/ws.py` (comentario Python). Si cambiás el protocolo de un lado, acordate de actualizar el otro.
- **Todo corre en WSL2 con Ubuntu, sin mezclar con Windows nativo** — esto costó una sesión entera de debugging (`docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md`): tener Ollama instalado tanto nativo en Windows como dentro de WSL2 hace que `localhost:11434` resuelva a dos procesos completamente distintos según desde dónde lo llames, cada uno con sus propios modelos descargados. Un `Invoke-RestMethod` desde PowerShell puede funcionar perfecto mientras el orchestrator (corriendo en WSL2) recibe `model not found` para el mismo modelo — no es contradictorio, son dos servidores distintos. Si algo "funciona en una terminal pero no en otra", lo primero a sospechar es esto, no el código.
- **Ollama nativo por default, no containerizado**: `docker-compose.yml` solo trae Qdrant + orchestrator; Ollama corre en el host (WSL2) porque ya lo tenías instalado ahí y containerizarlo no suma nada de performance (ni CPU ni GPU — los contenedores Linux son namespaces, no VMs). El override `docker-compose.ollama.yml` existe para quien no tenga Ollama nativo, ver `docker/README.md` — no combinar ambos.
- **Piper corre como subproceso CLI, no como paquete pip** (ver `docs/adr/0007-piper-como-subproceso-cli.md`) — a propósito, para no meter otra extensión compilada frágil entre versiones de Python al proyecto (ya nos pasó dos veces con `ctranslate2` y, en menor medida, `webrtcvad`). Esto implica un proceso de Piper nuevo por cada oración sintetizada, no un modelo cargado en memoria una sola vez — para frases cortas el overhead es aceptable, si en la práctica se nota lento vale la pena revisar ese ADR.
- **El binario y la voz de Piper no vienen con el repo** (son binarios grandes) — hay que descargarlos a mano en `models/piper/` antes de la Fase 5, ver `models/README.md`. Si faltan, el servidor falla al arrancar con un error explícito.
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

- No hay tests de integración end-to-end reales todavía (trabajo explícito de la Fase 7, agente `integration-engineer`). Lo que hay son tests unitarios sueltos (`test_health.py`, `test_chunking.py`, `test_vault_tools.py`, `test_tool_registry.py`, `test_vad_segmenter.py`, `test_sentence_buffer.py`).
- El resto de las mejoras conocidas y deliberadamente pospuestas (reindexado incremental, confirmación asíncrona, CI, observabilidad, etc.) están en la sección "Posibles incorporaciones futuras" de `docs/ROADMAP.md` — revisar ahí antes de decidir qué atacar después de la Fase 8, no reinventar la lista acá.
- Nada de esto está pensado para multi-usuario ni exposición fuera de tu máquina — si aparece la tentación de "exponerlo en la red" o "agregar login", eso es scope creep respecto al roadmap actual.
- Los agentes de desarrollo (`.claude/agents/` en el repo) tienen la responsabilidad de cada área — si estás retomando esto después de un tiempo, es más rápido pedirle a `software-architect` que audite el estado contra `docs/ARCHITECTURE.md` que releer todo el código de cero.