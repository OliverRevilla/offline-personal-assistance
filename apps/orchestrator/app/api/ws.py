import asyncio
import json
import logging
import re
import time
import unicodedata
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.metrics import metrics
from app.llm.ollama_client import SYSTEM_PROMPT, stream_chat
from app.rag.retriever import format_context, retrieve
from app.stt.vad_segmenter import VadSegmenter
from app.stt.whisper_client import transcribe_pcm16
from app.tools.registry import TOOL_SCHEMAS, is_destructive, run_tool
from app.tts.piper_client import synthesize
from app.tts.sentence_buffer import SentenceBuffer

logger = logging.getLogger(__name__)
router = APIRouter()

# Protocolo (ver docs/ARCHITECTURE.md):
#   cliente -> servidor: {"tipo": "user_message", "texto": str}                    (JSON)
#                        {"tipo": "confirmacion_respuesta", "id": str, "aprobado": bool}  (JSON)
#                        {"tipo": "set_preferences", "voz_salida": bool}           (JSON, opcional en cualquier momento)
#                        frame binario: 1 byte de cabecera (AUDIO_IN_HEADER) + PCM16 mono 16kHz
#   servidor -> cliente: {"tipo": "audio_meta", "sample_rate": int}   (una vez, al conectar)
#                        {"tipo": "turn_start"}
#                        {"tipo": "transcript_final", "texto": str}
#                        {"tipo": "token", "texto": str}
#                        {"tipo": "tool_call", "nombre": str, "argumentos": dict}
#                        {"tipo": "confirmacion_requerida", "id": str, "nombre": str, "argumentos": dict}
#                        {"tipo": "tool_result", "nombre": str, "resultado": dict}
#                        {"tipo": "dashboard_tareas", "fecha_referencia": str, "tareas": list, "resumen": dict}
#                        {"tipo": "turn_end"}
#                        {"tipo": "modo_entrada", "modo": "teclado"}  (el server detectó la frase de salida de voz)
#                        {"tipo": "error", "mensaje": str}
#                        frame binario: 1 byte de cabecera (AUDIO_OUT_HEADER) + PCM16 mono
#                        (sample rate según "audio_meta") — una oración sintetizada por frame
#
# Al conectar, el servidor saluda solo (un turno con GREETING_TEXT) antes de esperar nada del
# cliente — el modo voz-por-defecto asume que el usuario no va a tipear nada para arrancar.
# Si en un turno de audio la transcripción matchea MODO_TECLADO_RE, el servidor no lo manda al
# LLM: confirma por voz y avisa "modo_entrada" para que el cliente corte el micrófono. No hay
# frase de vuelta simétrica ("todo por voz") porque la decisión de producto es que volver a modo
# voz requiere reabrir la app o tocar el botón de mic — ver docs/ARCHITECTURE.md.

AUDIO_IN_HEADER = 0x01
AUDIO_OUT_HEADER = 0x02

MAX_TOOL_ITERATIONS = 5

GREETING_TEXT = "Oliver, ¿cómo estás? ¿En qué te puedo ayudar?"
# Ancla la frase completa (con `fullmatch`, no `search`) permitiendo solo un puñado de muletillas
# alrededor: "no quiero todo por teclado" o "¿qué es eso de todo por teclado?" NO deben matchear
# (mencionan la frase, no la ordenan) — un `search` sin anclar los activaría por error.
MODO_TECLADO_RE = re.compile(
    r"\W*(che|dale|ok|okay|bueno|listo)?\W*todo\s+por\s+teclado\W*(por\s+favor|gracias)?\W*",
    re.IGNORECASE,
)
MODO_TECLADO_CONFIRMACION_TEXT = "Listo, ahora todo por teclado."


def _normalizar_intencion(texto: str) -> str:
    sin_acentos = "".join(
        caracter for caracter in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(caracter)
    )
    return sin_acentos


def _token_parecido(token: str, candidatos: tuple[str, ...]) -> bool:
    """Tolera errores pequeños típicos de STT (ej. `dahboard` y `atreas`)."""
    if len(token) < 5:
        return False
    for candidato in candidatos:
        if token == candidato:
            return True
        # Distancia de Levenshtein acotada: evita depender del LLM para una orden de UI.
        anterior = list(range(len(candidato) + 1))
        for indice, caracter in enumerate(token, start=1):
            actual = [indice]
            for columna, esperado in enumerate(candidato, start=1):
                actual.append(min(actual[-1] + 1, anterior[columna] + 1, anterior[columna - 1] + (caracter != esperado)))
            anterior = actual
        if anterior[-1] <= 2:
            return True
    return False


