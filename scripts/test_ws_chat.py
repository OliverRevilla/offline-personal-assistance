"""Cliente manual de prueba para el WS de chat (Fases 1-5 del roadmap).

Uso:
    python scripts/test_ws_chat.py [ws://localhost:8000/ws/chat]

Requiere `websockets`, `sounddevice` y `numpy` (incluidos en el extra [dev] de apps/orchestrator).
Reproduce el audio de respuesta (TTS) a medida que llega, oración por oración.
"""

import asyncio
import json
import queue
import sys

import numpy as np
import sounddevice as sd
import websockets

AUDIO_OUT_HEADER = 0x02


def crear_reproductor(sample_rate: int) -> tuple[sd.OutputStream, "queue.Queue[np.ndarray]"]:
    """Arma un OutputStream que reproduce, en orden, los chunks de audio que se le encolen."""
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

    async with websockets.connect(uri) as ws:
        primer_mensaje = json.loads(await ws.recv())
        if primer_mensaje.get("tipo") != "audio_meta":
            raise RuntimeError(f"Se esperaba 'audio_meta' como primer mensaje, llegó: {primer_mensaje}")

        sample_rate = primer_mensaje["sample_rate"]
        stream, audio_queue = crear_reproductor(sample_rate)
        stream.start()

        print(f"Conectado (audio a {sample_rate}Hz). Escribe un mensaje y presiona Enter (Ctrl+C para salir).\n")
        loop = asyncio.get_event_loop()

        while True:
            texto = await loop.run_in_executor(None, input, "> ")
            if not texto.strip():
                continue

            await ws.send(json.dumps({"tipo": "user_message", "texto": texto}))

            while True:
                raw = await ws.recv()

                if isinstance(raw, bytes):
                    if not raw or raw[0] != AUDIO_OUT_HEADER:
                        continue
                    pcm16 = np.frombuffer(raw[1:], dtype=np.int16).astype(np.float32) / 32768.0
                    audio_queue.put(pcm16)
                    continue

                msg = json.loads(raw)
                tipo = msg.get("tipo")

                if tipo == "turn_start":
                    continue
                if tipo == "token":
                    print(msg["texto"], end="", flush=True)
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
                elif tipo == "turn_end":
                    print("\n")
                    break
                elif tipo == "error":
                    print(f"\n[error] {msg['mensaje']}\n")
                    break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
