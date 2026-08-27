"""Cliente manual de prueba para el WS de chat (Fases 1-3 del roadmap).

Uso:
    python scripts/test_ws_chat.py [ws://localhost:8000/ws/chat]

Requiere el paquete `websockets` (incluido en el extra [dev] de apps/orchestrator).
"""

import asyncio
import json
import sys

import websockets


async def main() -> None:
    uri = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000/ws/chat"
    print(f"Conectando a {uri} ...")

    async with websockets.connect(uri) as ws:
        print("Conectado. Escribe un mensaje y presiona Enter (Ctrl+C para salir).\n")
        loop = asyncio.get_event_loop()

        while True:
            texto = await loop.run_in_executor(None, input, "> ")
            if not texto.strip():
                continue

            await ws.send(json.dumps({"tipo": "user_message", "texto": texto}))

            while True:
                raw = await ws.recv()
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