def es_solicitud_dashboard(texto: str) -> bool:
    normalizado = _normalizar_intencion(texto)
    tokens = re.findall(r"[a-z0-9]+", normalizado)
    if any(token in {"no", "nunca", "cancelar", "cancela", "cierra"} for token in tokens):
        return False
    return any(_token_parecido(token, ("dashboard",)) for token in tokens)


async def pedir_confirmacion(websocket: WebSocket, nombre: str, argumentos: dict) -> bool:
    """Pausa el turno hasta que el cliente confirme o rechace una tool destructiva.

    Usa el `receive()` genérico (no `receive_json()`) porque el cliente puede seguir
    mandando frames de audio (ej. si sigue hablando) mientras hay una confirmación
    pendiente — esos se descartan acá en vez de romper el turno (Fase 7).
    """
    confirmation_id = str(uuid.uuid4())
    await websocket.send_json(
        {"tipo": "confirmacion_requerida", "id": confirmation_id, "nombre": nombre, "argumentos": argumentos}
    )

    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(code=message.get("code", 1000))

        if message.get("bytes") is not None:
            logger.warning("Frame de audio descartado: hay una confirmación pendiente (id=%s)", confirmation_id)
            continue

        if message.get("text") is None:
            continue
        data = json.loads(message["text"])

        if data.get("tipo") == "confirmacion_respuesta" and data.get("id") == confirmation_id:
            return bool(data.get("aprobado"))

        await websocket.send_json(
            {"tipo": "error", "mensaje": "Hay una confirmación pendiente; respondé a ella antes de continuar."}
        )


async def hablar_oraciones(websocket: WebSocket, cola: "asyncio.Queue[str | None]") -> None:
    """Consume oraciones de a una y manda el audio sintetizado por WS, en orden.

    Corre como task en paralelo al streaming de texto: así una oración larga tardando en
    sintetizarse no bloquea que sigan llegando tokens de texto al cliente mientras tanto.
    """
    while True:
        oracion = await cola.get()
        try:
            if oracion is None:
                break
            inicio = time.monotonic()
            audio = await synthesize(oracion)
            metrics.record_tts_latency((time.monotonic() - inicio) * 1000)
            await websocket.send_bytes(bytes([AUDIO_OUT_HEADER]) + audio)
        except Exception:  # noqa: BLE001 - un fallo de síntesis no debe tumbar el turno de texto
            logger.exception("Fallo al sintetizar/enviar audio para: %r", oracion)
        finally:
            cola.task_done()


async def hablar_texto_directo(websocket: WebSocket, texto: str, preferencias: dict) -> None:
    """Manda un turno completo (texto + voz) con un texto fijo, sin pasar por el LLM.

    Lo usan el saludo inicial y la confirmación de "modo teclado": del otro lado del WS se ve
    igual que un turno real (turn_start/token/turn_end + audio si `voz_salida` está prendida),
    así el cliente no necesita un caso especial para distinguirlos.

    No toca `history` a propósito: cada caller decide si el texto es parte de la conversación
    (el saludo sí, para que el LLM no vuelva a saludar en el primer turno real) o si es solo un
    acuse de recibo de la UI que no debe arrastrar contexto (la confirmación de "modo teclado").
    """
    voz_habilitada = preferencias.get("voz_salida", True)
    sentence_buffer = SentenceBuffer()
    audio_queue: asyncio.Queue[str | None] = asyncio.Queue()
    tts_task = asyncio.create_task(hablar_oraciones(websocket, audio_queue))

    try:
        await websocket.send_json({"tipo": "turn_start"})
        await websocket.send_json({"tipo": "token", "texto": texto})
        if voz_habilitada:
            for oracion in sentence_buffer.feed(texto):
                await audio_queue.put(oracion)
            resto = sentence_buffer.flush()
            if resto:
                await audio_queue.put(resto)
    finally:
        # mismo motivo que el `finally` de procesar_turno: el saludo es lo primero que pasa en
        # toda conexión, así que es el punto más probable para que el cliente se vaya a mitad de
        # turno — sin esto quedaría una task de síntesis huérfana esperando en la cola.
        await audio_queue.put(None)
        await tts_task

    await websocket.send_json({"tipo": "turn_end"})


