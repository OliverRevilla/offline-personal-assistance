from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.rag.embeddings import embed_text
from app.rag.store import search


async def retrieve(client: AsyncQdrantClient, query: str, top_k: int | None = None) -> list[qmodels.ScoredPoint]:
    vector = await embed_text(query)
    return await search(client, vector, top_k=top_k or settings.rag_top_k)


def format_context(results: list[qmodels.ScoredPoint]) -> str:
    """Arma el bloque de contexto a inyectar en el prompt, citando la nota de origen de cada chunk."""
    if not results:
        return ""

    blocks = []
    for r in results:
        payload = r.payload or {}
        blocks.append(
            f"### {payload.get('title')} — {payload.get('heading')} (`{payload.get('path')}`)\n"
            f"{payload.get('text')}"
        )
    return "\n\n".join(blocks)
