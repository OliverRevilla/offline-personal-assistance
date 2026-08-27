import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.llm.ollama_client import SYSTEM_PROMPT, stream_chat

logger = logging.getLogger(__name__)
router = APIRouter()

# Protocolo de Fase 1 (solo texto, sin audio ni tools todavía — ver docs/ARCHITECTURE.md):
#   cliente -> servidor: {"tipo": "user_message", "texto": str}
#   servidor -> cliente: {"tipo": "turn_start"}
#                        {"tipo": "token", "texto": str}          (uno por cada fragmento generado)
#                        {"tipo": "turn_end"}
#                        {"tipo": "error", "mensaje": str}


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("tipo") != "user_message":
                await websocket.send_json(
                    {"tipo": "error", "mensaje": f"tipo de mensaje no soportado: {data.get('tipo')!r}"}
                )
                continue

            texto = (data.get("texto") or "").strip()
            if not texto:
                continue

            history.append({"role": "user", "content": texto})
            await websocket.send_json({"tipo": "turn_start"})

            respuesta = ""
            try:
                async for token in stream_chat(history):
                    respuesta += token
                    await websocket.send_json({"tipo": "token", "texto": token})
            except Exception as exc:  # noqa: BLE001 - se reporta al cliente y se sigue la sesión
                logger.exception("Fallo al generar respuesta del LLM")
                await websocket.send_json({"tipo": "error", "mensaje": str(exc)})
                history.pop()  # el turno de usuario no obtuvo respuesta válida, no lo dejamos en el historial
                continue

            history.append({"role": "assistant", "content": respuesta})
            await websocket.send_json({"tipo": "turn_end"})

    except WebSocketDisconnect:
        logger.info("Cliente desconectado de /ws/chat")
