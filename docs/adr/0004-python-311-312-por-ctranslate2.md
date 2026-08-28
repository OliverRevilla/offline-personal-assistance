# 0004 — Fijar el orchestrator a Python 3.11-3.12

> **Actualización (refutada parcialmente):** el usuario downgradeó a Python 3.12 y el mismo `ModuleNotFoundError: pkg_resources` persistió, tanto con `uvicorn --reload` como sin él. Eso descarta la hipótesis de "ctranslate2 sin wheels para una versión de Python demasiado nueva" como causa raíz — 3.12 tiene soporte maduro de sobra. El tope de versión (`<3.13`) se mantiene por prudencia general, pero **no es el fix** de este error. Ver [ADR 0005](0005-pkg-resources-pin-setuptools.md) para el diagnóstico corregido.

## Contexto
Probando el proyecto en una máquina con Python 3.14 recién instalado, `uvicorn app.main:app --reload` falla con `ModuleNotFoundError: pkg_resources` dentro del subproceso que crea el reloader (`SpawnProcess-1`). Instalar `setuptools` en el venv no lo resuelve.

`faster-whisper` depende de `ctranslate2`, una extensión compilada en C++ (pybind11) que publica wheels precompiladas por versión de CPython. Históricamente tarda varios meses en soportar una versión nueva de Python después de su release. Python 3.14 es demasiado reciente como para asumir que ya hay wheels compatibles — el error de `pkg_resources` es plausible que sea un síntoma secundario de una instalación de `ctranslate2` incompleta/incompatible, no la causa raíz.

No se pudo diagnosticar con el traceback completo en el momento: el entorno donde se desarrolla el repo (laptop corporativa) no es el mismo donde se prueba (otra PC, con Python 3.14), así que no había forma de correr el import directamente y confirmar la hipótesis con certeza.

## Decisión
Fijar `requires-python = ">=3.11,<3.13"` en `apps/orchestrator/pyproject.toml` — es decir, Python 3.11 o 3.12 para el venv del orchestrator. Son las versiones en las que `faster-whisper`/`ctranslate2` tienen soporte confirmado y maduro.

## Consecuencias
- En la máquina de testeo (Python 3.14 instalado), hay que crear el venv apuntando explícitamente a un intérprete 3.11/3.12 en vez del `python`/`py` por defecto — con el launcher de Windows: `py -3.12 -m venv .venv` (requiere tener Python 3.12 instalado además del 3.14; si no está, instalarlo desde python.org o `winget install Python.Python.3.12`).
- Si en el futuro se confirma que `ctranslate2` ya publica wheels para una versión más nueva de Python (chequear su changelog/PyPI antes de asumirlo), se puede subir el tope en este mismo archivo — no antes.
- Este ADR quedó escrito sin haber visto el traceback completo (ver Contexto) — es la hipótesis más probable, no una certeza confirmada. Si al recrear el venv con Python 3.12 el error persiste, hay que reabrir el diagnóstico desde cero en vez de asumir que esta fue la causa.
