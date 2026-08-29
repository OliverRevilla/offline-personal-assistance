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


def test_turno_de_texto_sin_tools(client, monkeypatch):
    async def fake_stream_chat(messages, tools=None):
        for content in ["Hola", " mundo."]:
            yield {"type": "token", "content": content}

    monkeypatch.setattr(ws_module, "stream_chat", fake_stream_chat)

    with client.websocket_connect("/ws/chat") as ws:
        assert ws.receive_json()["tipo"] == "audio_meta"

        ws.send_json({"tipo": "user_message", "texto": "hola"})

        assert ws.receive_json()["tipo"] == "turn_start"
        assert ws.receive_json() == {"tipo": "token", "texto": "Hola"}
        assert ws.receive_json() == {"tipo": "token", "texto": " mundo."}

        # la síntesis del audio de "Hola mundo." se espera ANTES de turn_end (ver el
        # `finally` de procesar_turno que awaitea el tts_task) — no llega antes ni después.
        audio_frame = ws.receive_bytes()
        assert audio_frame[0] == 0x02

        assert ws.receive_json()["tipo"] == "turn_end"


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
        ws.send_json({"tipo": "user_message", "texto": "listame las tareas"})

        assert ws.receive_json()["tipo"] == "turn_start"

        tool_call_msg = ws.receive_json()
        assert tool_call_msg["tipo"] == "tool_call"
        assert tool_call_msg["nombre"] == "listar_tareas"

        assert ws.receive_json()["tipo"] == "tool_result"
        assert ws.receive_json() == {"tipo": "token", "texto": "Listo."}

        ws.receive_bytes()  # audio de "Listo."
        assert ws.receive_json()["tipo"] == "turn_end"


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
        ws2.send_json({"tipo": "user_message", "texto": "hola otra vez"})
        assert ws2.receive_json()["tipo"] == "turn_start"
        assert ws2.receive_json() == {"tipo": "token", "texto": "Hola de nuevo."}
