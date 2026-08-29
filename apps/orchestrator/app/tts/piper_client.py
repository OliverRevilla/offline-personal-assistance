"""Cliente de Piper-TTS vía subproceso CLI (ver docs/adr/0007-piper-como-subproceso-cli.md)."""

import asyncio
import json
import shutil

from app.core.config import settings


def verify_piper_available() -> None:
    """Falla rápido al arrancar si el binario o la voz configurada no están disponibles."""
    if shutil.which(settings.piper_binary) is None:
        raise FileNotFoundError(
            f"No se encontró el binario de Piper ({settings.piper_binary!r}). "
            "Instalalo y/o ajustá PIPER_BINARY en .env — ver models/README.md."
        )
    if not settings.piper_model_path.is_file():
        raise FileNotFoundError(
            f"No se encontró el modelo de voz de Piper en {settings.piper_model_path.resolve()}. "
            "Ver models/README.md para descargarlo."
        )
    if not settings.piper_config_path.is_file():
        raise FileNotFoundError(
            f"No se encontró la config de la voz de Piper en {settings.piper_config_path.resolve()}."
        )


def load_voice_sample_rate() -> int:
    data = json.loads(settings.piper_config_path.read_text(encoding="utf-8"))
    return data["audio"]["sample_rate"]


async def synthesize(text: str) -> bytes:
    """Sintetiza `text` a PCM16 mono crudo (sin encabezado WAV). Llamada por oración, no
    por mensaje completo — cada invocación es un proceso de Piper nuevo (ver ADR 0007)."""
    process = await asyncio.create_subprocess_exec(
        settings.piper_binary,
        "--model",
        str(settings.piper_model_path),
        "--output-raw",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate(text.encode("utf-8"))

    if process.returncode != 0:
        raise RuntimeError(f"piper terminó con código {process.returncode}: {stderr.decode(errors='replace')}")

    return stdout
