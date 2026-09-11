import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from app.core.config import settings
from app.tools import vault_tools

logger = logging.getLogger(__name__)

ToolExecutor = Callable[[dict, object], Awaitable[dict]]

TOOL_EXECUTORS: dict[str, ToolExecutor] = {
    "buscar_nota": vault_tools.buscar_nota,
    "crear_nota": vault_tools.crear_nota,
    "actualizar_nota": vault_tools.actualizar_nota,
    "listar_tareas": vault_tools.listar_tareas,
    "mostrar_dashboard_tareas": vault_tools.mostrar_dashboard_tareas,
    "eliminar_tarea": vault_tools.eliminar_tarea,
}

# Únicas tools que sobrescriben o borran contenido existente: requieren confirmación explícita
# del usuario antes de ejecutarse (ver docs/ARCHITECTURE.md, protocolo de confirmación).
DESTRUCTIVE_TOOLS = {"actualizar_nota", "eliminar_tarea"}


def load_tool_schemas() -> list[dict]:
    tools_dir = Path(settings.tools_schema_dir)
    if not tools_dir.is_dir():
        raise FileNotFoundError(
            f"No se encontró el directorio de schemas de tools en {tools_dir.resolve()} "
            "(configurable vía TOOLS_SCHEMA_DIR, ver .env.example)."
        )
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(tools_dir.glob("*.json"))]


TOOL_SCHEMAS = load_tool_schemas()


def is_destructive(name: str) -> bool:
    return name in DESTRUCTIVE_TOOLS


async def run_tool(name: str, arguments: dict, qdrant_client) -> dict:
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return {"error": f"Herramienta desconocida: {name!r}"}
    try:
        return await executor(arguments, qdrant_client)
    except Exception as exc:  # noqa: BLE001 - el error vuelve al LLM como tool_result, no tumba el turno
        logger.exception("Fallo ejecutando la tool %s", name)
        return {"error": str(exc)}
