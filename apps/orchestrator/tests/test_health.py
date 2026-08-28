from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import app.main as main_module


def test_health(monkeypatch) -> None:
    # Sin esto, el lifespan intentaría cargar (y potencialmente descargar) un modelo real
    # de whisper solo para levantar la app en un test que no necesita STT para nada.
    monkeypatch.setattr(main_module, "load_whisper_model", MagicMock(return_value=object()))

    with TestClient(main_module.app) as client:  # entra al lifespan (Qdrant + whisper)
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
