# icons/

Vacío a propósito — no hacen falta para `tauri dev` (esta fase), solo para `tauri build` (Fase 8, empaquetado).

Cuando llegue esa fase: con Node/Rust/Tauri CLI instalados, `tauri icon <ruta-a-un-png-cuadrado-grande>` genera automáticamente todos los tamaños/formatos que pide `tauri.conf.json` (`32x32.png`, `128x128.png`, `128x128@2x.png`, `icon.ico`, `icon.icns`) directamente en esta carpeta.
