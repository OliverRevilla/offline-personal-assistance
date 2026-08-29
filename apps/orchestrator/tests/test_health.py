from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.main as main_module


def test_health(monkeypatch) -> None:
    # Sin esto, el lifespan intentaría cargar un modelo real de whisper y validar que Piper
    # esté instalado, solo para levantar la app en un test que no necesita STT/TTS para nada.
    monkeypatch.setattr(main_module, "load_whisper_model", MagicMock(return_value=object()))
    monkeypatch.setattr(main_module, "verify_piper_available", MagicMock())
    monkeypatch.setattr(main_module, "load_voice_sample_rate", MagicMock(return_value=22050))

    with TestClient(main_module.app) as client:  # entra al lifespan (Qdrant + whisper + piper)
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