async def procesar_solicitud_dashboard(
    websocket: WebSocket, history: list[dict], texto: str, preferencias: dict
) -> None:
    """Abre el dashboard tras confirmación, incluso si el STT/LLM no reconoce la tool."""
    await websocket.send_json({"tipo": "turn_start"})
    voz_habilitada = preferencias.get("voz_salida", True)
    audio_queue: asyncio.Queue[str | None] = asyncio.Queue()
    tts_task = asyncio.create_task(hablar_oraciones(websocket, audio_queue))
    respuesta = ""

    try:
        argumentos: dict = {}
        await websocket.send_json({"tipo": "tool_call", "nombre": "mostrar_dashboard_tareas", "argumentos": argumentos})
        aprobado = await pedir_confirmacion(websocket, "mostrar_dashboard_tareas", argumentos)
        if aprobado:
            resultado = await run_tool("mostrar_dashboard_tareas", argumentos, websocket.app.state.qdrant)
            await websocket.send_json({"tipo": "tool_result", "nombre": "mostrar_dashboard_tareas", "resultado": resultado})
            if "error" not in resultado:
                await websocket.send_json({"tipo": "dashboard_tareas", **resultado})
                respuesta = "Listo, abrí tu dashboard nativo de tareas."
            else:
                respuesta = f"No pude abrir el dashboard: {resultado['error']}"
        else:
            resultado = {"error": "El usuario no confirmó la apertura del dashboard."}
            await websocket.send_json({"tipo": "tool_result", "nombre": "mostrar_dashboard_tareas", "resultado": resultado})
            respuesta = "De acuerdo, no abrí el dashboard."

        await websocket.send_json({"tipo": "token", "texto": respuesta})
        if voz_habilitada:
            await audio_queue.put(respuesta)
    finally:
        await audio_queue.put(None)
        await tts_task

    history.append({"role": "user", "content": texto})
    history.append({"role": "assistant", "content": respuesta})
    await websocket.send_json({"tipo": "turn_end"})


async def procesar_turno(websocket: WebSocket, history: list[dict], texto: str, preferencias: dict) -> None:
    """Ejecuta un turno completo (RAG + LLM + tool calling + TTS) y actualiza `history` in-place.

    La usan tanto los mensajes de texto (`user_message`) como las transcripciones de audio
    (Fase 4): para el resto del pipeline, dan exactamente lo mismo.

    `preferencias` es el dict mutable de `ws_chat` (ej. `{"voz_salida": bool}`) — si el
    cliente desactivó la voz de salida, ni se encola ni se sintetiza audio para este turno
    (no es solo "no reproducir del lado del cliente": el server no gasta CPU en Piper).
    """
    if es_solicitud_dashboard(texto):
        await procesar_solicitud_dashboard(websocket, history, texto, preferencias)
        return

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

    voz_habilitada = preferencias.get("voz_salida", True)
    sentence_buffer = SentenceBuffer()
    audio_queue: asyncio.Queue[str | None] = asyncio.Queue()
    tts_task = asyncio.create_task(hablar_oraciones(websocket, audio_queue))

    respuesta_final = ""
    try:
        try:
            for iteracion in range(MAX_TOOL_ITERATIONS):
                respuesta_ronda = ""
                tool_calls: list[dict] = []

                inicio_ronda = time.monotonic()
                primer_token_visto = False

                async for event in stream_chat(messages, tools=TOOL_SCHEMAS):
                    if event["type"] == "token":
                        if iteracion == 0 and not primer_token_visto:
                            metrics.record_llm_ttfb((time.monotonic() - inicio_ronda) * 1000)
                            primer_token_visto = True
                        respuesta_ronda += event["content"]
                        await websocket.send_json({"tipo": "token", "texto": event["content"]})
                        if voz_habilitada:
                            for oracion in sentence_buffer.feed(event["content"]):
                                await audio_queue.put(oracion)
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
                    if nombre == "mostrar_dashboard_tareas" and "error" not in resultado:
                        await websocket.send_json({"tipo": "dashboard_tareas", **resultado})
                    messages.append({"role": "tool", "content": json.dumps(resultado, ensure_ascii=False)})
            else:
                logger.warning("Se alcanzó MAX_TOOL_ITERATIONS (%d) sin una respuesta final", MAX_TOOL_ITERATIONS)

            resto = sentence_buffer.flush()
            if resto and voz_habilitada:
                await audio_queue.put(resto)

        except WebSocketDisconnect:
            # el cliente se fue a mitad de turno (posiblemente esperando una confirmación
            # pendiente): dejar que lo maneje el handler externo, no es un fallo del LLM.
            raise
        except Exception as exc:  # noqa: BLE001 - se reporta al cliente y se sigue la sesión
            logger.exception("Fallo al generar la respuesta del LLM")
            await websocket.send_json({"tipo": "error", "mensaje": str(exc)})
            return
    finally:
        # pase lo que pase arriba, cerrar prolijamente el worker de TTS: sin esto, un turno
        # fallido dejaría una task de síntesis huérfana esperando para siempre en la cola.
        await audio_queue.put(None)
        await tts_task

    history.append({"role": "user", "content": texto})
    history.append({"role": "assistant", "content": respuesta_final})
    await websocket.send_json({"tipo": "turn_end"})


