# Roadmap — MVI (Mínimo Viable Incremental)

Cada fase cierra con un commit/tag independiente y un criterio de "hecho" verificable sin depender de la fase siguiente. No se avanza de fase sin cumplir el criterio de la anterior.

## Fase 0 — Bootstrap & Infra
**Owner:** devops-engineer (revisa software-architect)
- Estructura de carpetas del repo (ver `docs/REPO_STRUCTURE.md` / raíz del proyecto).
- `docker-compose.yml` (Qdrant + orchestrator, asume Ollama nativo en el host — ver [ADR 0006](adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md)) + `docker-compose.ollama.yml` (override: Ollama containerizado, para quien no lo tenga nativo) + `docker-compose.gpu.yml` (override sobre el anterior: NVIDIA Container Toolkit).
- Script de setup: pull de modelo Ollama (LLM + `nomic-embed-text`), init de colección Qdrant.
- **Hecho cuando:** `docker compose up` levanta Qdrant, y `ollama run <modelo>` responde (nativo, o vía `docker-compose.ollama.yml` si corresponde) usando GPU si aplica.

## Fase 1 — Backend esqueleto + chat de texto
**Owner:** backend-engineer + lead-ai-engineer
- FastAPI con endpoint WS mínimo: recibe texto plano, llama a Ollama, devuelve stream de tokens por WS. Sin voz, sin RAG.
- **Hecho cuando:** un script/cliente de prueba puede chatear en streaming con el LLM local vía WS.

## Fase 2 — RAG sobre el vault
**Owner:** lead-ai-engineer
- Pipeline de indexación del vault (chunking → embeddings → Qdrant).
- Inyección de contexto RAG en el prompt.
- **Hecho cuando:** una pregunta cuya respuesta está en una nota real del vault es respondida citando esa nota.

## Fase 3 — Tool calling
**Owner:** integration-engineer + lead-ai-engineer
- Schemas de `buscar_nota`, `crear_nota`, `actualizar_nota`, `listar_tareas`.
- Ejecución sandboxeada al vault, con confirmación explícita para operaciones destructivas.
- **Hecho cuando:** el asistente crea/edita una nota real en el vault a pedido del usuario, y el cambio es auditable.

## Fase 4 — Voz: oídos (STT + VAD)
**Owner:** backend-engineer
- webrtcvad sobre el stream entrante + faster-whisper (CPU) para transcripción (ver [ADR 0003](adr/0003-webrtcvad-en-vez-de-silero-vad.md) sobre por qué no Silero VAD).
- **Hecho cuando:** hablar por micrófono (vía script de prueba) produce una transcripción visible en tiempo real, sin frontend final.

## Fase 5 — Voz: boca (TTS)
**Owner:** backend-engineer + lead-ai-engineer (sentence-buffering)
- Piper-TTS integrado, troceo del stream del LLM por frase, envío de audio incremental por WS.
- **Hecho cuando:** el pipeline texto→voz funciona de punta a punta vía script de prueba, con audio empezando antes de que el LLM termine de generar el mensaje completo.

## Fase 6 — Frontend Tauri + Next.js
**Owner:** frontend-engineer + integration-engineer
- App de escritorio: captura de mic, reproducción de audio en streaming, UI de conversación, cliente WS.
- **Hecho cuando:** existe una demo end-to-end real — hablarle a la app y que responda con voz, con RAG y tool calling funcionando.

## Fase 7 — Hardening, observabilidad y gestión de recursos
**Owner:** devops-engineer (revisa software-architect)
- Manejo de VRAM (keep_alive de Ollama, medición de pico con LLM+STT simultáneos), reconexión de WS, logging estructurado, tests de integración end-to-end (integration-engineer).
- **Hecho cuando:** el sistema sobrevive a una desconexión de WS a mitad de turno y hay métricas básicas de latencia (TTFB del LLM, latencia STT, latencia TTS).

## Fase 8 — Empaquetado y distribución
**Owner:** devops-engineer
- Instalador Tauri (Windows/Linux), `docker-compose` de producción, guía de instalación para usuario final.
- **Hecho cuando:** alguien sin el entorno de desarrollo puede instalar y correr el asistente completo siguiendo solo la guía.

---

**Nota de alcance:** ninguna fase agrega orquestación multi-usuario, autenticación remota, ni despliegue en la nube — el sistema es mono-usuario, local y offline por diseño. Si en algún punto se propone algo de eso, es una señal de scope creep y debe pasar por un ADR (`docs/adr/`) antes de aceptarse.

## Posibles incorporaciones futuras (no planificadas, no forman parte de ninguna fase)

