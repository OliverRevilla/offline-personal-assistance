# 0001 — Reindexado completo vs. incremental del vault

## Contexto
El pipeline de RAG (Fase 2) necesita mantener sincronizada la colección de Qdrant con el estado real de los archivos `.md` del vault. Un enfoque incremental (detectar qué archivos cambiaron, borrar solo sus chunks viejos, re-embeber solo lo nuevo) es más eficiente pero requiere trackear qué está indexado (manifiesto de hashes por archivo) y manejar correctamente los archivos borrados.

## Opciones consideradas
1. **Incremental**: manifiesto de hashes por archivo, diffing en cada corrida, borrado selectivo por filtro de payload en Qdrant.
2. **Full reindex**: en cada corrida, se borra y se recrea la colección completa desde cero, re-embebiendo todos los archivos del vault.

## Decisión
Full reindex (opción 2), implementado en `apps/orchestrator/app/rag/indexer.py`.

## Consecuencias
- Simplicidad: no hay estado de indexación que pueda desincronizarse del contenido real del vault ni casos borde de archivos eliminados.
- Costo: cada reindexado re-embebe todo el vault, no solo lo que cambió. Para un vault personal (cientos/pocos miles de notas) esto es aceptable en tiempo y no requiere GPU (el modelo de embeddings es liviano).
- Si el vault crece lo suficiente como para que el reindex completo se vuelva lento (varios minutos+), esto debe revisarse — en ese punto sí se justifica un manifiesto incremental. No implementarlo antes de que el problema sea real.
