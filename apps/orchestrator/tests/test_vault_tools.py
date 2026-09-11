import asyncio

import pytest

from app.tools.vault_tools import eliminar_tarea, resolve_vault_path


def test_resolve_vault_path_allows_paths_inside_vault(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    resolved = resolve_vault_path("proyectos/idea.md")

    assert resolved == (tmp_path / "proyectos" / "idea.md").resolve()


def test_resolve_vault_path_blocks_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    with pytest.raises(ValueError, match="fuera del vault"):
        resolve_vault_path("../fuera-del-vault.md")


def test_resolve_vault_path_blocks_reserved_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    with pytest.raises(ValueError, match="reservada"):
        resolve_vault_path(".asistente/audit.jsonl")


# eliminar_tarea es `async def` (por la firma compartida de ToolExecutor) pero no usa await
# adentro (no necesita qdrant_client) — se llama con asyncio.run() en vez de sumar
# pytest-asyncio como dependencia nueva solo para esto.


def test_eliminar_tarea_borra_la_linea_pendiente(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))
    nota = tmp_path / "tareas.md"
    nota.write_text(
        "# Tareas\n- [ ] comprar pan\n- [x] pagar el alquiler\n- [ ] llamar al dentista\n", encoding="utf-8"
    )

    resultado = asyncio.run(eliminar_tarea({"ruta": "tareas.md", "texto": "comprar pan"}, None))

    assert resultado["ok"] is True
    contenido = nota.read_text(encoding="utf-8")
    assert "comprar pan" not in contenido
    assert "pagar el alquiler" in contenido
    assert "llamar al dentista" in contenido


def test_eliminar_tarea_hace_backup_del_archivo_antes_de_borrar(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))
    nota = tmp_path / "tareas.md"
    contenido_original = "- [ ] comprar pan\n"
    nota.write_text(contenido_original, encoding="utf-8")

    resultado = asyncio.run(eliminar_tarea({"ruta": "tareas.md", "texto": "comprar pan"}, None))

    backup_path = tmp_path / resultado["backup"]
    assert backup_path.read_text(encoding="utf-8") == contenido_original


def test_eliminar_tarea_no_borra_una_tarea_ya_hecha(monkeypatch, tmp_path) -> None:
    """Pedir "eliminar" una tarea ya marcada como hecha se trata como no encontrada, no se
    interpreta como "eliminala igual" — ver el docstring de eliminar_tarea."""
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))
    nota = tmp_path / "tareas.md"
    nota.write_text("- [x] comprar pan\n", encoding="utf-8")

    resultado = asyncio.run(eliminar_tarea({"ruta": "tareas.md", "texto": "comprar pan"}, None))

    assert "error" in resultado
    assert "comprar pan" in nota.read_text(encoding="utf-8")


def test_eliminar_tarea_con_texto_inexistente_devuelve_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))
    nota = tmp_path / "tareas.md"
    nota.write_text("- [ ] comprar pan\n", encoding="utf-8")

    resultado = asyncio.run(eliminar_tarea({"ruta": "tareas.md", "texto": "esto no está en la nota"}, None))

    assert "error" in resultado


def test_eliminar_tarea_con_ruta_inexistente_devuelve_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    resultado = asyncio.run(eliminar_tarea({"ruta": "no-existe.md", "texto": "comprar pan"}, None))

    assert "error" in resultado
