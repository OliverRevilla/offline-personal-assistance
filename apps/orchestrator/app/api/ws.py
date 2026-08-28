import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.llm.ollama_client import SYSTEM_PROMPT, stream_chat
from app.rag.retriever import format_context, retrieve
from app.stt.vad_segmenter import VadSegmenter
from app.stt.whisper_client import transcribe_pcm16
from app.tools.registry import TOOL_SCHEMAS, is_destructive, run_tool

logger = logging.getLogger(__name__)
router = APIRouter()

# Protocolo (ver docs/ARCHITECTURE.md):
#   cliente -> servidor: {"tipo": "user_message", "texto": str}                    (JSON)
#                        {"tipo": "confirmacion_respuesta", "id": str, "aprobado": bool}  (JSON)
#                        frame binario: 1 byte de cabecera (AUDIO_IN_HEADER) + PCM16 mono 16kHz
#   servidor -> cliente: {"tipo": "turn_start"}
#                        {"tipo": "transcript_final", "texto": str}
#                        {"tipo": "token", "texto": str}
#                        {"tipo": "tool_call", "nombre": str, "argumentos": dict}
#                        {"tipo": "confirmacion_requerida", "id": str, "nombre": str, "argumentos": dict}
#                        {"tipo": "tool_result", "nombre": str, "resultado": dict}
#                        {"tipo": "turn_end"}
#                        {"tipo": "error", "mensaje": str}

AUDIO_IN_HEADER = 0x01
# 0x02 (audio_out) queda reservado para la Fase 5 (TTS), todavía no se usa.

MAX_TOOL_ITERATIONS = 5


async def pedir_confirmacion(websocket: WebSocket, nombre: str, argumentos: dict) -> bool:
    """Pausa el turno hasta que el cliente confirme o rechace una tool destructiva."""
    confirmation_id = str(uuid.uuid4())
    await websocket.send_json(
        {"tipo": "confirmacion_requerida", "id": confirmation_id, "nombre": nombre, "argumentos": argumentos}
    )

    while True:
        data = await websocket.receive_json()
        if data.get("tipo") == "confirmacion_respuesta" and data.get("id") == confirmation_id:
            return bool(data.get("aprobado"))
        await websocket.send_json(
            {"tipo": "error", "mensaje": "Hay una confirmación pendiente; respondé a ella antes de continuar."}
        )


async def procesar_turno(websocket: WebSocket, history: list[dict], texto: str) -> None:
    """Ejecuta un turno completo (RAG + LLM + tool calling) y actualiza `history` in-place.

    La usan tanto los mensajes de texto (`user_message`) como las transcripciones de audio
    (Fase 4): para el resto del pipeline, dan exactamente lo mismo.
    """
    messages = list(history)
    try:
        resultados = await retrieve(websocket.app.state.qdrant, texto)
        contexto = format_context(resultados)
        if contexto:
            messages.append({"role": "system", "content": f"Contexto relevante del vault:\n\n{contexto}"})
    except Exception:  # noqa: BLE001 - RAG es un enhancement, no debe tumbar el chat
        logger.exception("Fallo al recuperar contexto de Qdrant, se continúa sin RAG")

    messages.append({"role": "user", "content": texto})
    await websocket.send_json({"tipo": "turn_start"})

    respuesta_final = ""
    try:
        for iteracion in range(MAX_TOOL_ITERATIONS):
            respuesta_ronda = ""
            tool_calls: list[dict] = []

            async for event in stream_chat(messages, tools=TOOL_SCHEMAS):
                if event["type"] == "token":
                    respuesta_ronda += event["content"]
                    await websocket.send_json({"tipo": "token", "texto": event["content"]})
                elif event["type"] == "tool_calls":
                    tool_calls.extend(event["calls"])

            assistant_message: dict = {"role": "assistant", "content": respuesta_ronda}
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)
            respuesta_final += respuesta_ronda

            if not tool_calls:
                break

            for call in tool_calls:
                nombre = call["function"]["name"]
                argumentos = call["function"]["arguments"]
                if isinstance(argumentos, str):
                    argumentos = json.loads(argumentos)

                await websocket.send_json({"tipo": "tool_call", "nombre": nombre, "argumentos": argumentos})

                if is_destructive(nombre) and not await pedir_confirmacion(websocket, nombre, argumentos):
                    resultado = {"error": "El usuario no confirmó la operación; no se ejecutó."}
                else:
                    resultado = await run_tool(nombre, argumentos, websocket.app.state.qdrant)

                await websocket.send_json({"tipo": "tool_result", "nombre": nombre, "resultado": resultado})
                messages.append({"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)})
        else:
            logger.warning("Se alcanzó MAX_TOOL_ITERATIONS (%d) sin una respuesta final", MAX_TOOL_ITERATIONS)

    except WebSocketDisconnect:
        # el cliente se fue a mitad de turno (posiblemente esperando una confirmación
        # pendiente): dejar que lo maneje el handler externo, no es un fallo del LLM.
        raise
    except Exception as exc:  # noqa: BLE001 - se reporta al cliente y se sigue la sesión
        logger.exception("Fallo al generar la respuesta del LLM")
        await websocket.send_json({"tipo": "error", "mensaje": str(exc)})
        return

    history.append({"role": "user", "content": texto})
    history.append({"role": "assistant", "content": respuesta_final})
    await websocket.send_json({"tipo": "turn_end"})


async def procesar_audio(websocket: WebSocket, history: list[dict], segmenter: VadSegmenter, raw: bytes) -> None:
    """Alimenta un frame de audio al VAD; si detecta fin de turno, transcribe y dispara procesar_turno."""
    if not raw or raw[0] != AUDIO_IN_HEADER:
        logger.warning("Frame binario con cabecera desconocida (primer byte=%r), se descarta", raw[:1])
        return

    utterance = segmenter.feed(raw[1:])
    if utterance is None:
        return

    texto = await asyncio.to_thread(transcribe_pcm16, websocket.app.state.whisper_model, utterance)
    await websocket.send_json({"tipo": "transcript_final", "texto": texto})

    texto = texto.strip()
    if texto:
        await procesar_turno(websocket, history, texto)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    # `history` solo guarda turnos reales de la conversación (system/user/assistant), nunca
    # el contexto RAG ni la mecánica interna de tool calling: si los persistiéramos ahí
    # crecería sin control y arrastraría contexto de rondas viejas en turnos donde ya no aplica.
    history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    segmenter = VadSegmenter(aggressiveness=settings.vad_aggressiveness, window_ms=settings.vad_window_ms)

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(code=message.get("code", 1000))

            if message.get("bytes") is not None:
                await procesar_audio(websocket, history, segmenter, message["bytes"])
                continue

            if message.get("text") is None:
                continue
            data = json.loads(message["text"])

            if data.get("tipo") != "user_message":
                await websocket.send_json(
                    {"tipo": "error", "mensaje": f"tipo de mensaje no soportado: {data.get('tipo')!r}"}
                )
                continue

            texto = (data.get("texto") or "").strip()
            if not texto:
                continue

            await procesar_turno(websocket, history, texto)

    except WebSocketDisconnect:
        logger.info("Cliente desconectado de /ws/chat")
