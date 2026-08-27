# Setup idempotente de Fase 0: descarga los modelos de Ollama y crea la colección de Qdrant.
# Requiere que `docker compose up -d` (servicios ollama + qdrant) ya esté corriendo.

$ComposeFile = Join-Path $PSScriptRoot "..\docker\docker-compose.yml"

$OllamaLlmModel = if ($env:OLLAMA_LLM_MODEL) { $env:OLLAMA_LLM_MODEL } else { "qwen2.5:7b-instruct-q4_K_M" }
$OllamaEmbedModel = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { "nomic-embed-text" }
$QdrantHost = if ($env:QDRANT_HOST) { $env:QDRANT_HOST } else { "http://localhost:6333" }
$QdrantCollection = if ($env:QDRANT_COLLECTION) { $env:QDRANT_COLLECTION } else { "obsidian-vault" }
$EmbeddingSize = if ($env:EMBEDDING_SIZE) { $env:EMBEDDING_SIZE } else { 768 }

Write-Host "==> Descargando modelo LLM: $OllamaLlmModel"
docker compose -f $ComposeFile exec -T ollama ollama pull $OllamaLlmModel

Write-Host "==> Descargando modelo de embeddings: $OllamaEmbedModel"
docker compose -f $ComposeFile exec -T ollama ollama pull $OllamaEmbedModel

Write-Host "==> Creando colección de Qdrant: $QdrantCollection (idempotente)"
$body = "{`"vectors`": {`"size`": $EmbeddingSize, `"distance`": `"Cosine`"}}"
try {
    Invoke-RestMethod -Uri "$QdrantHost/collections/$QdrantCollection" -Method Put -ContentType "application/json" -Body $body | Out-Null
    Write-Host "Colección lista."
} catch {
    Write-Host "Aviso: Qdrant respondió con error (puede que la colección ya existiera con otra config). $_"
}

Write-Host "==> Setup completo. Probar con: docker compose -f $ComposeFile exec ollama ollama run $OllamaLlmModel"
