"""Cliente manual de prueba para STT + TTS vía micrófono (Fases 4-5 del roadmap).

Uso:
    python scripts/test_stt_mic.py [ws://localhost:8000/ws/chat]

Requiere `sounddevice`, `websockets` y `numpy` (extra [dev] de apps/orchestrator).
Hablá al micrófono; cuando el VAD detecta que terminaste de hablar, el servidor transcribe
con faster-whisper, sigue con el turno normal (RAG + LLM + tools), y esta vez también vas a
escuchar la respuesta sintetizada con Piper-TTS a medida que llega.
"""

import asyncio
import json
import queue
import sys

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE_IN = 16000
FRAME_MS = 30
FRAME_SAMPLES = SAMPLE_RATE_IN * FRAME_MS // 1000
AUDIO_IN_HEADER = bytes([0x01])
AUDIO_OUT_HEADER = 0x02


def crear_reproductor(sample_rate: int) -> tuple[sd.OutputStream, "queue.Queue[np.ndarray]"]:
    cola: queue.Queue[np.ndarray] = queue.Queue()
    pendiente = np.zeros(0, dtype=np.float32)

    def callback(outdata, frames, time_info, status) -> None:
        nonlocal pendiente
        if status:
            print(f"[audio warning] {status}", file=sys.stderr)

        listo = 0
        while listo < frames:
            if pendiente.size == 0:
                try:
                    pendiente = cola.get_nowait()
                except queue.Empty:
                    outdata[listo:, 0] = 0.0
                    return
            usar = min(frames - listo, pendiente.size)
            outdata[listo : listo + usar, 0] = pendiente[:usar]
            pendiente = pendiente[usar:]
            listo += usar

    stream = sd.OutputStream(samplerate=sample_rate, channels=1, dtype="float32", callback=callback)
    return stream, cola


async def main() -> None:
    uri = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/chat"
    print(f"Conectando a {uri} ...")

    loop = asyncio.get_event_loop()
    mic_queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_mic_audio(indata, frames, time_info, status) -> None:
        if status:
            print(f"[mic warning] {status}", file=sys.stderr)
        pcm16 = np.clip(indata[:, 0] * 32767, -32768, 32767).astype(np.int16).tobytes()
        loop.call_soon_threadsafe(mic_queue.put_nowait, pcm16)

    async with websockets.connect(uri) as ws:
        primer_mensaje = json.loads(await ws.recv())
        if primer_mensaje.get("tipo") != "audio_meta":
            raise RuntimeError(f"Se esperaba 'audio_meta' como primer mensaje, llegó: {primer_mensaje}")

        playback_stream, playback_queue = crear_reproductor(primer_mensaje["sample_rate"])
        playback_stream.start()

        print("Conectado. Hablá al micrófono (Ctrl+C para salir).\n")

        async def enviar_audio() -> None:
            while True:
                pcm = await mic_queue.get()
                await ws.send(AUDIO_IN_HEADER + pcm)

        async def recibir_mensajes() -> None:
            while True:
                raw = await ws.recv()

                if isinstance(raw, bytes):
                    if not raw or raw[0] != AUDIO_OUT_HEADER:
                        continue
                    pcm16 = np.frombuffer(raw[1:], dtype=np.int16).astype(np.float32) / 32768.0
                    playback_queue.put(pcm16)
                    continue

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
            samplerate=SAMPLE_RATE_IN, channels=1, dtype="float32", blocksize=FRAME_SAMPLES, callback=on_mic_audio
        ):
            await asyncio.gather(enviar_audio(), recibir_mensajes())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
