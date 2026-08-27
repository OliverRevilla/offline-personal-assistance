import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings

# Placeholder de Fase 1 (sin RAG, sin tools todavía).
# El system prompt "real" del asistente vivirá versionado en /prompts (Fase 2, lead-ai-engineer).
SYSTEM_PROMPT = "Eres un asistente útil, conciso y que responde en español."


async def stream_chat(messages: list[dict]) -> AsyncIterator[str]:
    """Llama a Ollama /api/chat en modo streaming y va cediendo el contenido token a token."""
    payload = {
        "model": settings.ollama_llm_model,
        "messages": messages,
        "stream": True,
        "keep_alive": settings.ollama_keep_alive,
    }
    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=None) as client:
        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield content
                if chunk.get("done"):
                    break
