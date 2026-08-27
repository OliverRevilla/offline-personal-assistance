# docker

`docker-compose.yml` (Ollama + Qdrant + orchestrator) y `docker-compose.gpu.yml` (override con NVIDIA Container Toolkit para pasar la GPU al contenedor de Ollama).

Owner: `devops-engineer`.

## Cómo levantar (Fase 0 del roadmap)

```bash
cp ../.env.example ../.env   # ajustar si hace falta

# CPU-only (sin GPU, o para probar el compose antes de configurar NVIDIA Container Toolkit):
docker compose -f docker-compose.yml up -d ollama qdrant

# Con GPU (Linux/WSL2 con NVIDIA Container Toolkit instalado):
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d ollama qdrant

# Descargar modelos e inicializar la colección de Qdrant:
../scripts/setup.sh     # o ../scripts/setup.ps1 en Windows

# Verificar que el LLM responde usando GPU:
docker compose -f docker-compose.yml exec ollama ollama run qwen2.5:7b-instruct-q4_K_M
```

El servicio `orchestrator` (Fase 1) también está definido en `docker-compose.yml`, pero durante desarrollo activo suele ser más rápido correrlo fuera de Docker (ver [apps/orchestrator/README.md](../apps/orchestrator/README.md)).
