import uuid

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.rag.chunking import Chunk

# Namespace fijo y arbitrario, solo para que los UUID5 sean deterministas entre corridas.
ID_NAMESPACE = uuid.UUID("f7c1b9de-2f0a-4f3a-9d7a-9f6f8a2d6b11")


def get_client() -> AsyncQdrantClient:
    return AsyncQdrantClient(url=settings.qdrant_host)


def point_id(chunk: Chunk) -> str:
    return str(uuid.uuid5(ID_NAMESPACE, f"{chunk.path}::{chunk.index}"))


async def ensure_fresh_collection(client: AsyncQdrantClient) -> None:
    """Recrea la colección desde cero. Ver docs/adr/0001-reindex-completo-vs-incremental.md para el porqué."""
    existing = await client.get_collections()
    if any(c.name == settings.qdrant_collection for c in existing.collections):
        await client.delete_collection(settings.qdrant_collection)
    await client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(size=settings.embedding_size, distance=qmodels.Distance.COSINE),
    )


async def upsert_chunks(client: AsyncQdrantClient, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    points = [
        qmodels.PointStruct(
            id=point_id(chunk),
            vector=vector,
            payload={
                "path": chunk.path,
                "title": chunk.title,
                "heading": chunk.heading,
                "text": chunk.text,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    await client.upsert(collection_name=settings.qdrant_collection, points=points)


async def search(client: AsyncQdrantClient, query_vector: list[float], top_k: int) -> list[qmodels.ScoredPoint]:
    # query_points en vez de search(): esta última está deprecada en qdrant-client >=1.10.
    response = await client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        limit=top_k,
    )
    return response.points
