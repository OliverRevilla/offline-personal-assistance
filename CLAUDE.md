# offline-personal-assistance

Asistente de voz personal, 100% offline, sobre hardware de consumo (GPU NVIDIA 8GB VRAM, 16GB RAM). Ver contexto completo en:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — flujo de datos, contratos entre servicios, presupuesto de VRAM.
- [docs/ROADMAP.md](docs/ROADMAP.md) — fases del roadmap (MVI) y criterio de "hecho" de cada una.
- [docs/REPO_STRUCTURE.md](docs/REPO_STRUCTURE.md) — estructura de carpetas y convenciones.

## Stack (decisiones cerradas, ver ADRs en `docs/adr/` para reabrir)
LLM: Ollama (Qwen2.5-7B/Llama3.1-8B, Q4/Q5) · RAG: Qdrant + `nomic-embed-text` sobre un vault de Obsidian · STT: faster-whisper + Silero VAD (CPU) · TTS: Piper-TTS (CPU) · Backend: FastAPI (WS + tool calling) · Frontend: Tauri + Next.js/React · Infra: Docker + NVIDIA Container Toolkit.

## Subagentes de desarrollo (`.claude/agents/`)
| Agente | Foco |
|---|---|
| `software-architect` | Diseño cross-subsistema, ADRs, presupuesto de VRAM/RAM |
| `lead-ai-engineer` | Ollama, RAG (Qdrant/embeddings), prompts, tool schemas |
| `backend-engineer` | FastAPI orchestrator, WS, STT, TTS, sentence-buffering |
| `frontend-engineer` | App Tauri + Next.js, captura/reproducción de audio, UI |
| `devops-engineer` | Docker, NVIDIA Container Toolkit, CI, empaquetado, observabilidad |
| `integration-engineer` | Ejecución de tools contra el vault, tests end-to-end, contratos cross-servicio |

Restricción de arquitectura que todos los agentes deben respetar: **solo el LLM usa GPU de forma sostenida**; STT/TTS/embeddings corren en CPU para no competir por los 8GB de VRAM. Cualquier cambio a esto requiere un ADR revisado por `software-architect`.
