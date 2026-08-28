# 0005 — `pkg_resources` faltante: no es un problema de versión de Python

## Contexto
El ADR 0004 asumía que el `ModuleNotFoundError: pkg_resources` al levantar el orchestrator era por `ctranslate2` (dependencia de `faster-whisper`) sin wheels para una versión de Python demasiado nueva (3.14). Esa hipótesis quedó **refutada**: downgradeando a Python 3.12, el mismo error persiste, tanto con `uvicorn --reload` como sin él (lo cual también descarta que fuera un problema específico del subproceso que crea el reload en Windows).

Diagnóstico corregido: `pkg_resources` es parte de `setuptools`, y desde hace varias versiones el módulo `venv` de Python **ya no instala `setuptools`/`wheel` por defecto** al crear un entorno virtual nuevo (antes lo hacía vía `ensurepip`). Esto aplica tanto a 3.12 como a 3.13/3.14 — por eso bajar la versión de Python no cambió nada. Si `ctranslate2` (u otra dependencia transitiva) todavía hace `import pkg_resources` en tiempo de ejecución, y el venv no tiene `setuptools` instalado, revienta con exactamente este error, sea cual sea la versión de Python.

Ya se había agregado `"setuptools>=68"` a `apps/orchestrator/pyproject.toml` como dependencia real del proyecto (no solo en `[build-system] requires`, que no alcanza — ver commit anterior). Si el error sigue apareciendo en la máquina de pruebas después de eso, la explicación más probable no es que la librería esté ausente del `pyproject.toml`, sino que **el venv donde se está probando no tiene ese cambio instalado todavía** — porque el fix se commiteó/pusheó desde esta máquina pero no se confirmó que se haya hecho `pull` + reinstalado (`pip install -e ".[dev]"`) en un venv realmente limpio en la máquina de pruebas. El propio usuario reportó "muchos procesos involucrados de site-packages", consistente con un entorno con restos de instalaciones previas (Python 3.14 desinstalado, venvs viejos, etc.).

## Decisión
1. Mantener `setuptools` como dependencia real del proyecto, pero con un techo de versión conservador (`>=68,<76`) en vez de sin límite superior — hay riesgo real de que versiones muy nuevas de `setuptools` reduzcan o rompan la superficie de `pkg_resources` (viene siendo deprecado activamente en el ecosistema hace años); no vale la pena arriesgarse a que "la última versión disponible" sea justamente una que ya no sirva para este propósito.
2. Antes de tocar código de nuevo, verificar con un **smoke test aislado** (sin FastAPI, sin uvicorn) que el venv de la máquina de pruebas realmente tiene `pkg_resources` disponible, para separar "problema de entorno/instalación" de "problema de código":
   ```powershell
   # con el venv (recién recreado) activado:
   python -c "import pkg_resources; print(pkg_resources.__file__)"
   python -c "import faster_whisper; print('ok')"
   ```
   Si el primer comando ya falla, es 100% un problema de instalación del venv (no de nuestro código) — solución: `pip install "setuptools<76"` ahí mismo, o recrear el venv desde cero.
3. Procedimiento de "entorno limpio" recomendado en la máquina de pruebas, para eliminar cualquier resto de Python 3.14 / venvs viejos de la ecuación:
   ```powershell
   cd apps/orchestrator
   Remove-Item -Recurse -Force .venv    # borrar el venv entero, no reusarlo
   py -3.12 -m venv .venv
   .venv\Scripts\activate
   python -c "import sys; print(sys.executable)"   # confirmar que apunta DENTRO de .venv
   pip install -e ".[dev]" -v
   python -c "import pkg_resources; print('setuptools ok')"
   uvicorn app.main:app
   ```

## Consecuencias
- Si el smoke test del paso 2 falla incluso en un venv recién creado con la dependencia de `setuptools` ya en `pyproject.toml`, el problema no es de este repo sino del propio Python/pip de esa máquina (instalación corrupta, `PATH` apuntando a otro intérprete, etc.) — ahí ya no corresponde seguir cambiando dependencias del proyecto a ciegas.
- No se reemplaza `faster-whisper`/`ctranslate2` por otra librería todavía: no hay evidencia de que el problema esté en esa librería en sí, solo en que el entorno no tiene lo que esa librería necesita. Cambiar de librería sin confirmar esto sería resolver el síntoma equivocado.
