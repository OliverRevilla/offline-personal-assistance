# Estructura de repositorio

```
offline-personal-assistance/
├── apps/
│   ├── orchestrator/           # Backend FastAPI: WS gateway, tool calling, sesión/estado (backend-engineer)
│   │   ├── app/
│   │   │   ├── api/            # rutas HTTP/WS
│   │   │   ├── core/           # config, logging, framing de mensajes
│   │   │   ├── stt/            # faster-whisper + Silero VAD
│   │   │   ├── tts/            # Piper-TTS + sentence buffering
│   │   │   ├── llm/            # cliente Ollama, streaming, tool-calling loop
│   │   │   ├── tools/          # ejecución real de tools contra el vault (integration-engineer)
│   │   │   └── rag/            # embeddings + cliente Qdrant (lead-ai-engineer)
│   │   ├── tests/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   └── desktop/                 # Frontend Tauri + Next.js/React (frontend-engineer)
│       ├── src/                 # app Next.js (UI, cliente WS, audio)
│       ├── src-tauri/           # shell nativo Tauri (config, permisos, build)
│       └── package.json
│
├── packages/
│   ├── rag-engine/               # lógica de chunking/indexación reutilizable (CLI, benchmarks, tests aislados)
│   ├── voice-pipeline/           # wrappers de STT/VAD/TTS reutilizables fuera de FastAPI (benchmarks de latencia)
│   └── shared-contracts/         # schemas compartidos (mensajes WS, tool schemas) — fuente única para Python/TS
│
├── docker/
│   ├── docker-compose.yml        # Ollama + Qdrant + orchestrator (CPU-only por default)
│   ├── docker-compose.gpu.yml    # override con NVIDIA Container Toolkit
│   └── ollama/                   # Modelfiles / config de modelos
│
├── prompts/
│   ├── system/                   # system prompt del asistente (versionado)
│   ├── tools/                    # schemas JSON de las tools invocables
│   └── personas/                 # variantes de tono/persona si aplica
│
├── scripts/                      # setup.sh/.ps1, pull de modelos, seed de Qdrant, benchmarks de latencia
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   ├── REPO_STRUCTURE.md
│   └── adr/                      # Architecture Decision Records
│
├── .claude/
│   └── agents/                   # subagentes de desarrollo (este documento los referencia)
│
├── vault/                        # (gitignored) vault de Obsidian local para desarrollo — nunca se commitea
├── .env.example
├── CLAUDE.md
└── README.md
```

## Convenciones
- `apps/*` son desplegables independientes (el orchestrator corre en Docker, el desktop se empaqueta con Tauri).
- `packages/*` no se despliegan solos — son librerías consumidas por `apps/*`, pensadas para poder testear/benchmarkear STT/TTS/RAG fuera del servidor WS.
- `prompts/*` son datos versionados, no código — cualquier cambio de prompt de sistema o de schema de tool es un diff legible en review, no un string embebido en `app/llm/`.
- El vault real del usuario vive fuera del repo en producción; `vault/` solo existe como punto de montaje para desarrollo local y está en `.gitignore`.