async def procesar_audio(
    websocket: WebSocket, history: list[dict], segmenter: VadSegmenter, raw: bytes, preferencias: dict
) -> None:
    """Alimenta un frame de audio al VAD; si detecta fin de turno, transcribe y dispara procesar_turno."""
    if not raw or raw[0] != AUDIO_IN_HEADER:
        logger.warning("Frame binario con cabecera desconocida (primer byte=%r), se descarta", raw[:1])
        return

    if preferencias.get("entrada_teclado"):
        # el cliente ya debería haber cortado la captura de mic tras "todo por teclado", pero no
        # confiamos solo en eso (mismo criterio que voz_salida): si igual llega audio, ni se
        # transcribe ni se le pasa al LLM.
        return

    utterance = segmenter.feed(raw[1:])
    if utterance is None:
        return

    inicio = time.monotonic()
    texto = await asyncio.to_thread(transcribe_pcm16, websocket.app.state.whisper_model, utterance)
    metrics.record_stt_latency((time.monotonic() - inicio) * 1000)
    await websocket.send_json({"tipo": "transcript_final", "texto": texto})

    texto = texto.strip()
    if not texto:
        return

    if MODO_TECLADO_RE.fullmatch(texto):
        # comando interno: no llega al LLM ni queda en `history` como turno de conversación.
        preferencias["entrada_teclado"] = True
        await websocket.send_json({"tipo": "modo_entrada", "modo": "teclado"})
        await hablar_texto_directo(websocket, MODO_TECLADO_CONFIRMACION_TEXT, preferencias)
        return

    await procesar_turno(websocket, history, texto, preferencias)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"tipo": "audio_meta", "sample_rate": websocket.app.state.piper_sample_rate})

    # `history` solo guarda turnos reales de la conversación (system/user/assistant), nunca
    # el contexto RAG ni la mecánica interna de tool calling: si los persistiéramos ahí
    # crecería sin control y arrastraría contexto de rondas viejas en turnos donde ya no aplica.
    history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    segmenter = VadSegmenter(aggressiveness=settings.vad_aggressiveness, window_ms=settings.vad_window_ms)
    # Mutable a propósito: procesar_turno/procesar_audio lo leen para decidir si sintetizan
    # audio o no, y si siguen aceptando audio de entrada. "voz_salida" en True y
    # "entrada_teclado" en False por default (mic escuchando, salida hablada).
    preferencias: dict = {"voz_salida": True, "entrada_teclado": False}

    try:
        # el saludo va adentro del try: es lo primero que pasa en toda conexión, así que
        # también es un punto donde el cliente se puede ir a mitad de turno.
        await hablar_texto_directo(websocket, GREETING_TEXT, preferencias)
        history.append({"role": "assistant", "content": GREETING_TEXT})

        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                raise WebSocketDisconnect(code=message.get("code", 1000))

            if message.get("bytes") is not None:
                await procesar_audio(websocket, history, segmenter, message["bytes"], preferencias)
                continue

            if message.get("text") is None:
                continue
            data = json.loads(message["text"])
            tipo = data.get("tipo")

            if tipo == "set_preferences":
                if "voz_salida" in data:
                    preferencias["voz_salida"] = bool(data["voz_salida"])
                continue

            if tipo != "user_message":
                await websocket.send_json({"tipo": "error", "mensaje": f"tipo de mensaje no soportado: {tipo!r}"})
                continue

            texto = (data.get("texto") or "").strip()
            if not texto:
                continue

            await procesar_turno(websocket, history, texto, preferencias)

    except WebSocketDisconnect:
        logger.info("Cliente desconectado de /ws/chat")
