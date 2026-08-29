# apps/desktop

App de escritorio: Tauri (shell nativo, webview del sistema) + Next.js/React (UI, exportada estática). Captura de micrófono, reproducción de audio en streaming (`AudioWorklet`), UI de conversación, cliente WebSocket hacia `apps/orchestrator`.

Owner: `frontend-engineer`. Ver [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) para el contrato del protocolo WS y [docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md](../../docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md) para las decisiones de esta fase.

## Dónde corre esto

**Nativo en Windows** — no dentro de WSL2 (a diferencia del backend). El backend sigue viviendo en WSL2 sin cambios; este frontend le habla por WebSocket a `ws://localhost:8000/ws/chat`, que WSL2 expone solo hacia Windows. Ver el ADR 0008 para el porqué.

## Requisitos (en Windows, no en WSL2)

- Node.js LTS (18+).
- Rust + Cargo ([rustup.rs](https://rustup.rs)).
- Tauri CLI: se instala como dependencia de desarrollo (`@tauri-apps/cli`, ya en `package.json`), no hace falta instalarlo global.
- En Windows, Tauri usa WebView2 (viene preinstalado en Windows 10/11 actualizados; si falta, el instalador de Tauri/Edge lo resuelve).

## Cómo correr

```powershell
cd apps\desktop
npm install
copy .env.local.example .env.local
npm run tauri dev
```

Esto levanta `next dev` (vía `beforeDevCommand` en `tauri.conf.json`) y abre la ventana de Tauri apuntando a `http://localhost:3000`. Requiere que el backend (`apps/orchestrator`, en WSL2) ya esté corriendo — ver la raíz de `GUIDE.md`.

## Estado actual (Fase 6 del roadmap)

Todo lo de las fases 1-5 (texto, RAG, tool calling con confirmación, voz de entrada y salida) ahora con una UI real: conversación en pantalla, botón de micrófono, reproducción de audio, y la barra de confirmación para operaciones destructivas (`actualizar_nota`).

No incluye todavía: empaquetado/instalador (Fase 8 — íconos de la app tampoco existen aún, ver `src-tauri/icons/README.md`), ni ningún comando Rust custom (no hace falta ninguno para esta fase).
