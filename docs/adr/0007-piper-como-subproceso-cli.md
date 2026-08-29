# 0007 — Piper-TTS integrado como subproceso CLI, no como paquete pip

## Contexto
Para la Fase 5 hay dos formas razonables de integrar Piper-TTS al orchestrator:
1. El paquete `piper-tts` de PyPI (API Python nativa), que depende de `piper-phonemize` (extensión compilada que envuelve espeak-ng).
2. El binario `piper` (ejecutable standalone que publica el proyecto en sus releases de GitHub, con `espeak-ng-data` incluido), invocado como subproceso.

## Decisión
Opción 2: el orchestrator descarga/usa el binario `piper` como subproceso (`asyncio.create_subprocess_exec`), pasándole el texto por stdin y leyendo audio PCM crudo por stdout.

## Por qué
Esta sesión ya perdió tiempo real dos veces por depender de extensiones Python compiladas con compatibilidad frágil entre versiones de Python/plataforma (`ctranslate2` vía `faster-whisper` — ADR 0004/0005 — y, en menor medida, `webrtcvad` — ADR 0003). `piper-phonemize` tiene un historial similar de fragilidad de empaquetado (wheels específicas por plataforma, dependencia de datos de espeak-ng en rutas que a veces no se resuelven bien). Usar el binario standalone evita meter una cuarta pieza de ese mismo tipo de riesgo al proyecto: es un ejecutable autocontenido, sin `pip install` de por medio, sin sorpresas de versión de Python.

## Consecuencias
- Hay que descargar el binario y al menos una voz (`.onnx` + `.onnx.json`) manualmente antes de poder correr la Fase 5 — no es automático como el modelo de whisper (que se descarga solo la primera vez). Ver `models/README.md`.
- Cada síntesis de una oración es un proceso nuevo (`asyncio.create_subprocess_exec`), no una llamada a una librería ya cargada en memoria — hay overhead de arranque de proceso por oración. Para frases cortas esto es aceptable; si en la práctica el overhead por-proceso resulta significativo, se puede reconsiderar un modo "servidor" de Piper (mantenerlo corriendo y mandarle texto por stdin en un loop) en vez de un proceso por oración — no implementarlo antes de medir que hace falta.
- El empaquetado en Docker (Fase 8) va a necesitar bajar el binario + la voz dentro de la imagen — no resuelto todavía, deliberadamente fuera del alcance de la Fase 5 (que se valida vía script de prueba local, no vía Docker).
