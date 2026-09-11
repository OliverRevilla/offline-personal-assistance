"""Ejecución real de las tools invocables por el LLM, sandboxeada al vault.

Todas las funciones tienen la misma firma `(argumentos: dict, qdrant_client) -> dict`
(aunque no todas usen `qdrant_client`) para que el dispatcher en `registry.py` las pueda
llamar de forma uniforme.
"""

import json
import re
import time
from datetime import date
from pathlib import Path

from app.core.config import settings
from app.rag.chunking import iter_markdown_files
from app.rag.retriever import retrieve

RESERVED_DIR = ".asistente"  # carpeta interna: audit log + backups, nunca destino de una tool
TASK_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+)$")
DATE_VALUE_RE = r"(\d{4}-\d{2}-\d{2})"
# Sintaxis de Obsidian Tasks, más aliases legibles para que el agente pueda escribirlos al
# crear o editar una nota. Ej.: `- [ ] Preparar demo 🛫 2026-09-14 📅 2026-09-20`.
TASK_START_RE = re.compile(rf"(?:🛫|inicio\s*::?|start\s*::?)\s*{DATE_VALUE_RE}", re.IGNORECASE)
TASK_END_RE = re.compile(rf"(?:📅|🏁|fecha[_\s-]*l[ií]mite\s*::?|fin\s*::?|due\s*::?)\s*{DATE_VALUE_RE}", re.IGNORECASE)
TASK_METADATA_RE = re.compile(
    rf"\s*(?:🛫|inicio\s*::?|start\s*::?|📅|🏁|fecha[_\s-]*l[ií]mite\s*::?|fin\s*::?|due\s*::?)\s*{DATE_VALUE_RE}",
    re.IGNORECASE,
)


def vault_root() -> Path:
    return Path(settings.vault_path).resolve()


def resolve_vault_path(relpath: str) -> Path:
    """Resuelve `relpath` contra el vault y garantiza que no escape de él (ni apunte a RESERVED_DIR)."""
    root = vault_root()
    candidate = (root / relpath).resolve()

    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Ruta fuera del vault: {relpath!r}")

    parts = candidate.relative_to(root).parts
    if parts[:1] == (RESERVED_DIR,):
        raise ValueError(f"Ruta reservada para uso interno del asistente: {relpath!r}")

    return candidate


def audit_log_path() -> Path:
    path = vault_root() / RESERVED_DIR / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_audit(tool: str, ruta: str, detail: str = "") -> None:
    entry = {"timestamp": time.time(), "tool": tool, "ruta": ruta, "detail": detail}
    with audit_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def backup_before_overwrite(target: Path) -> Path:
    """Guarda el contenido previo antes de sobrescribir, para que el cambio sea auditable/reversible."""
    backups_dir = vault_root() / RESERVED_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    relpath = target.relative_to(vault_root()).as_posix()
    stamp = int(time.time())
    backup_path = backups_dir / f"{relpath.replace('/', '__')}.{stamp}.bak.md"
    backup_path.write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
    return backup_path


async def buscar_nota(argumentos: dict, qdrant_client) -> dict:
    consulta = argumentos["consulta"]
    resultados = await retrieve(qdrant_client, consulta)
    return {
        "resultados": [
            {
                "ruta": (r.payload or {}).get("path"),
                "titulo": (r.payload or {}).get("title"),
                "encabezado": (r.payload or {}).get("heading"),
                "fragmento": ((r.payload or {}).get("text") or "")[:400],
            }
            for r in resultados
        ]
    }


async def crear_nota(argumentos: dict, qdrant_client) -> dict:
    ruta = argumentos["ruta"]
    contenido = argumentos["contenido"]

    if not ruta.endswith(".md"):
        return {"error": f"La ruta debe terminar en .md: {ruta!r}"}

    path = resolve_vault_path(ruta)
    if path.exists():
        return {"error": f"Ya existe una nota en '{ruta}'. Usá actualizar_nota si el objetivo es modificarla."}

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contenido, encoding="utf-8")
    append_audit("crear_nota", ruta)
    return {"ok": True, "ruta": ruta}


async def actualizar_nota(argumentos: dict, qdrant_client) -> dict:
    ruta = argumentos["ruta"]
    contenido = argumentos["contenido"]

    path = resolve_vault_path(ruta)
    if not path.is_file():
        return {"error": f"No existe una nota en '{ruta}'. Usá crear_nota si el objetivo es crearla."}

    backup_path = backup_before_overwrite(path)
    path.write_text(contenido, encoding="utf-8")
    append_audit("actualizar_nota", ruta, detail=f"backup en {backup_path.relative_to(vault_root()).as_posix()}")
    return {"ok": True, "ruta": ruta, "backup": backup_path.relative_to(vault_root()).as_posix()}


