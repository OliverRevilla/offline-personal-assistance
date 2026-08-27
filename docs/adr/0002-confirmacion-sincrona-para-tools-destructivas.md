# 0002 — Confirmación síncrona in-turn para tools destructivas

## Contexto
La Fase 3 requiere que operaciones destructivas (hoy: `actualizar_nota`, que sobrescribe el contenido de una nota existente) no se ejecuten sin que el usuario las apruebe explícitamente.

## Opciones consideradas
1. **Confiar en el prompt**: pedirle al LLM en el system prompt que pregunte "¿confirmás?" en el texto y no invoque la tool hasta la siguiente respuesta del usuario. Simple, pero frágil: depende de que el modelo respete la instrucción de forma consistente, y no hay garantía real — el LLM podría invocar la tool igual.
2. **Confirmación síncrona a nivel de protocolo**: cuando el LLM invoca una tool marcada como destructiva, el servidor pausa ese turno, le pide confirmación explícita al cliente por WS (`confirmacion_requerida` / `confirmacion_respuesta`), y solo ejecuta si el usuario aprueba.
3. **Cola de aprobaciones asíncrona**: las tools destructivas quedan "pendientes" y se aprueban desde otra parte de la UI en cualquier momento, no bloqueante.

## Decisión
Opción 2, implementada en `apps/orchestrator/app/api/ws.py` (función `pedir_confirmacion`).

## Consecuencias
- La garantía de "no se ejecuta sin aprobación" vive en el servidor, no depende de que el LLM se comporte bien — el peor caso si el modelo "alucina" que ya preguntó es que el usuario ve un prompt de confirmación de todos modos.
- El turno de WS queda bloqueado esperando la respuesta del usuario mientras hay una confirmación pendiente; esto es aceptable para un asistente mono-usuario y síncrono, pero **no va a escalar** si en el futuro se agrega interacción por voz simultánea a la de texto sin coordinarlo (la Fase 5-6 debería decidir explícitamente cómo se pide esta confirmación por voz, no asumir que el patrón de texto se traslada igual).
- La opción 3 (cola asíncrona) se descartó por ahora por ser una complejidad de UI que no está justificada en esta escala (un solo usuario, un solo turno a la vez). Reconsiderar si en algún momento se soportan operaciones destructivas de larga duración que no tenga sentido bloquear el turno completo.