Ideas anotadas para evaluar más adelante, deliberadamente fuera del roadmap actual hasta que se decidan con su propio ADR:

- **Conexión a servidores MCP externos**: el orchestrator (no el LLM en sí) actuaría como cliente MCP, sumando las tools que exponga un servidor MCP al mismo array de schemas que hoy arma `app/tools/registry.py` para `buscar_nota`/`crear_nota`/etc. Tensiona directamente con la nota de alcance de arriba (offline por diseño): requeriría que sea una fuente de tools opcional/togglable, con degradación explícita cuando no hay red, y una decisión consciente de qué datos del vault/la conversación pueden salir de la máquina hacia ese servidor. No implementar sin un ADR que resuelva esos tres puntos primero.

### RAG
- **Reindexado incremental del vault** en vez de full reindex (ver [ADR 0001](adr/0001-reindex-completo-vs-incremental.md)), idealmente junto con un **watcher de archivos** que dispare el reindex solo cuando cambia algo — hoy hay que correrlo a mano después de cada cambio. No implementar sin evidencia real de que el reindex completo se volvió lento.

### Tool calling
- **Confirmación de tools destructivas como cola asíncrona** en vez de bloquear el turno de WS completo (ver [ADR 0002](adr/0002-confirmacion-sincrona-para-tools-destructivas.md), opción descartada) — reconsiderar si se agrega interacción por voz simultánea a la de texto (fases 5-6), o si aparecen operaciones destructivas de larga duración.
- ~~**Manejo robusto de un frame de audio llegando mientras hay una confirmación pendiente**~~ — resuelto en la Fase 7: `pedir_confirmacion` ahora usa el `receive()` genérico y descarta (con log) cualquier frame binario que llegue mientras espera, en vez de romper el turno.
- **Tool para borrar/archivar una nota**: no está en el set mínimo de la Fase 3. Si se agrega, es al menos tan destructiva como `actualizar_nota` y necesita el mismo flujo de confirmación (o uno más estricto).

### Voz
- **Transcripción parcial en streaming** (hoy solo se manda `transcript_final` una vez que el VAD decide que el turno de habla terminó) — mejoraría la UX percibida cuando exista frontend (Fase 6), no hace falta para validar el pipeline con un script de prueba.
- **Mejorar la precisión de escucha (VAD + STT)**: probado en Fase 4, el pipeline funciona ("medianamente correcto" según feedback real de uso) pero hay margen de mejora en qué tan bien detecta inicio/fin de turno y en la fidelidad de la transcripción. Candidatos a probar, en orden de costo creciente: ajustar `VAD_AGGRESSIVENESS`/`VAD_WINDOW_MS`, subir `WHISPER_MODEL_SIZE` de `base` a `small`/`medium` (más preciso, más lento en CPU), y recién como último recurso reconsiderar Silero VAD en vez de `webrtcvad` (ver [ADR 0003](adr/0003-webrtcvad-en-vez-de-silero-vad.md) — ahora sí con evidencia real de que `webrtcvad` se queda corto, no solo hipotética). Programado para revisarse después de la Fase 7, no bloquea las fases siguientes.

### Infra y calidad
- **CI** (lint + tests automáticos en cada push): hoy `pytest` se corre a mano. Sigue sin implementar — la Fase 7 agregó los tests de integración end-to-end (`test_integration_turno.py`) y las métricas, pero no un pipeline de CI que los corra solo.
- ~~**Observabilidad real** (métricas de latencia expuestas, no solo logs)~~ — resuelto en la Fase 7: `GET /metrics` (TTFB del LLM, latencia STT, latencia TTS) + logging estructurado en JSON. Sin Prometheus/Grafana, como estaba decidido.
- **Persistencia de la conversación entre reinicios del backend**: hoy `history` vive en memoria por conexión WS — un restart del servidor o una reconexión pierden el contexto de la sesión anterior. La Fase 7 agregó reconexión automática del lado del cliente, pero no persistencia del historial — el usuario ve un aviso de que el contexto se perdió, no se lo recupera.

### Contratos compartidos
- **`packages/rag-engine/` y `packages/voice-pipeline/` siguen vacíos a propósito** — se justifican recién cuando exista un segundo consumidor real. `packages/shared-contracts/` también sigue vacío, pero esa decisión ya está tomada (no una pendiente): la Fase 6 llegó y se decidió duplicar el contrato a mano en vez de generarlo — ver [ADR 0008](adr/0008-frontend-nativo-windows-y-stack-tauri.md) y `packages/shared-contracts/README.md`.