async def eliminar_tarea(argumentos: dict, qdrant_client) -> dict:
    """Borra una línea de tarea pendiente (`- [ ] ...`) de una nota, identificada por
    ruta + texto exacto (las tareas no tienen un id propio, ver `listar_tareas`).

    Solo borra tareas PENDIENTES a propósito (no `- [x]`): si el texto matchea una tarea ya
    hecha, se lo tratamos como no encontrada en vez de borrar contenido ya completado — pedir
    "eliminar" una tarea hecha probablemente sea un error del usuario/LLM, no la intención real.
    """
    ruta = argumentos["ruta"]
    texto = argumentos["texto"].strip()

    path = resolve_vault_path(ruta)
    if not path.is_file():
        return {"error": f"No existe una nota en '{ruta}'."}

    lineas = path.read_text(encoding="utf-8").splitlines(keepends=True)
    indice_objetivo = None
    for i, linea in enumerate(lineas):
        match = TASK_RE.match(linea)
        if not match or match.group(1).lower() == "x":
            continue
        if match.group(2).strip() == texto:
            indice_objetivo = i
            break

    if indice_objetivo is None:
        return {"error": f"No se encontró una tarea pendiente con el texto {texto!r} en '{ruta}'."}

    backup_path = backup_before_overwrite(path)
    del lineas[indice_objetivo]
    path.write_text("".join(lineas), encoding="utf-8")
    append_audit(
        "eliminar_tarea", ruta, detail=f"tarea eliminada: {texto!r}; backup en {backup_path.relative_to(vault_root()).as_posix()}"
    )
    return {"ok": True, "ruta": ruta, "texto": texto, "backup": backup_path.relative_to(vault_root()).as_posix()}


async def listar_tareas(argumentos: dict, qdrant_client) -> dict:
    solo_pendientes = bool(argumentos.get("solo_pendientes", False))
    root = vault_root()

    tareas = []
    for md_file in iter_markdown_files(root):
        relpath = md_file.relative_to(root).as_posix()
        for line in md_file.read_text(encoding="utf-8").splitlines():
            match = TASK_RE.match(line)
            if not match:
                continue
            hecha = match.group(1).lower() == "x"
            if solo_pendientes and hecha:
                continue
            tareas.append({"ruta": relpath, "texto": match.group(2).strip(), "hecha": hecha})

    return {"tareas": tareas}


def parse_task_date(match: re.Match[str] | None) -> date | None:
    """Devuelve una fecha válida; un texto que parece fecha pero es inválido queda sin calendarizar."""
    if match is None:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def task_dashboard_item(relpath: str, line_number: int, text: str, hecha: bool, today: date) -> dict:
    start_date = parse_task_date(TASK_START_RE.search(text))
    end_date = parse_task_date(TASK_END_RE.search(text))
    alerts: list[str] = []

    # Una fecha de vencimiento sin inicio es un hito de un día; así entra al Gantt sin
    # inventar duración. Si solo hay inicio, se muestra también como hito hasta que se defina fin.
    if start_date is None and end_date is not None:
        start_date = end_date
    elif start_date is not None and end_date is None:
        end_date = start_date
    elif start_date is not None and end_date is not None and start_date > end_date:
        alerts.append("La fecha de inicio es posterior a la fecha de vencimiento.")

    if hecha:
        status = "completada"
    elif end_date is None:
        status = "sin_fecha"
    elif end_date < today:
        status = "vencida"
    elif end_date == today:
        status = "hoy"
    else:
        status = "programada"

    title = TASK_METADATA_RE.sub("", text).strip() or text
    return {
        "id": f"{relpath}:{line_number}",
        "ruta": relpath,
        "texto": text,
        "titulo": title,
        "hecha": hecha,
        "progreso": 100 if hecha else 0,
        "fecha_inicio": start_date.isoformat() if start_date else None,
        "fecha_fin": end_date.isoformat() if end_date else None,
        "estado": status,
        "alertas": alerts,
    }


async def mostrar_dashboard_tareas(argumentos: dict, qdrant_client) -> dict:
    """Construye los datos del dashboard desde tareas Markdown, sin modificar el vault."""
    today = date.today()
    root = vault_root()
    tareas: list[dict] = []

    for md_file in iter_markdown_files(root):
        relpath = md_file.relative_to(root).as_posix()
        for line_number, line in enumerate(md_file.read_text(encoding="utf-8").splitlines(), start=1):
            match = TASK_RE.match(line)
            if not match:
                continue
            tareas.append(task_dashboard_item(relpath, line_number, match.group(2).strip(), match.group(1).lower() == "x", today))

    tareas.sort(key=lambda task: (task["fecha_fin"] is None, task["fecha_fin"] or "9999-12-31", task["ruta"], task["id"]))
    pendientes = [task for task in tareas if not task["hecha"]]
    return {
        "fecha_referencia": today.isoformat(),
        "tareas": tareas,
        "resumen": {
            "total": len(tareas),
            "pendientes": len(pendientes),
            "completadas": len(tareas) - len(pendientes),
            "vencidas": sum(task["estado"] == "vencida" for task in pendientes),
            "sin_fecha": sum(task["estado"] == "sin_fecha" for task in pendientes),
        },
    }
