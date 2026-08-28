import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from app.core.config import settings


def load_system_prompt() -> str:
    path = Path(settings.system_prompt_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"No se encontró el system prompt en {path.resolve()} "
            "(configurable vía SYSTEM_PROMPT_PATH, ver .env.example)."
        )
    return path.read_text(encoding="utf-8").strip()


SYSTEM_PROMPT = load_system_prompt()


async def stream_chat(messages: list[dict], tools: list[dict] | None = None) -> AsyncIterator[dict]:
    """Llama a Ollama /api/chat en modo streaming.

    Cede eventos `{"type": "token", "content": str}` a medida que se genera texto, y
    `{"type": "tool_calls", "calls": [...]}` si el modelo decide invocar una o más tools
    (formato nativo de Ollama, compatible con el de OpenAI).
    """
    payload = {
        "model": settings.ollama_llm_model,
        "messages": messages,
        "stream": True,
        "keep_alive": settings.ollama_keep_alive,
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=None) as client:
        async with client.stream("POST", "/api/chat", json=payload) as response:
            if response.is_error:
                # httpx.HTTPStatusError no incluye el cuerpo de la respuesta en su mensaje,
                # y ahí es donde Ollama explica qué falló de verdad (ej. "model does not
                # support tools") — sin esto quedamos ciegos a la razón real del error.
                body = (await response.aread()).decode(errors="replace")
                raise RuntimeError(
                    f"Ollama respondió {response.status_code} en POST {settings.ollama_host}/api/chat: {body}"
                )
            async for line in response.aiter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                message = chunk.get("message", {})

                content = message.get("content", "")
                if content:
                    yield {"type": "token", "content": content}

                tool_calls = message.get("tool_calls")
                if tool_calls:
                    yield {"type": "tool_calls", "calls": tool_calls}

                if chunk.get("done"):
                    break
