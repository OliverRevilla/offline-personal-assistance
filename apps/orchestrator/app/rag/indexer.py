"""Reindexado completo del vault.

Estrategia: full reindex (drop & rebuild de la colección) en cada corrida, no incremental.
Es la opción correcta y simple para el tamaño de un vault personal; ver
docs/adr/0001-reindex-completo-vs-incremental.md antes de cambiarla.

Uso manual: `python -m app.rag.indexer` (desde apps/orchestrator, con el venv activado).
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.rag.chunking import Chunk, chunk_file, iter_markdown_files
from app.rag.embeddings import embed_texts
from app.rag.store import ensure_fresh_collection, get_client, upsert_chunks

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


async def reindex_vault() -> int:
    vault_path = Path(settings.vault_path).resolve()
    if not vault_path.is_dir():
        raise FileNotFoundError(f"VAULT_PATH no existe o no es un directorio: {vault_path}")

    chunks: list[Chunk] = []
    for md_file in iter_markdown_files(vault_path):
        chunks.extend(chunk_file(md_file, vault_path))

    client = get_client()
    try:
        await ensure_fresh_collection(client)
        for i in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[i : i + EMBED_BATCH_SIZE]
            vectors = await embed_texts([c.text for c in batch])
            await upsert_chunks(client, batch, vectors)
            logger.info("Indexados %d/%d chunks", min(i + EMBED_BATCH_SIZE, len(chunks)), len(chunks))
    finally:
        await client.close()

    return len(chunks)


async def main() -> None:
    logging.basicConfig(level="INFO")
    total = await reindex_vault()
    print(f"Reindexado completo: {total} chunks indexados desde {Path(settings.vault_path).resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
