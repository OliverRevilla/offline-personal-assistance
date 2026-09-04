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

## Adenda: dónde viven los archivos (no es lo mismo que dónde corre el proceso)
Esta decisión original solo cubrió *dónde corre el proceso* (Windows nativo) y asumió implícitamente que eso resolvía el acceso a los archivos — no es así, porque el repo entero vive en el filesystem de WSL2 (ruta Linux, ej. `/home/<usuario>/.../offline-personal-assistance`), no en el filesystem nativo de Windows.

Opciones consideradas:
1. **Clon separado en NTFS nativo de Windows**: rápido y sin rarezas para `npm`/`cargo`, pero implica dos checkouts del mismo repo que hay que mantener sincronizados (pull en ambos lados).
2. **Acceder al mismo checkout de WSL2 desde Windows vía `\\wsl.localhost\<distro>\...`**: un solo checkout, sin nada que sincronizar — pero `npm`/`cargo` corriendo contra esa ruta de red (protocolo 9P) son conocidos por ser más lentos que sobre NTFS nativo, y hay reportes de rarezas de permisos/symlinks/file-watching en ese cruce específico.

**Decisión**: opción 2, confirmada explícitamente con el usuario — prioriza un solo checkout por sobre la performance/robustez máxima. Si en la práctica `npm install`/`cargo build`/el hot-reload de `next dev` resultan demasiado lentos o dan problemas raros de permisos, ese es el momento de reconsiderar y migrar a la opción 1 — no antes.

## Adenda 2: `npm run tauri dev` no reconocía el proyecto — causa real y fix
Síntoma: `tauri dev` fallaba con `Couldn't recognize the current folder as a Tauri project` **a pesar de que `src-tauri/tauri.conf.json` existía** exactamente donde debía. Mapear la ruta UNC a una letra de unidad con `net use` no lo resolvió (`\\wsl.localhost\...` no es un recurso SMB real, es un proveedor de filesystem especial de WSL — `net use` no lo trata como una unidad de red genuina para este propósito).

**Causa real, confirmada**: `npm` en Windows corre los scripts de `package.json` a través de `cmd.exe` por default, y `cmd.exe` **rechaza explícitamente** una ruta UNC como su directorio actual — cae de vuelta a `C:\Windows` en silencio (con un aviso en stderr que es fácil no ver: *"CMD.EXE se inició con esta ruta como el directorio actual. No se permiten rutas UNC. Regresando de manera predeterminada al directorio Windows."*). El binario de `tauri` arranca heredando ese `cwd` equivocado (`C:\Windows`), no `apps\desktop` — por eso "no encuentra" el proyecto.

**Fix intentado**: `apps/desktop/.npmrc` con `script-shell=powershell.exe` (se mantiene en el repo, no está de más). **No fue suficiente** — el error persistió. Hipótesis no confirmada de por qué: `tauri-cli` probablemente invoca sus propios comandos internos (ej. `beforeDevCommand`) shell-eando vía `cmd.exe` directamente desde el binario Rust, sin pasar por la configuración de `script-shell` de npm en absoluto — `script-shell` solo controla cómo *npm mismo* corre *sus* scripts, no lo que hace un binario de terceros invocado desde ahí. No se investigó más a fondo el mecanismo exacto porque apareció una salida más simple y definitiva (adenda 3).

## Adenda 3: decisión final — migrar a un clon separado en NTFS nativo
Con la adenda 2 confirmando que el problema es estructural (`cmd.exe` rechazando UNC como `cwd`, en más de un punto de la cadena de invocación) y no un detalle puntual arreglable con una config, se cumplió el criterio que la adenda 1 ya había dejado escrito para este caso exacto: **migrar a la opción 1**.

Decisión final, confirmada con el usuario: `apps/desktop` (y en la práctica, el repo completo, por simplicidad de no armar un sparse-checkout) se clona **también** en el filesystem nativo de Windows (NTFS), en una ruta normal como `C:\Users\<usuario>\proyectos\offline-personal-assistance`. El checkout de WSL2 sigue siendo el único que se usa para el backend — nada de eso cambia. Consecuencia operativa real: a partir de ahora hay **dos checkouts que sincronizar** cuando cambia algo que afecta a ambos lados (sobre todo `docs/ARCHITECTURE.md`, el protocolo WS, y cualquier archivo de `apps/desktop`) — hacer `git pull` en los dos lugares, no asumir que uno se actualiza solo por actualizar el otro.

## Consecuencias
- Instalar Node.js + Rust + Tauri CLI **en Windows**, no en la WSL2 donde vive el backend — un entorno de desarrollo más para el proyecto, documentado por separado en `GUIDE.md`.
- ~~Los íconos de la app no hacen falta para `tauri dev`, solo para `tauri build`~~ — **corregido**: en Windows, `icon.ico` hace falta para *cualquier* compilación (dev incluida), porque el build de Rust genera un recurso de Windows embebido en el `.exe` siempre. `src-tauri/icons/` ya tiene placeholders reales (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.ico`) generados a mano para no bloquear esta fase — falta `icon.icns` (macOS) para la Fase 8.
- Las versiones exactas de Next.js/Tauri/React en `package.json` están ancladas por mayor (`^15`, `^2`, `^19`) con la mejor información disponible al escribir esto — si `npm install` resuelve algo con un schema/API distinto al esperado (más probable en Tauri, cuyo `tauri.conf.json` es sensible a la versión), no asumas que el código está mal: compará contra la versión real instalada primero.
