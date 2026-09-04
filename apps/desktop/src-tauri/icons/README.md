# icons/

`32x32.png`, `128x128.png`, `128x128@2x.png` e `icon.ico` son **placeholders reales** (un cuadrado azul con una "A", generados con `System.Drawing` vía PowerShell) — no diseño final, pero archivos válidos que sirven para compilar.

**Corrección a una suposición anterior**: se había asumido que los íconos solo hacían falta para `tauri build` (empaquetado, Fase 8), no para `tauri dev`. Es **falso en Windows específicamente** — el build de Rust en Windows genera un recurso de Windows (`.rc`) embebido en el `.exe` en *cualquier* compilación, dev incluida, y ese paso necesita `icon.ico` sí o sí. Sin él, `cargo build`/`tauri dev` falla con `icon.ico not found; required for generating a Windows Resource file`.

Falta todavía `icon.icns` (formato de ícono de macOS) — no se generó porque no hay herramientas de macOS disponibles para armarlo correctamente, y no bloquea nada en Windows. Hace falta antes de intentar empaquetar para macOS (Fase 8) — no antes.

Cuando llegue el momento de un ícono real (Fase 8): con Node/Rust/Tauri CLI instalados, `tauri icon <ruta-a-un-png-cuadrado-grande>` regenera automáticamente todos los tamaños/formatos (incluido `icon.icns`) directamente en esta carpeta, reemplazando estos placeholders.