// Sin comandos Rust custom en esta fase: WebSocket, getUserMedia y Web Audio API son Web
// APIs estándar que el webview resuelve solo, sin pasar por el puente de Tauri. Ver
// docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md.

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error al correr la app de Tauri");
}
