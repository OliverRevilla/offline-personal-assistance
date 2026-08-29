# packages/voice-pipeline

Wrappers de webrtcvad, faster-whisper y Piper-TTS, reutilizables fuera de FastAPI (scripts de benchmark de latencia, pruebas manuales sin levantar todo el orchestrator). Igual que `packages/rag-engine/`, hoy la lógica real vive directamente en `apps/orchestrator/app/stt/` y `apps/orchestrator/app/tts/` porque es el único consumidor — extraerla acá solo si aparece un segundo consumidor real.

Owner: `backend-engineer`.
