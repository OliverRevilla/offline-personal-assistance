# 0008 — Frontend nativo en Windows + stack Tauri/Next.js para la Fase 6

## Contexto
El backend está estandarizado a WSL2 (ADR 0006) para evitar el tipo de incidente de "dos instancias del mismo servicio" que ya costó tiempo real (Ollama). El frontend Tauri es distinto en naturaleza: es un proceso separado que le habla al backend por red (WebSocket a `ws://localhost:8000/ws/chat`), no un servicio que pueda duplicarse de la misma forma. Pero es una app de escritorio con GUI real y captura de micrófono — dos cosas donde WSL2 depende de WSLg, cuyo soporte de audio/mic es notablemente menos maduro que en Windows nativo.

## Decisión
El frontend (Node.js, Rust/Cargo, Tauri CLI) corre **nativo en Windows**, no dentro de WSL2. El backend sigue en WSL2 sin cambios. La conexión WS cruza ese límite vía el port forwarding de WSL2 (`localhost:8000` desde Windows llega al backend en WSL2 sin configuración adicional, tal como ya se documentó para probar Ollama).

Confirmado explícitamente con el usuario antes de implementar (no es una decisión unilateral): dado el historial de esta sesión con problemas de entorno (`pkg_resources`, dos Ollama, versión de Python), el riesgo de WSLg-para-audio no valía la pena para una fase que ya tiene bastante superficie nueva (Node/Rust/Tauri) por sí sola.

## Stack elegido
- **Next.js** (App Router) con `output: 'export'` — se compila a HTML/JS/CSS estático, sin servidor Node en runtime. Tauri sirve ese `out/` estático desde su webview.
- **Tauri 2.x**: sin comandos Rust custom ni plugins — todo lo que necesita esta fase (WebSocket, `getUserMedia`, Web Audio API) son Web APIs estándar que el webview ya resuelve solo, sin pasar por el puente de Tauri. El `src-tauri/` es prácticamente el scaffold default.
- **Captura y reproducción de audio**: `AudioWorklet` (no `ScriptProcessorNode`, deprecado) — un procesador para capturar el mic y convertir a PCM16, otro para reproducir el audio entrante en cola. `AudioContext({ sampleRate: 16000 })` para la captura, delegando el resampling del hardware al navegador (Chromium/WebView2 lo soporta).
- **Sin librería de estado/UI adicional** (nada de Redux/Zustand/Tailwind): la complejidad de esta pantalla no lo justifica — `useState`/`useRef` de React alcanzan.
- **Contrato del protocolo WS duplicado a mano** en `src/lib/protocol.ts` (TypeScript), no generado desde el lado Python. `packages/shared-contracts/` sigue vacío a propósito — recién se justifica el codegen si el protocolo diverge en la práctica y causa un bug real, no antes.

## Consecuencias
- Instalar Node.js + Rust + Tauri CLI **en Windows**, no en la WSL2 donde vive el backend — un entorno de desarrollo más para el proyecto, documentado por separado en `GUIDE.md`.
- Los íconos de la app (`src-tauri/icons/`) no existen todavía — no hacen falta para `tauri dev`, pero si son necesarios para `tauri build` (Fase 8, empaquetado). No bloquea esta fase.
- Las versiones exactas de Next.js/Tauri/React en `package.json` están ancladas por mayor (`^15`, `^2`, `^19`) con la mejor información disponible al escribir esto — si `npm install` resuelve algo con un schema/API distinto al esperado (más probable en Tauri, cuyo `tauri.conf.json` es sensible a la versión), no asumas que el código está mal: compará contra la versión real instalada primero.
