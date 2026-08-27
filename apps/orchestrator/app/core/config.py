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


settings = Settings()
