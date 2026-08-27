import httpx

from app.core.config import settings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embebe uno o más textos con el modelo de embeddings servido por Ollama (/api/embed)."""
    if not texts:
        return []
    async with httpx.AsyncClient(base_url=settings.ollama_host, timeout=None) as client:
        response = await client.post(
            "/api/embed",
            json={"model": settings.ollama_embed_model, "input": texts},
        )
        response.raise_for_status()
        return response.json()["embeddings"]


async def embed_text(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
