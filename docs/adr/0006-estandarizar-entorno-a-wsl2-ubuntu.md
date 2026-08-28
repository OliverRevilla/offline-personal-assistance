# 0006 — Estandarizar el entorno de desarrollo/testing a WSL2 Ubuntu

## Contexto
Una sesión completa de debugging (`ModuleNotFoundError: pkg_resources`, después `model not found` en Ollama) terminó rastreándose a una causa de fondo distinta a cualquiera de las hipótesis técnicas que se probaron primero (versión de Python, `setuptools`, nombre del modelo): **había dos instalaciones de Ollama corriendo en paralelo** — una nativa en Windows (probada manualmente desde PowerShell, con el modelo LLM ya descargado) y otra dentro de WSL2 (donde realmente corre `uvicorn`/el orchestrator, sin el modelo descargado ahí). Ambas responden en `localhost:11434` porque cada una vive en su propio namespace de red (Windows vs. la VM de WSL2), así que "anda desde PowerShell" y "no anda desde el proceso real" no eran contradictorios — eran, literalmente, dos backends distintos.

Lo mismo aplicaba de fondo al script de setup: `scripts/setup.ps1` (pensado para un escenario Windows-nativo puro) terminó pulleando el modelo del lado equivocado sin que nada lo señalara como error.

Documentar la versión de Python (ADR 0004) o pinnear `setuptools` (ADR 0005) fueron correcciones válidas en su momento, pero no atacaban la causa real: **tener dos entornos de ejecución candidatos (Windows nativo y WSL2) sin que estuviera decidido y documentado cuál es "el" entorno real de desarrollo/testing** invita exactamente a este tipo de bug fantasma, difícil de diagnosticar porque cada mitad del sistema parece funcionar por separado.

## Decisión
El entorno de desarrollo y testing local del orchestrator es **WSL2 con Ubuntu**, sin ambigüedad. Esto significa:
- `uvicorn`, el venv de Python, y **Ollama** corren todos dentro de la misma instancia de WSL2 — nunca mezclados con instalaciones nativas de Windows para las mismas piezas.
- Los comandos de referencia en `GUIDE.md` y los READMEs son de shell POSIX (bash), pensados para correr dentro de WSL2. Los equivalentes de PowerShell quedan solo como nota secundaria, marcados explícitamente para el caso de no usar WSL2 en absoluto (no para "a veces uno, a veces el otro").
- `scripts/setup.ps1` se mantiene pero con una advertencia explícita: usarlo implica que TODO el resto del stack (Ollama incluido) también corre nativo en Windows, no una mezcla.
- Docker Desktop con integración WSL2 sigue siendo válido para los contenedores (Qdrant, y opcionalmente Ollama vía `docker-compose.yml`), pero los comandos de `docker compose` se corren desde dentro de WSL2, no desde PowerShell, para evitar cualquier ambigüedad de qué "lado" está hablando con qué.

## Consecuencias
- Si en algún momento se necesita soporte real de desarrollo Windows-nativo (sin WSL2) además de WSL2, tiene que ser un modo explícito y documentado por separado — no una mezcla implícita como la que causó este incidente.
- Cualquier instrucción nueva en `GUIDE.md`/READMEs que mencione un comando de Windows nativo junto a uno de WSL2/Linux para el mismo paso debe dejar clarísimo que son alternativas **excluyentes**, no intercambiables a mitad de flujo.
- No resuelve el caso de alguien queriendo GPU en Windows puro sin WSL2 (ver `docs/ARCHITECTURE.md`, ya advertía que Ollama en Docker no ve la GPU sin WSL2 de por medio) — para ese caso, todo el flujo tendría que ser 100% nativo Windows, sin ningún WSL2 de por medio tampoco.
