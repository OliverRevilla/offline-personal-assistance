import asyncio
from datetime import date

import pytest

from app.tools.vault_tools import eliminar_tarea, mostrar_dashboard_tareas, resolve_vault_path, task_dashboard_item


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


def test_dashboard_extrae_fechas_y_estado_desde_la_tarea() -> None:
    tarea = task_dashboard_item(
        "proyectos/demo.md",
        7,
        "Preparar demo 🛫 2026-09-14 📅 2026-09-20",
        False,
        date(2026, 9, 11),
    )

    assert tarea["titulo"] == "Preparar demo"
    assert tarea["fecha_inicio"] == "2026-09-14"
    assert tarea["fecha_fin"] == "2026-09-20"
    assert tarea["estado"] == "programada"
    assert tarea["progreso"] == 0


def test_dashboard_usa_vencimiento_como_hito_y_no_inventa_duracion() -> None:
    tarea = task_dashboard_item("tareas.md", 2, "Pagar servicio 📅 2026-09-10", False, date(2026, 9, 11))

    assert tarea["fecha_inicio"] == "2026-09-10"
    assert tarea["fecha_fin"] == "2026-09-10"
    assert tarea["estado"] == "vencida"


def test_mostrar_dashboard_reune_tareas_calendarizadas_y_sin_fecha(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))
    (tmp_path / "plan.md").write_text(
        "- [ ] Definir alcance 🛫 2026-09-14 📅 2026-09-18\n- [x] Crear borrador\n", encoding="utf-8"
    )

    resultado = asyncio.run(mostrar_dashboard_tareas({}, None))

    assert resultado["resumen"]["total"] == 2
    assert resultado["resumen"]["pendientes"] == 1
    assert resultado["tareas"][0]["titulo"] == "Definir alcance"
    assert resultado["tareas"][1]["estado"] == "completada"
