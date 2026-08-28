# docker

Dos escenarios, dos combinaciones de archivos — no son alternativas de un mismo compose, son composables:

| Archivo | Rol |
|---|---|
| `docker-compose.yml` | Base: Qdrant + orchestrator. **Asume que Ollama ya corre nativo en el host** (caso por defecto de este repo). |
| `docker-compose.ollama.yml` | Override que agrega Ollama containerizado, para quien NO tenga Ollama instalado nativo. |
| `docker-compose.gpu.yml` | Override que le pasa la GPU al Ollama containerizado (solo tiene sentido junto con `docker-compose.ollama.yml`). |

Containerizar Ollama o no **no afecta performance** (los contenedores Linux son namespaces, no VMs, y el passthrough de GPU vía NVIDIA Container Toolkit es directo al device) — la razón para preferir Ollama nativo, si ya lo tenés, es evitar terminar con dos Ollama distintos escuchando en el mismo puerto (ver [docs/adr/0006](../docs/adr/0006-estandarizar-entorno-a-wsl2-ubuntu.md), el incidente que motivó esta separación en dos archivos).

Owner: `devops-engineer`.

## Escenario A (por defecto): Ollama ya instalado en el host

Todo esto desde una terminal de **WSL2** (entorno de referencia del proyecto, ver ADR 0006), no desde PowerShell:

```bash
cp ../.env.example ../.env   # ajustar si hace falta

docker compose -f docker-compose.yml up -d qdrant

# Descargar modelos (nativo) e inicializar la colección de Qdrant:
../scripts/setup.sh

# Verificar que el LLM responde (usando tu instalación nativa, con o sin GPU según cómo
# la tengas configurada vos a nivel de sistema/drivers):
ollama run qwen2.5:7b-instruct-q4_K_M
```

El servicio `orchestrator` también está definido en `docker-compose.yml` (build context = raíz del repo, no `apps/orchestrator/`, porque la imagen también necesita `/prompts`) y ya viene configurado para resolver Ollama en el host vía `host.docker.internal` — pero durante desarrollo activo suele ser más rápido correrlo fuera de Docker directamente (ver [apps/orchestrator/README.md](../apps/orchestrator/README.md)).

## Escenario B: todo containerizado (sin Ollama nativo)

```bash
cp ../.env.example ../.env

# CPU-only:
docker compose -f docker-compose.yml -f docker-compose.ollama.yml up -d ollama qdrant

# Con GPU (NVIDIA Container Toolkit configurado dentro de WSL2):
docker compose -f docker-compose.yml -f docker-compose.ollama.yml -f docker-compose.gpu.yml up -d ollama qdrant

# Descargar modelos e inicializar la colección de Qdrant — en scripts/setup.sh, comentar las
# líneas de `ollama pull` nativo y usar la alternativa docker exec que ese mismo script deja documentada:
../scripts/setup.sh

# Verificar que el LLM responde usando GPU:
docker compose -f docker-compose.yml -f docker-compose.ollama.yml exec ollama ollama run qwen2.5:7b-instruct-q4_K_M
```

No mezclar los dos escenarios (por ejemplo, levantar `docker-compose.ollama.yml` mientras además tenés Ollama nativo corriendo) — eso es exactamente el incidente del ADR 0006.

## Vault

Montaje del vault (Fase 2-3): el contenedor de `orchestrator` monta `../vault` (el vault de prueba del repo) como `/vault`, en lectura/escritura — desde la Fase 3 el asistente puede crear/editar notas ahí (tool calling), no solo leerlas para RAG. Para apuntar a un vault real fuera del repo, hay que sobreescribir ese volumen en un `docker-compose.override.yml` local (no versionado) apuntando a la ruta real.
