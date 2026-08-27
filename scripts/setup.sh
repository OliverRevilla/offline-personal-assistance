#!/usr/bin/env bash
# Setup idempotente de Fase 0: descarga los modelos de Ollama y crea la colección de Qdrant.
# Requiere que `docker compose up -d` (servicios ollama + qdrant) ya esté corriendo.
set -euo pipefail

COMPOSE_FILE="$(dirname "$0")/../docker/docker-compose.yml"

OLLAMA_LLM_MODEL="${OLLAMA_LLM_MODEL:-qwen2.5:7b-instruct-q4_K_M}"
OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"
QDRANT_HOST="${QDRANT_HOST:-http://localhost:6333}"
QDRANT_COLLECTION="${QDRANT_COLLECTION:-obsidian-vault}"
EMBEDDING_SIZE="${EMBEDDING_SIZE:-768}" # dimensión de nomic-embed-text

echo "==> Descargando modelo LLM: ${OLLAMA_LLM_MODEL}"
docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama pull "${OLLAMA_LLM_MODEL}"

echo "==> Descargando modelo de embeddings: ${OLLAMA_EMBED_MODEL}"
docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama pull "${OLLAMA_EMBED_MODEL}"

echo "==> Creando colección de Qdrant: ${QDRANT_COLLECTION} (idempotente)"
http_code=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "${QDRANT_HOST}/collections/${QDRANT_COLLECTION}" \
  -H "Content-Type: application/json" \
  -d "{\"vectors\": {\"size\": ${EMBEDDING_SIZE}, \"distance\": \"Cosine\"}}")

if [ "${http_code}" = "200" ]; then
  echo "Colección lista."
else
  echo "Aviso: Qdrant respondió HTTP ${http_code} (puede que la colección ya existiera con otra config)."
fi

echo "==> Setup completo. Probar con: docker compose -f ${COMPOSE_FILE} exec ollama ollama run ${OLLAMA_LLM_MODEL}"
