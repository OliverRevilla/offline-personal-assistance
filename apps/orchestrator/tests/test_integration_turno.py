"""Tests de integración end-to-end del turno completo (Fase 7), mockeando Ollama/Piper/Qdrant
para que corran sin depender de servicios externos reales.

Ejercitan el WS de punta a punta (`client.websocket_connect`), no funciones sueltas — es la
diferencia con los tests unitarios del resto de `tests/`.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.ws as ws_module
import app.main as main_module


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main_module, "load_whisper_model", MagicMock(return_value=object()))
    monkeypatch.setattr(main_module, "verify_piper_available", MagicMock())
    monkeypatch.setattr(main_module, "load_voice_sample_rate", MagicMock(return_value=22050))

    monkeypatch.setattr(ws_module, "retrieve", AsyncMock(return_value=[]))
    monkeypatch.setattr(ws_module, "synthesize", AsyncMock(return_value=b"\x00\x00"))

    with TestClient(main_module.app) as test_client:
        yield test_client


def consumir_saludo(ws) -> None:
    """Cada conexión saluda sola antes de esperar nada del cliente (ver GREETING_TEXT en ws.py).

    El saludo tiene dos oraciones (parte en `feed`, el resto vía `flush`), así que son dos
    frames de audio — no uno — antes del `turn_end`.
    """
    assert ws.receive_json()["tipo"] == "turn_start"
    assert ws.receive_json() == {"tipo": "token", "texto": ws_module.GREETING_TEXT}
    ws.receive_bytes()
    ws.receive_bytes()
    assert ws.receive_json()["tipo"] == "turn_end"


def consumir_confirmacion_modo_teclado(ws) -> None:
    assert ws.receive_json() == {"tipo": "modo_entrada", "modo": "teclado"}
    assert ws.receive_json()["tipo"] == "turn_start"
    assert ws.receive_json() == {"tipo": "token", "texto": ws_module.MODO_TECLADO_CONFIRMACION_TEXT}
    ws.receive_bytes()
    assert ws.receive_json()["tipo"] == "turn_end"


def test_saludo_al_conectar_no_pasa_por_el_llm(client, monkeypatch):
    stream_chat_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "stream_chat", stream_chat_mock)

    with client.websocket_connect("/ws/chat") as ws:
        assert ws.receive_json()["tipo"] == "audio_meta"
        consumir_saludo(ws)

    stream_chat_mock.assert_not_called()


def test_frase_todo_por_teclado_no_llega_al_llm(client, monkeypatch):
    class FakeSegmenter:
        def __init__(self, *args, **kwargs):
            self.entregada = False

        def feed(self, chunk: bytes) -> bytes | None:
            if self.entregada:
                return None
            self.entregada = True
            return b"\x00\x00"

    stream_chat_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "VadSegmenter", FakeSegmenter)
    monkeypatch.setattr(ws_module, "transcribe_pcm16", MagicMock(return_value="todo por teclado"))
    monkeypatch.setattr(ws_module, "stream_chat", stream_chat_mock)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)

        ws.send_bytes(bytes([0x01]) + b"\x00\x00" * 10)

        assert ws.receive_json() == {"tipo": "transcript_final", "texto": "todo por teclado"}
        consumir_confirmacion_modo_teclado(ws)

    stream_chat_mock.assert_not_called()


def test_frase_todo_por_teclado_no_matchea_si_solo_se_menciona(client, monkeypatch):
    """Regresión: un `search` sin anclar activaría esto por error con frases que solo
    mencionan el comando en vez de darlo (ver MODO_TECLADO_RE — usa `fullmatch`)."""

    class FakeSegmenter:
        def __init__(self, *args, **kwargs):
            self.entregada = False

        def feed(self, chunk: bytes) -> bytes | None:
            if self.entregada:
                return None
            self.entregada = True
            return b"\x00\x00"

    async def fake_stream_chat(messages, tools=None):
        yield {"type": "token", "content": "Sí, se puede."}

    monkeypatch.setattr(ws_module, "VadSegmenter", FakeSegmenter)
    monkeypatch.setattr(
        ws_module, "transcribe_pcm16", MagicMock(return_value="¿se puede hacer todo por teclado?")
    )
    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)

        ws.send_bytes(bytes([0x01]) + b"\x00\x00" * 10)

        assert ws.receive_json() == {"tipo": "transcript_final", "texto": "¿se puede hacer todo por teclado?"}
        # va al LLM como un turno normal, no como el comando de modo teclado
        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "token", "texto": "Sí, se puede."}
        ws.receive_bytes()
        assert ws.receive_json()["tipo"] == "turn_end"


def test_modo_teclado_bloquea_audio_subsiguiente_del_lado_del_server(client, monkeypatch):
    """El server no confía solo en que el cliente corte el mic tras "todo por teclado": si
    igual llega otro frame de audio, ni lo transcribe ni lo manda al LLM (mismo criterio que
    `voz_salida`, que tampoco confía solo en que el cliente no reproduzca)."""

    class FakeSegmenter:
        def feed(self, chunk: bytes) -> bytes | None:
            return b"\x00\x00"  # cada frame que llega ya cuenta como una utterance completa

    transcribe_mock = MagicMock(return_value="todo por teclado")
    stream_chat_mock = AsyncMock()
    monkeypatch.setattr(ws_module, "VadSegmenter", FakeSegmenter)
    monkeypatch.setattr(ws_module, "transcribe_pcm16", transcribe_mock)
    monkeypatch.setattr(ws_module, "stream_chat", stream_chat_mock)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)

        ws.send_bytes(bytes([0x01]) + b"\x00\x00" * 10)
        assert ws.receive_json() == {"tipo": "transcript_final", "texto": "todo por teclado"}
        consumir_confirmacion_modo_teclado(ws)

        # el cliente "no debería" mandar más audio después de esto, pero llega igual (ej. una
        # race con el stop() del lado del cliente) — el server lo descarta antes de transcribir.
        ws.send_bytes(bytes([0x01]) + b"\x00\x00" * 10)

    assert transcribe_mock.call_count == 1
    stream_chat_mock.assert_not_called()


def test_saludo_queda_en_history_para_que_el_llm_no_repita(client, monkeypatch):
    mensajes_capturados: dict = {}

    async def fake_stream_chat(messages, tools=None):
        mensajes_capturados["messages"] = messages
        yield {"type": "token", "content": "Hola."}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)

        ws.send_json({"tipo": "user_message", "texto": "hola"})
        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "token", "texto": "Hola."}
        ws.receive_bytes()
        assert ws.receive_json()["tipo"] == "turn_end"

    assert {"role": "assistant", "content": ws_module.GREETING_TEXT} in mensajes_capturados["messages"]


def test_turno_de_texto_sin_tools(client, monkeypatch):
    async def fake_stream_chat(messages, tools=None):
        for content in ["Hola", " mundo."]:
            yield {"type": "token", "content": content}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        assert ws.receive_json()["tipo"] == "audio_meta"
        consumir_saludo(ws)

        ws.send_json({"tipo": "user_message", "texto": "hola"})

        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "token", "texto": "Hola"}
        assert ws.receive_json() == {"tipo": "token", "texto": " mundo."}

        # la síntesis del audio de "Hola mundo." se espera ANTES de turn_end (ver el
        # `finally` de procesar_turno que awaitea el tts_task) — no llega antes ni después.
        audio_frame = ws.receive_bytes()
        assert audio_frame[0] == 0x02

        assert ws.receive_json()["tipo"] == "turn_end"


def test_set_preferences_desactiva_la_voz_de_salida(client, monkeypatch):
    """Con `voz_salida: false`, no debe llegar ningún frame de audio ni llamarse a Piper."""

    async def fake_stream_chat(messages, tools=None):
        for content in ["Hola", " mundo."]:
            yield {"type": "token", "content": content}

    sintetizar_mock = AsyncMock(return_value=b"\x00\x00")
    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(ws_module, "synthesize", sintetizar_mock)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        # el saludo inicial usa el default (voz_salida=True): el toggle recién llega al server
        # en el próximo mensaje, así que este primer turno sí tiene audio (y sí llama a Piper).
        consumir_saludo(ws)
        llamadas_del_saludo = sintetizar_mock.call_count
        assert llamadas_del_saludo > 0, "el saludo debería sintetizar audio con el default voz_salida=True"

        ws.send_json({"tipo": "set_preferences", "voz_salida": False})
        ws.send_json({"tipo": "user_message", "texto": "hola"})

        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "token", "texto": "Hola"}
        assert ws.receive_json() == {"tipo": "token", "texto": " mundo."}
        # sin frame de audio en el medio: el siguiente mensaje ya es turn_end
        assert ws.receive_json()["tipo"] == "turn_end"

    # se compara contra el contador de después del saludo, no con `assert_not_called()`: el
    # saludo de la conexión ya llamó a synthesize antes de que el toggle pudiera llegar. Lo que
    # se verifica es que el turno POSTERIOR al toggle no gastó nada de CPU en Piper.
    assert sintetizar_mock.call_count == llamadas_del_saludo


def test_turno_con_tool_calling(client, monkeypatch):
    calls = {"n": 0}

    async def fake_stream_chat(messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {"type": "tool_calls", "calls": [{"function": {"name": "listar_tareas", "arguments": {}}}]}
        else:
            yield {"type": "token", "content": "Listo."}

    async def fake_run_tool(nombre, argumentos, qdrant_client):
        return {"tareas": []}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(ws_module, "run_tool", fake_run_tool)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)
        ws.send_json({"tipo": "user_message", "texto": "listame las tareas"})

        assert ws.receive_json()["tipo"] == "turn_start"

        tool_call_msg = ws.receive_json()
        assert tool_call_msg["tipo"] == "tool_call"
        assert tool_call_msg["nombre"] == "listar_tareas"

        assert ws.receive_json()["tipo"] == "tool_result"
        assert ws.receive_json() == {"tipo": "token", "texto": "Listo."}

        ws.receive_bytes()  # audio de "Listo."
    assert ws.receive_json()["tipo"] == "turn_end"


def test_tool_dashboard_envia_evento_tipado_al_cliente(client, monkeypatch):
    calls = {"n": 0}
    dashboard = {
        "fecha_referencia": "2026-09-11",
        "tareas": [],
        "resumen": {"total": 0, "pendientes": 0, "completadas": 0, "vencidas": 0, "sin_fecha": 0},
    }

    async def fake_stream_chat(messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {"type": "tool_calls", "calls": [{"function": {"name": "mostrar_dashboard_tareas", "arguments": {}}}]}
        else:
            yield {"type": "token", "content": "Abrí tu dashboard."}

    async def fake_run_tool(nombre, argumentos, qdrant_client):
        assert nombre == "mostrar_dashboard_tareas"
        return dashboard

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(ws_module, "run_tool", fake_run_tool)
    monkeypatch.setattr(ws_module, "es_solicitud_dashboard", lambda texto: False)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)
        ws.send_json({"tipo": "user_message", "texto": "Permitíme ver el dashboard de tareas"})

        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "tool_call", "nombre": "mostrar_dashboard_tareas", "argumentos": {}}
        assert ws.receive_json() == {"tipo": "tool_result", "nombre": "mostrar_dashboard_tareas", "resultado": dashboard}
        assert ws.receive_json() == {"tipo": "dashboard_tareas", **dashboard}
        assert ws.receive_json() == {"tipo": "token", "texto": "Abrí tu dashboard."}
        ws.receive_bytes()
        assert ws.receive_json()["tipo"] == "turn_end"


def test_dashboard_intencion_tolera_errores_de_transcripcion():
    assert ws_module.es_solicitud_dashboard("Dahboard de atreas") is True
    assert ws_module.es_solicitud_dashboard("no quiero abrir el dashboard") is False


def test_confirmacion_aprobada_ejecuta_la_tool(client, monkeypatch):
    calls = {"n": 0}

    async def fake_stream_chat(messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {
                "type": "tool_calls",
                "calls": [
                    {"function": {"name": "actualizar_nota", "arguments": {"ruta": "x.md", "contenido": "y"}}}
                ],
            }
        else:
            yield {"type": "token", "content": "Hecho."}

    executed = []

    async def fake_run_tool(nombre, argumentos, qdrant_client):
        executed.append((nombre, argumentos))
        return {"ok": True}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(ws_module, "run_tool", fake_run_tool)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)
        ws.send_json({"tipo": "user_message", "texto": "actualizá la nota"})

        ws.receive_json()  # turn_start
        assert ws.receive_json()["tipo"] == "tool_call"

        confirm = ws.receive_json()
        assert confirm["tipo"] == "confirmacion_requerida"

        ws.send_json({"tipo": "confirmacion_respuesta", "id": confirm["id"], "aprobado": True})

        assert ws.receive_json()["tipo"] == "tool_result"
        assert ws.receive_json() == {"tipo": "token", "texto": "Hecho."}
        ws.receive_bytes()
        assert ws.receive_json()["tipo"] == "turn_end"

    assert executed == [("actualizar_nota", {"ruta": "x.md", "contenido": "y"})]


def test_audio_durante_confirmacion_pendiente_no_rompe_el_turno(client, monkeypatch):
    """Regresión del rough edge de la Fase 3/4: llegaba un frame de audio mientras
    `pedir_confirmacion` esperaba, y rompía el turno con un error no manejado."""
    calls = {"n": 0}

    async def fake_stream_chat(messages, tools=None):
        calls["n"] += 1
        if calls["n"] == 1:
            yield {
                "type": "tool_calls",
                "calls": [
                    {"function": {"name": "actualizar_nota", "arguments": {"ruta": "x.md", "contenido": "y"}}}
                ],
            }
        else:
            yield {"type": "token", "content": "Ok."}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(
        ws_module, "run_tool", AsyncMock(side_effect=AssertionError("no debería ejecutarse: se rechaza"))
    )

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)
        ws.send_json({"tipo": "user_message", "texto": "actualizá"})
        ws.receive_json()  # turn_start
        assert ws.receive_json()["tipo"] == "tool_call"
        confirm = ws.receive_json()
        assert confirm["tipo"] == "confirmacion_requerida"

        # el usuario sigue hablando mientras hay una confirmación pendiente: no debe romper el turno
        ws.send_bytes(bytes([0x01]) + b"\x00\x00" * 10)

        ws.send_json({"tipo": "confirmacion_respuesta", "id": confirm["id"], "aprobado": False})

        tool_result = ws.receive_json()
        assert tool_result["tipo"] == "tool_result"
        assert "no confirmó" in tool_result["resultado"]["error"]
        assert ws.receive_json() == {"tipo": "token", "texto": "Ok."}
        ws.receive_bytes()
        assert ws.receive_json()["tipo"] == "turn_end"


def test_desconexion_a_mitad_de_turno_no_rompe_el_server(client, monkeypatch):
    """Criterio de "hecho" de la Fase 7: el server sobrevive a una desconexión a mitad de turno.

    La desconexión ocurre mientras `pedir_confirmacion` está esperando `websocket.receive()`
    (no a mitad de la generación del LLM): es el punto donde el server efectivamente puede
    *detectar* la desconexión activamente, y el que más le importa a este criterio porque es
    justo donde vive el rough edge de la Fase 3/4 (turno bloqueado esperando al cliente).
    """

    async def fake_stream_chat(messages, tools=None):
        yield {
            "type": "tool_calls",
            "calls": [{"function": {"name": "actualizar_nota", "arguments": {"ruta": "x.md", "contenido": "y"}}}],
        }

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        ws.receive_json()  # audio_meta
        consumir_saludo(ws)
        ws.send_json({"tipo": "user_message", "texto": "actualizá"})
        ws.receive_json()  # turn_start
        assert ws.receive_json()["tipo"] == "tool_call"
        assert ws.receive_json()["tipo"] == "confirmacion_requerida"
        # el cliente se desconecta acá, con el server esperando su confirmación

    # una conexión nueva inmediatamente después tiene que funcionar normal — el server no
    # debe haber quedado en un estado roto (task de TTS huérfana, excepción sin manejar, etc.)
    # por la desconexión anterior.
    async def fake_stream_chat_normal(messages, tools=None):
        yield {"type": "token", "content": "Hola de nuevo."}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat_normal)

    with client.websocket_connect("/ws/chat") as ws2:
        ws2.receive_json()  # audio_meta
        consumir_saludo(ws2)
        ws2.send_json({"tipo": "user_message", "texto": "hola otra vez"})
        assert ws2.receive_json()["tipo"] == "turn_start"
        assert ws2.receive_json() == {"tipo": "token", "texto": "Hola de nuevo."}
