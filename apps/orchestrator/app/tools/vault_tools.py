"""Ejecución real de las tools invocables por el LLM, sandboxeada al vault.

Todas las funciones tienen la misma firma `(argumentos: dict, qdrant_client) -> dict`
(aunque no todas usen `qdrant_client`) para que el dispatcher en `registry.py` las pueda
llamar de forma uniforme.
"""

import json
import re
import time
from pathlib import Path

from app.core.config import settings
from app.rag.chunking import iter_markdown_files
from app.rag.retriever import retrieve

RESERVED_DIR = ".asistente"  # carpeta interna: audit log + backups, nunca destino de una tool
TASK_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+)$")


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
