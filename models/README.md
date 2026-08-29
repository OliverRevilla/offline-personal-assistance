# models/

Assets binarios grandes que **no se commitean** (voces de Piper, y cualquier otro modelo descargado a mano en el futuro). Esta carpeta solo trackea este README como punto de referencia.

## Piper-TTS (Fase 5)

Ver [docs/adr/0007-piper-como-subproceso-cli.md](../docs/adr/0007-piper-como-subproceso-cli.md): Piper corre como binario CLI, no como paquete pip.

1. **Binario**: descargar el release de Piper para tu plataforma desde [github.com/rhasspy/piper/releases](https://github.com/rhasspy/piper/releases) (en WSL2/Linux: el asset `piper_linux_x86_64.tar.gz`). Descomprimir y dejar el ejecutable `piper` accesible en tu `PATH`, o ajustar `PIPER_BINARY` en `.env` a la ruta completa.

2. **Voz**: descargar el modelo `es_ES-davefx-medium` (u otra voz en español) desde [huggingface.co/rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) — necesitás los dos archivos:
   - `es_ES-davefx-medium.onnx`
   - `es_ES-davefx-medium.onnx.json`

   Ambos van en `models/piper/` (esta carpeta). Si usás otra voz, ajustá `PIPER_VOICE` en `.env` para que coincida con el nombre de archivo (sin extensión).

3. Verificar: arrancar el orchestrator (`uvicorn app.main:app`, desde `apps/orchestrator`) — si el binario o la voz no están disponibles, falla rápido al levantar con un error explícito, en vez de recién al primer intento de hablar.
