# models/

Assets binarios grandes que **no se commitean** (voces de Piper, y cualquier otro modelo descargado a mano en el futuro). Esta carpeta solo trackea este README como punto de referencia.

## Piper-TTS (Fase 5)

Ver [docs/adr/0007-piper-como-subproceso-cli.md](../docs/adr/0007-piper-como-subproceso-cli.md): Piper corre como binario CLI, no como paquete pip.

Todo esto desde WSL2/Ubuntu (entorno de referencia del proyecto, ver ADR 0006).

### 1. Binario

```bash
mkdir -p ~/tools
cd ~/tools
curl -L -o piper.tar.gz https://github.com/rhasspy/piper/releases/latest/download/piper_linux_x86_64.tar.gz
tar -xzf piper.tar.gz
rm piper.tar.gz
```

Esto extrae a `~/tools/piper/` (el ejecutable `piper` + `espeak-ng-data/` que necesita al lado — no muevas el binario solo, sin esa carpeta al lado falla). Agregalo al PATH:

```bash
echo 'export PATH="$HOME/tools/piper:$PATH"' >> ~/.bashrc
source ~/.bashrc

which piper   # debería mostrar ~/tools/piper/piper
```

Si preferís no tocar el PATH, la alternativa es dejar `PIPER_BINARY=/home/<usuario>/tools/piper/piper` (ruta completa) en `apps/orchestrator/.env` en vez de `PIPER_BINARY=piper`.

### 2. Voz

Modelo `es_ES-davefx-medium` (u otra voz en español) desde [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) — necesitás los dos archivos, en `models/piper/` (esta carpeta):

```bash
mkdir -p models/piper   # desde la raíz del repo
cd models/piper

curl -L -o es_ES-davefx-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx

curl -L -o es_ES-davefx-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json

cd ../..
```

**Aviso**: esa URL de Hugging Face está escrita de memoria (siguiendo la estructura conocida del repo `rhasspy/piper-voices`), no verificada navegando. Si el `curl` de la voz da 404 o baja un HTML de error en vez del archivo real, andá a [huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium](https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_ES/davefx/medium) y descargá los dos archivos a mano desde ahí, a la misma carpeta.

Si usás otra voz, ajustá `PIPER_VOICE` en `.env` para que coincida con el nombre de archivo (sin extensión), y `PIPER_MODELS_DIR` si no la dejaste en `models/piper/`.

### 3. Smoke test (antes de tocar `uvicorn`, para aislar Piper solo)

```bash
echo "Hola, esto es una prueba" | piper --model models/piper/es_ES-davefx-medium.onnx --output_file /tmp/test.wav
```

Si genera `/tmp/test.wav` sin error, Piper está bien instalado. Recién ahí levantá el orchestrator (`uvicorn app.main:app`, desde `apps/orchestrator`) — si el binario o la voz no estuvieran disponibles, falla rápido al arrancar con un error explícito, en vez de recién al primer intento de hablar.