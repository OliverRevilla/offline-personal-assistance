# NOTA: build context = raíz del repo (ver docker/docker-compose.yml), no apps/orchestrator,
# porque también se copia /prompts dentro de la imagen.

FROM python:3.11-slim

WORKDIR /app

COPY apps/orchestrator/pyproject.toml ./
COPY apps/orchestrator/app ./app
COPY prompts ./prompts

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
