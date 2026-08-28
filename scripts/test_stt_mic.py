"""Cliente manual de prueba para STT vía micrófono (Fase 4 del roadmap).

Uso:
    python scripts/test_stt_mic.py [ws://localhost:8000/ws/chat]

Requiere `sounddevice` y `websockets` (extra [dev] de apps/orchestrator: pip install -e ".[dev]").
Hablá al micrófono; cuando el VAD detecta que terminaste de hablar, el servidor transcribe
con faster-whisper y sigue con el turno normal (RAG + LLM + tools) como si lo hubieras escrito.
"""

import asyncio
import json
import sys

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000
AUDIO_IN_HEADER = bytes([0x01])


async def main() -> None:
    uri = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/chat"
    print(f"Conectando a {uri} ...")

    loop = asyncio.get_event_loop()
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_audio(indata, frames, time_info, status) -> None:
        if status:
            print(f"[mic warning] {status}", file=sys.stderr)
        pcm16 = np.clip(indata[:, 0] * 32767, -32768, 32767).astype(np.int16).tobytes()
        loop.call_soon_threadsafe(audio_queue.put_nowait, pcm16)

    async with websockets.connect(uri) as ws:
        print("Conectado. Hablá al micrófono (Ctrl+C para salir).\n")

        async def enviar_audio() -> None:
            while True:
                pcm = await audio_queue.get()
                await ws.send(AUDIO_IN_HEADER + pcm)

        async def recibir_mensajes() -> None:
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                tipo = msg.get("tipo")

                if tipo == "transcript_final":
                    print(f"\n[transcripción] {msg['texto']}")
                elif tipo == "turn_start":
                    print("[pensando...]")
                elif tipo == "token":
                    print(msg["texto"], end="", flush=True)
                elif tipo == "turn_end":
                    print("\n")
                elif tipo == "tool_call":
                    print(f"\n[tool] {msg['nombre']}({msg['argumentos']})")
                elif tipo == "tool_result":
                    print(f"[tool result] {msg['nombre']} -> {msg['resultado']}")
                elif tipo == "confirmacion_requerida":
                    print(f"\n[confirmación requerida] {msg['nombre']}({msg['argumentos']})")
                    respuesta = await loop.run_in_executor(None, input, "¿Aprobás? (s/n): ")
                    aprobado = respuesta.strip().lower() in ("s", "si", "sí", "y", "yes")
                    await ws.send(
                        json.dumps({"tipo": "confirmacion_respuesta", "id": msg["id"], "aprobado": aprobado})
                    )
                elif tipo == "error":
                    print(f"\n[error] {msg['mensaje']}")

        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME_SAMPLES, callback=on_audio
        ):
            await asyncio.gather(enviar_audio(), recibir_mensajes())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
