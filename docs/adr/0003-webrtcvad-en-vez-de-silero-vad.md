# 0003 — webrtcvad en vez de Silero VAD

## Contexto
El stack original pedido para el proyecto especificaba "Silero VAD" como filtro de detección de voz para el pipeline de STT (Fase 4). Al implementarlo, la vía más directa para usar Silero VAD en streaming (`VADIterator` del paquete `silero-vad`) depende de `torch` como contenedor de tensores, incluso cuando el modelo en sí corre razonablemente liviano. `torch` sería, de lejos, la dependencia más pesada de todo el proyecto — nada más en el orchestrator lo necesita hoy (ni siquiera `faster-whisper`, que usa `ctranslate2`, no `torch`).

## Opciones consideradas
1. **Silero VAD + torch**: mejor calidad de detección (más robusto con ruido de fondo), pero agrega cientos de MB de dependencia y una superficie de API sobre la que había incertidumbre real (no se pudo verificar en el momento si la variante "sin torch" funciona igual en streaming).
2. **webrtcvad**: bindings livianos en C (sin modelos que descargar, sin torch), muy probado en asistentes de voz en tiempo real (ej. Home Assistant Voice). Algo menos preciso que Silero en audio ruidoso.

## Decisión
Opción 2 (`webrtcvad`), confirmada explícitamente por el usuario — se le presentó el trade-off en vez de decidirlo unilateralmente, dado que "Silero VAD" era una elección explícita del stack original.

## Consecuencias
- Implementado en `apps/orchestrator/app/stt/vad_segmenter.py`: ring buffer + umbrales de disparo/corte (90% voz para empezar, 90% silencio para terminar), el patrón clásico del ejemplo de `py-webrtcvad`.
- Sin dependencia de `torch` en el orchestrator. Si en la práctica el recall de `webrtcvad` no alcanza (ej. mucho ruido de fondo, usuario susurrando), reconsiderar Silero VAD en una revisión de este ADR — no cambiarlo por las dudas antes de tener evidencia real de un problema.
- Nada de esto afecta la elección de faster-whisper para la transcripción en sí, que se mantiene sin cambios.
