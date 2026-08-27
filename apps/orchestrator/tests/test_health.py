from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:  # entra al lifespan (crea/cierra el cliente de Qdrant)
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
