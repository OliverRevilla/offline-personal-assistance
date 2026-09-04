# Aprender Rust — aplicado a este proyecto

## Por qué te importa acá

Rust aparece en un solo lugar del repo: `apps/desktop/src-tauri/`, el shell nativo de la app de escritorio (Fase 6). Hoy es un scaffold mínimo — no hay ningún comando Rust custom, porque todo lo que la Fase 6 necesita (WebSocket, micrófono, reproducción de audio) son Web APIs estándar que el webview resuelve solo (ver [docs/adr/0008](../adr/0008-frontend-nativo-windows-y-stack-tauri.md)). Pero el día que necesites algo que el navegador no puede hacer por sí solo — leer/escribir archivos del sistema fuera del sandbox del vault, un ícono en la bandeja del sistema, notificaciones nativas, autostart — vas a escribir un **comando Tauri** en Rust, y ahí sí hace falta saber lo básico.

Archivos reales del repo para ubicarte:
- `apps/desktop/src-tauri/Cargo.toml` — las dependencias (el equivalente Rust de `package.json`).
- `apps/desktop/src-tauri/src/lib.rs` — el punto de entrada real (`pub fn run()`).
- `apps/desktop/src-tauri/src/main.rs` — un wrapper mínimo que llama a `lib.rs` (separados así para que el mismo código sirva también para mobile, algo estándar de los proyectos Tauri, no una decisión nuestra).
- `apps/desktop/src-tauri/tauri.conf.json` — configuración de la ventana, el build, y qué se empaqueta.
- `apps/desktop/src-tauri/capabilities/default.json` — qué permisos tiene la ventana principal (hoy solo `core:default`, porque no usamos ningún plugin ni comando).

## Conceptos mínimos para entender lo que ya existe

No hace falta dominar Rust para leer el `lib.rs` actual — es literalmente esto:

```rust
#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error al correr la app de Tauri");
}
```

Para entender **esta línea** hace falta saber:
- `pub fn` — una función pública (exportada fuera del módulo). Como `export function` en TS.
- `tauri::Builder::default()` — el patrón *builder*: encadenás métodos (`.plugin(...)`, `.invoke_handler(...)`, etc.) antes de `.run(...)`. Muy común en Rust, parecido a encadenar métodos en JS pero sin mutar nada hasta el final.
- `.expect("mensaje")` — si `.run(...)` devuelve un error, el programa termina mostrando ese mensaje. Es la versión "no me importa manejarlo con elegancia, si falla que reviente con este texto" de Rust — razonable acá porque si la app no puede arrancar, no hay nada más que hacer.
- `#[cfg_attr(...)]` — un *atributo* (como un decorador). Este en particular dice "esta función es el entry point solo si estamos compilando para mobile" — no aplica a nuestro build de Windows, es boilerplate del scaffold estándar de Tauri.

Lo próximo que sí vas a necesitar en algún momento:

| Concepto | Por qué importa acá |
|---|---|
| **Ownership y borrowing** (`&`, `&mut`, mover un valor) | Es LA diferencia central de Rust vs. cualquier lenguaje con garbage collector (JS incluido). Todo comando Tauri que reciba datos del frontend va a chocar con esto tarde o temprano. |
| **`Result<T, E>` y `?`** | Rust no tiene excepciones — las funciones que pueden fallar devuelven `Result`. Cualquier comando Tauri que toque el filesystem lo va a usar. |
| **`Option<T>`** | El equivalente a `T \| null` de TS, pero forzado por el compilador — no podés "olvidarte" de chequear `None`. |
| **`async`/`await`** | Tauri corre sobre `tokio` (el runtime async de Rust) por debajo. Se ve parecido a JS pero con reglas distintas de por qué/cuándo algo es `Send`. |
| **Macros (`#[derive(...)]`, `#[tauri::command]`)** | Código que genera código en tiempo de compilación — vas a ver `#[derive(Serialize, Deserialize)]` en cualquier struct que cruce la frontera Rust↔JS. |

## Ejemplo concreto: cómo se vería agregar un comando

Esto es **hipotético** (no existe en el repo todavía) — para que cuando llegue el momento no arranques de cero. Un comando que devuelva la versión de la app:

```rust
// en src-tauri/src/lib.rs

#[tauri::command]
fn get_app_version() -> String {
    env!("CARGO_PKG_VERSION").to_string()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![get_app_version]) // <- acá se registra
        .run(tauri::generate_context!())
        .expect("error al correr la app de Tauri");
}
```

Y del lado TypeScript (`apps/desktop/src/...`), se invoca así:

```typescript
import { invoke } from "@tauri-apps/api/core";

const version = await invoke<string>("get_app_version");
```

Ese `invoke` es el puente — es básicamente un RPC entre el JS del webview y el binario Rust. Cualquier tipo que cruce ese puente (argumentos o el valor de retorno) necesita poder serializarse a JSON de los dos lados; para structs propios, eso es lo que hace `#[derive(Serialize, Deserialize)]` (usando el crate `serde`, ya está en `Cargo.toml`).

## Recursos de aprendizaje

- **[The Rust Book](https://doc.rust-lang.org/book/)** — el libro oficial, gratis. Es *la* referencia; los capítulos de ownership (cap. 4) y de manejo de errores (cap. 9) son los que más te van a servir para este proyecto puntualmente.
- **[Rust by Example](https://doc.rust-lang.org/rust-by-example/)** — si aprendés mejor leyendo código corto y ejecutable que prosa.
- **[Rustlings](https://github.com/rust-lang/rustlings)** — ejercicios interactivos en la terminal, el compilador te va guiando. Muy recomendado para practicar ownership sin quedarte trabado leyendo teoría.
- **[Comprehensive Rust (Google)](https://google.github.io/comprehensive-rust/)** — curso gratuito con foco práctico, pensado originalmente para gente que ya sabe programar en otro lenguaje (tu caso).
- **[The Cargo Book](https://doc.rust-lang.org/cargo/)** — para entender `Cargo.toml`/`Cargo.lock` con más profundidad.
- **[Tauri — Calling Rust from the frontend](https://tauri.app/develop/calling-rust/)** — la documentación oficial específica de `#[tauri::command]` e `invoke`, justo lo que necesitás el día que agregues el primer comando.
- **[Tauri — Capabilities y permisos](https://tauri.app/security/capabilities/)** — para entender `capabilities/default.json` si en algún momento necesitás un permiso más allá de `core:default`.

## Cómo practicar en este repo mismo

Un ejercicio real y acotado: agregar el comando `get_app_version` de arriba (existe de verdad, `env!("CARGO_PKG_VERSION")` lee el `version` de `Cargo.toml`) y mostrarlo en algún lugar chico de la UI (ej. al pie de la ventana). Te obliga a tocar `lib.rs`, entender `invoke_handler`, y ver el viaje completo Rust → JSON → TypeScript sin arriesgar nada del resto de la app.