# Roadmap — MVI (Mínimo Viable Incremental)

Cada fase cierra con un commit/tag independiente y un criterio de "hecho" verificable sin depender de la fase siguiente. No se avanza de fase sin cumplir el criterio de la anterior.

## Fase 0 — Bootstrap & Infra
**Owner:** devops-engineer (revisa software-architect)
- Estructura de carpetas del repo (ver `docs/REPO_STRUCTURE.md` / raíz del proyecto).
- `docker-compose.yml` (Ollama + Qdrant) + `docker-compose.gpu.yml` (override NVIDIA Container Toolkit).
- Script de setup: pull de modelo Ollama (LLM + `nomic-embed-text`), init de colección Qdrant.
- **Hecho cuando:** `docker compose up` levanta Ollama + Qdrant, y `ollama run <modelo>` responde usando GPU.

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
- Silero VAD sobre el stream entrante + faster-whisper (CPU) para transcripción.
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
