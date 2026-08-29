from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_keep_alive: str = "5m"

    qdrant_host: str = "http://localhost:6333"
    qdrant_collection: str = "obsidian-vault"
    embedding_size: int = 768  # dimensión de nomic-embed-text

    # Rutas relativas asumiendo CWD = apps/orchestrator (ver README) tanto en local como en Docker
    # (en Docker, docker-compose las sobreescribe con rutas absolutas dentro del contenedor).
    vault_path: str = "../../vault"
    system_prompt_path: str = "../../prompts/system/assistant.md"
    tools_schema_dir: str = "../../prompts/tools"
    rag_top_k: int = 4

    orchestrator_host: str = "0.0.0.0"
    orchestrator_port: int = 8000
    log_level: str = "info"

    # --- STT (Fase 4) ---
    whisper_model_size: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"  # el más rápido en CPU; ver faster-whisper docs
    whisper_language: str = "es"

    # webrtcvad: 0 (menos agresivo filtrando no-voz) a 3 (más agresivo)
    vad_aggressiveness: int = 2
    vad_window_ms: int = 300  # ventana (ring buffer) usada para decidir inicio/fin de turno

    # --- TTS (Fase 5) — Piper como subproceso CLI, ver ADR 0007 ---
    piper_binary: str = "piper"  # nombre en PATH, o ruta absoluta/relativa al ejecutable
    piper_models_dir: str = "../../models/piper"
    piper_voice: str = "es_ES-davefx-medium"  # requiere <voz>.onnx + <voz>.onnx.json en piper_models_dir

    @property
    def piper_model_path(self) -> Path:
        return Path(self.piper_models_dir) / f"{self.piper_voice}.onnx"

    @property
    def piper_config_path(self) -> Path:
        return Path(self.piper_models_dir) / f"{self.piper_voice}.onnx.json"


settings = Settings()
