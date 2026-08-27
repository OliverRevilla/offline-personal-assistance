from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:7b-instruct-q4_K_M"
    ollama_keep_alive: str = "5m"

    orchestrator_host: str = "0.0.0.0"
    orchestrator_port: int = 8000
    log_level: str = "info"


settings = Settings()
