# ATENCIÓN: el entorno de desarrollo/testing de referencia de este proyecto es WSL2 + Ubuntu
# (ver docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md) — el script real a usar ahí es
# scripts/setup.sh, corrido desde una terminal de WSL2, NO este .ps1.
#
# Este .ps1 existe solo para el caso de correr TODO nativo en Windows sin WSL2 en absoluto
# (Ollama incluido). Si mezclás este script con un Ollama/orchestrator corriendo dentro de
# WSL2, vas a terminar con dos Ollama distintos escuchando en el mismo localhost:11434,
# cada uno con sus propios modelos — exactamente el incidente que documenta el ADR 0006.
#
# Setup idempotente de Fase 0: descarga los modelos de Ollama (nativo) y crea la colección
# de Qdrant. Requiere Ollama instalado en el host y `docker compose up -d qdrant` corriendo.

$OllamaLlmModel = if ($env:OLLAMA_LLM_MODEL) { $env:OLLAMA_LLM_MODEL } else { "qwen2.5:7b-instruct-q4_K_M" }
$OllamaEmbedModel = if ($env:OLLAMA_EMBED_MODEL) { $env:OLLAMA_EMBED_MODEL } else { "nomic-embed-text" }
$QdrantHost = if ($env:QDRANT_HOST) { $env:QDRANT_HOST } else { "http://localhost:6333" }
$QdrantCollection = if ($env:QDRANT_COLLECTION) { $env:QDRANT_COLLECTION } else { "obsidian-vault" }
$EmbeddingSize = if ($env:EMBEDDING_SIZE) { $env:EMBEDDING_SIZE } else { 768 }

Write-Host "==> Descargando modelo LLM: $OllamaLlmModel"
ollama pull $OllamaLlmModel

Write-Host "==> Descargando modelo de embeddings: $OllamaEmbedModel"
ollama pull $OllamaEmbedModel

Write-Host "==> Creando colección de Qdrant: $QdrantCollection (idempotente)"
$body = "{`"vectors`": {`"size`": $EmbeddingSize, `"distance`": `"Cosine`"}}"
try {
    Invoke-RestMethod -Uri "$QdrantHost/collections/$QdrantCollection" -Method Put -ContentType "application/json" -Body $body | Out-Null
    Write-Host "Colección lista."
} catch {
    Write-Host "Aviso: Qdrant respondió con error (puede que la colección ya existiera con otra config). $_"
}

Write-Host "==> Setup completo. Probar con: ollama run $OllamaLlmModel"
