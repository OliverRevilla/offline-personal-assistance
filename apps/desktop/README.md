# apps/desktop

App de escritorio: Tauri (shell nativo, webview del sistema) + Next.js/React (UI, exportada estática). Captura de micrófono, reproducción de audio en streaming (`AudioWorklet`), UI de conversación, cliente WebSocket hacia `apps/orchestrator`.

Owner: `frontend-engineer`. Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS y [docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md](../../docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md) para las decisiones de esta fase.

## Dónde corre esto

**El proceso** (Node/npm/Tauri) corre **nativo en Windows** — no dentro de WSL2 (a diferencia del backend). El backend sigue viviendo en WSL2 sin cambios; este frontend le habla por WebSocket a `ws://localhost:8000/ws/chat`, que WSL2 expone solo hacia Windows. Ver el ADR 0008 para el porqué.

**Los archivos**, en cambio, siguen viviendo en el filesystem de WSL2 (es el mismo checkout del repo, no uno separado) — el frontend nativo de Windows los accede vía la ruta de red `\\wsl.localhost\<distro>\...` (ver la adenda del ADR 0008 para el trade-off de esta elección vs. clonar el repo también en NTFS nativo). Esto es más lento que trabajar sobre NTFS nativo — es esperable que `npm install`/`cargo build` tarden más de lo que tardarían en Windows puro, no es un signo de que algo esté mal.

## Requisitos (en Windows, no en WSL2)

- Node.js LTS (18+).
- Rust + Cargo ([rustup.rs](https://rustup.rs)).
- **Toolchain de C++ de Visual Studio** (Visual Studio Installer → workload "Desktop development with C++", o los "Build Tools for Visual Studio" standalone si no querés el IDE completo) — Tauri necesita esto para compilar la parte de Rust en Windows. Sin esto, `npm run tauri dev`/`cargo build` fallan con errores de linker (`link.exe not found` o similares), no con un error de nuestro código.
- Tauri CLI: se instala como dependencia de desarrollo (`@tauri-apps/cli`, ya en `package.json`), no hace falta instalarlo global.
- En Windows, Tauri usa WebView2 (viene preinstalado en Windows 10/11 actualizados; si falta, el instalador de Tauri/Edge lo resuelve).

## Cómo correr

Primero encontrá la ruta de red a tu repo (desde PowerShell, para saber el nombre exacto de tu distro):

```powershell
wsl -l -v
```

Y desde dentro de WSL2, la ruta absoluta del repo (`pwd` parado en la raíz del repo). Combinás ambas cosas en `\\wsl.localhost\<DistroName>\<ruta-absoluta-de-pwd>`. Por ejemplo, si `wsl -l -v` dice `Ubuntu` y `pwd` dice `/home/tu-usuario/proyectos/offline-personal-assistance`:

```powershell
cd \\wsl.localhost\Ubuntu\home\tu-usuario\proyectos\offline-personal-assistance\apps\desktop
npm install
copy .env.local.example .env.local
npm run tauri dev
```

(Si tu Windows es más viejo y `\\wsl.localhost\` no resuelve, probá `\\wsl$\` en su lugar — es el alias anterior, debería apuntar a lo mismo.)

**Nota sobre `.npmrc`**: este directorio incluye un `.npmrc` con `script-shell=powershell.exe` — sin eso, `npm run tauri dev` falla con `Couldn't recognize the current folder as a Tauri project` porque `npm` en Windows corre los scripts vía `cmd.exe` por default, y `cmd.exe` rechaza una ruta UNC como directorio actual (cae a `C:\Windows` en silencio). Ver la adenda 2 de `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md` para el detalle completo — ya está resuelto en el repo, no hace falta que hagas nada extra, pero si alguna vez ves ese error de nuevo, es lo primero a revisar.

**Si el hot-reload de `next dev` no detecta tus cambios** (guardás un archivo y la ventana no se actualiza sola): es un síntoma conocido del file-watching nativo de Windows cruzando al filesystem de WSL2 por la ruta de red. Como workaround, parar y volver a correr `npm run tauri dev` después de cada cambio suele alcanzar mientras se prueba esto; si se vuelve molesto de verdad, ese es el momento de reconsiderar el clon separado en NTFS nativo (ver la adenda del ADR 0008), no antes.

Esto levanta `next dev` (vía `beforeDevCommand` en `tauri.conf.json`) y abre la ventana de Tauri apuntando a `http://localhost:3000`. Requiere que el backend (`apps/orchestrator`, en WSL2) ya esté corriendo — ver la raíz de `GUIDE.md`.

## Estado actual (Fase 7 del roadmap)

Todo lo de las fases 1-5 (texto, RAG, tool calling con confirmación, voz de entrada y salida) con una UI real: conversación en pantalla, botón de micrófono, reproducción de audio, y la barra de confirmación para operaciones destructivas (`actualizar_nota`). El cliente WS (`src/lib/ws-client.ts`) reconecta solo con backoff exponencial si se cae la conexión, y avisa en la UI que el contexto de la conversación anterior se perdió.

No incluye todavía: empaquetado/instalador (Fase 8 — íconos de la app tampoco existen aún, ver `src-tauri/icons/README.md`), ni ningún comando Rust custom (no hace falta ninguno para esta fase).
