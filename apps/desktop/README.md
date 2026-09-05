# apps/desktop

App de escritorio: Tauri (shell nativo, webview del sistema) + Next.js/React (UI, exportada estática). Captura de micrófono, reproducción de audio en streaming (`AudioWorklet`), UI de conversación, cliente WebSocket hacia `apps/orchestrator`.

Owner: `frontend-engineer`. Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS y [docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md](../../docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md) para las decisiones de esta fase.

## Dónde corre esto

**El proceso** (Node/npm/Tauri) corre **nativo en Windows** — no dentro de WSL2 (a diferencia del backend). El backend sigue viviendo en WSL2 sin cambios; este frontend le habla por WebSocket a `ws://localhost:8000/ws/chat`, que WSL2 expone solo hacia Windows. Ver el ADR 0008 para el porqué.

**Los archivos**: el repo está clonado **dos veces** — una en WSL2 (la que usás para el backend) y otra en el filesystem nativo de Windows (NTFS), solo para trabajar acá. No es el mismo checkout accedido por dos lados: se probó eso primero (vía `\\wsl.localhost\<distro>\...`) y se abandonó, porque `cmd.exe` en Windows rechaza estructuralmente una ruta UNC como directorio de trabajo de un proceso — rompía `npm run tauri dev` de una forma que no tenía un fix limpio. Ver las adendas 2 y 3 de `docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md` para el detalle completo de por qué se descartó esa vía.

**Esto significa que tenés que mantener sincronizados los dos checkouts**: cualquier cambio que afecte a `apps/desktop`, `docs/ARCHITECTURE.md`, o el protocolo WS, necesita `git pull` en **ambos** lados — el de WSL2 y este clon de Windows. No asumas que actualizar uno actualiza el otro.

## Requisitos (en Windows, no en WSL2)

- Node.js LTS (18+).
- Rust + Cargo ([rustup.rs](https://rustup.rs)).
- **Toolchain de C++ de Visual Studio** (Visual Studio Installer → workload "Desktop development with C++", o los "Build Tools for Visual Studio" standalone si no querés el IDE completo) — Tauri necesita esto para compilar la parte de Rust en Windows. Sin esto, `npm run tauri dev`/`cargo build` fallan con errores de linker (`link.exe not found` o similares), no con un error de nuestro código.
- Tauri CLI: se instala como dependencia de desarrollo (`@tauri-apps/cli`, ya en `package.json`), no hace falta instalarlo global.
- En Windows, Tauri usa WebView2 (viene preinstalado en Windows 10/11 actualizados; si falta, el instalador de Tauri/Edge lo resuelve).

## Cómo correr

**Primera vez — cloná el repo también en Windows nativo** (desde PowerShell, en una carpeta cualquiera de tu NTFS):

```powershell
cd C:\Users\<tu-usuario>\proyectos    # o donde prefieras, en un disco/carpeta nativa de Windows
git clone \\wsl.localhost\Ubuntu\home\<tu-usuario>\ruta\a\offline-personal-assistance offline-personal-assistance
```

(Ajustá la distro y la ruta de origen a la tuya — `wsl -l -v` te confirma el nombre exacto de la distro. Si tenés el repo también en un remoto tipo GitHub, clonar desde ahí en vez de desde la ruta de WSL2 funciona igual de bien.)

Desde ahí en adelante, todo el trabajo de frontend es en este clon de Windows — **no** en la ruta `\\wsl.localhost\...`:

```powershell
cd C:\Users\<tu-usuario>\proyectos\offline-personal-assistance\apps\desktop
npm install
copy .env.local.example .env.local
npm run tauri dev
```

Esto levanta `next dev` (vía `beforeDevCommand` en `tauri.conf.json`) y abre la ventana de Tauri apuntando a `http://localhost:3000`. Requiere que el backend (`apps/orchestrator`, en WSL2, en el *otro* checkout) ya esté corriendo — ver la raíz de `GUIDE.md`.

**Cada vez que cambie algo en `apps/desktop` (o en el protocolo WS)**: `git pull` en este clon de Windows también, no solo en el de WSL2 — son dos checkouts independientes ahora (ver "Dónde corre esto" arriba).

## Estado actual (Fase 7 del roadmap)

Todo lo de las fases 1-5 (texto, RAG, tool calling con confirmación, voz de entrada y salida) con una UI real: conversación en pantalla, botón de micrófono, reproducción de audio, y la barra de confirmación para operaciones destructivas (`actualizar_nota`). El cliente WS (`src/lib/ws-client.ts`) reconecta solo con backoff exponencial si se cae la conexión, y avisa en la UI que el contexto de la conversación anterior se perdió.

**Input y salida de voz/texto, independientes**: podés escribir o hablar indistintamente en cualquier momento (el botón 🎙️ no bloquea la caja de texto ni viceversa). La salida sí es un toggle explícito — el botón 🔊/🔇 en la barra de entrada apaga/prende que el asistente hable; con la voz apagada, el backend ni siquiera sintetiza audio para esa conexión (no es solo silenciar del lado del cliente).

**Escucha por defecto + bola de estado**: al abrir la app se pide permiso de mic automáticamente (sin ningún click) y el asistente saluda por voz ("Oliver, ¿cómo estás?..."), sea la primera conexión o una reconexión. Arriba de la conversación hay una bola de estado (`assistant-ball` en `globals.css`) que refleja qué está pasando: celeste y reactiva al volumen del mic mientras escucha, violeta pulsando mientras el LLM piensa, verde pulsando mientras suena la voz del asistente, gris fija en modo teclado, roja si se cayó la conexión. Decir la frase **"todo por teclado"** apaga el mic (el server lo detecta en la transcripción, confirma por voz, y el cliente corta la captura) — no hay frase inversa: para volver a modo voz hay que tocar el botón 🎙️ o reabrir la app, es una decisión de producto documentada en `docs/ARCHITECTURE.md` (sección 3.1), no una limitación técnica.

⚠️ **Riesgo conocido de eco/feedback**: no hay cancelación de eco acústico (AEC). Si usás parlantes en vez de auriculares, el mic puede llegar a captar la propia voz del asistente. Hay una mitigación parcial del lado del cliente (se deja de mandar audio al server mientras hay audio de salida sonando), pero no es una solución completa — con parlantes, preferí mantener el volumen bajo o usar auriculares.

No incluye todavía: empaquetado/instalador real (Fase 8 — los íconos actuales son placeholders generados a mano, ver `src-tauri/icons/README.md`; resultaron necesarios para `tauri dev` en Windows, no solo para `tauri build` como se había asumido primero), ni ningún comando Rust custom (no hace falta ninguno para esta fase).
