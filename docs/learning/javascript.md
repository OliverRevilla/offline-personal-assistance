# Aprender JavaScript/TypeScript — aplicado a este proyecto

## Por qué te importa acá

Todo `apps/desktop/src/` es TypeScript (JavaScript con tipos, se compila a JS antes de correr). Es la Fase 6 completa: la UI (React), el cliente WebSocket, y la captura/reproducción de audio. Los dos únicos archivos JS puros del repo son los `AudioWorklet` en `apps/desktop/public/worklets/` — están en JS sin tipos a propósito, porque los Worklets de audio corren en un contexto especial del navegador que no pasa por el bundler de Next.js/TypeScript.

Archivos reales para ubicarte:
- `apps/desktop/src/lib/protocol.ts` — los tipos del contrato WS (qué mensajes existen y su forma).
- `apps/desktop/src/lib/ws-client.ts` — la clase que envuelve el `WebSocket` nativo, con reconexión.
- `apps/desktop/src/lib/audio-capture.ts` / `audio-playback.ts` — Web Audio API + AudioWorklet.
- `apps/desktop/public/worklets/*.js` — los procesadores de audio (JS puro, corren en su propio hilo).
- `apps/desktop/src/components/ChatApp.tsx` — la UI en React (hooks: `useState`, `useEffect`, `useRef`, `useCallback`).

## Conceptos clave, mapeados a código real del repo

### 1. `async`/`await` y Promises
`apps/desktop/src/lib/audio-capture.ts`:
```typescript
async start(onFrame: (pcm16: Int16Array) => void): Promise<void> {
  this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  this.context = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE });
  await this.context.audioWorklet.addModule("/worklets/pcm-capture-processor.js");
  ...
}
```
`getUserMedia` le pide permiso al usuario y devuelve una `Promise` que se resuelve (con el micrófono) o se rechaza (si el usuario lo niega, o no hay micrófono). `await` pausa la función hasta que se resuelve, sin bloquear el resto de la página — es la base de casi todo el código de este proyecto.

### 2. Clases y closures
`WsClient` (`ws-client.ts`) es una clase con estado privado (`socket`, `reconnectAttempt`) y callbacks que le pasás por afuera:
```typescript
export interface WsClientCallbacks {
  onServerMessage: (msg: ServerMessage) => void;
  onOpen?: (wasReconnect: boolean) => void;
  // ...
}
```
Esas funciones que le pasás (`onOpen`, `onServerMessage`, etc.) son *closures*: capturan variables del lugar donde las definiste (en `ChatApp.tsx`, capturan `setConnectionState`, `appendMessage`) y las siguen viendo aunque se ejecuten después, desde adentro de la clase. Es el mecanismo central para comunicar "algo pasó" entre código async y tu UI.

### 3. Tipos discriminados (discriminated unions) — la parte más "TypeScript" del repo
`protocol.ts` define cada mensaje con un campo `tipo` literal:
```typescript
export interface TokenMessage {
  tipo: "token";
  texto: string;
}
export interface TurnEndMessage {
  tipo: "turn_end";
}
export type ServerMessage = TokenMessage | TurnEndMessage | /* ... */;
```
Y en `ChatApp.tsx`, un `switch (msg.tipo)` hace que TypeScript **sepa** dentro de cada `case` qué campos existen — en el `case "token":` sabe que `msg.texto` existe; en `case "turn_end":` ni te deja intentar leer `msg.texto`, porque ese tipo no lo tiene. Esto es lo que en TS se llama *narrowing*: el compilador va "achicando" el tipo posible a medida que agregás chequeos. Es la razón por la que vale la pena escribir el protocolo como tipos en vez de `any`.

### 4. React hooks
`ChatApp.tsx` usa los cuatro hooks más comunes:
- `useState` — estado que, al cambiar, vuelve a dibujar el componente (`messages`, `connectionState`).
- `useRef` — una caja que guarda un valor **sin** volver a dibujar el componente al cambiar (`wsRef`, `playbackRef` — el `WsClient` y el `AudioPlayback` no necesitan que React "reaccione" cuando cambian).
- `useEffect` — código que corre después de que el componente se dibuja, con una lista de dependencias que controla cuándo se vuelve a correr (acá, `[]` implícito vía `[appendMessage]` estable → corre una sola vez, al montar, para abrir la conexión WS).
- `useCallback` — memoriza una función para que no cambie de identidad en cada render (importante para no reconectar el WS sin querer en cada re-render).

### 5. Web APIs específicas de este proyecto (lo más denso técnicamente)
- **[WebSocket](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)**: la conexión con el backend. `socket.binaryType = "arraybuffer"` es clave — sin eso, los frames de audio llegarían como `Blob` en vez de `ArrayBuffer`, mucho más incómodo de procesar sincrónicamente.
- **[Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)** y **[AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)**: el mic y el parlante no se tocan directo — armás un grafo de nodos de audio (`MediaStreamAudioSourceNode` → `AudioWorkletNode` → `destination`). El `AudioWorklet` corre en su **propio hilo de audio en tiempo real**, separado del hilo principal de JS — por eso esos archivos viven en `public/` como JS suelto y se comunican con el resto de la app vía `port.postMessage()`, no importándolos directamente.
- **TypedArrays** (`Int16Array`, `Float32Array`, `DataView`): el audio viaja como bytes crudos (PCM16), no como JSON. `ws-client.ts` usa `DataView.getInt16(offset, true)` para leer esos bytes respetando el orden (little-endian) que manda el backend Python — si algún día el audio suena "a ruido", el primer sospechoso es un desajuste acá.

## Recursos de aprendizaje

- **[MDN — JavaScript](https://developer.mozilla.org/en-US/docs/Web/JavaScript)** — la referencia definitiva del lenguaje y las Web APIs. Cuando tengas dudas de "¿qué hace exactamente este método?", empezá acá.
- **[javascript.info](https://javascript.info/)** — tutorial gratuito completo, ordenado de básico a avanzado (incluye async/await, clases, closures).
- **[TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)** — oficial. La sección de [narrowing](https://www.typescriptlang.org/docs/handbook/2/narrowing.html) es literalmente lo que pasa en el `switch` de `ChatApp.tsx`.
- **[React — react.dev/learn](https://react.dev/learn)** — la documentación oficial reescrita en formato tutorial interactivo, con foco en hooks.
- **[Next.js Docs](https://nextjs.org/docs)** — específicamente la sección de [Static Exports](https://nextjs.org/docs/app/guides/static-exports), que es el modo en el que corre este proyecto (`output: 'export'` en `next.config.mjs`).
- **[MDN — Web Audio API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)** y **[MDN — AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)** — para el código de `audio-capture.ts`/`audio-playback.ts` y los worklets.
- **[MDN — WebSocket API](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API)** — para `ws-client.ts`.

## Cómo practicar en este repo mismo

Un ejercicio real y acotado, sin tocar el backend: agregar un botón "Silenciar" en `ChatApp.tsx` que, mientras esté activo, ponga en pausa la reproducción de audio sin cortar la conexión WS ni el micrófono — te obliga a tocar `AudioPlayback` (agregar un método `mute()`/`unmute()` que, por ejemplo, desconecte el `workletNode` de `destination` temporalmente y lo reconecte), pasar ese estado desde `ChatApp.tsx`, y pensar qué pasa con los chunks de audio que siguen llegando mientras está silenciado (¿se acumulan en la cola y suenan todos juntos al reactivar, o se descartan?) — una decisión de diseño real y chica, del mismo tipo que las que aparecen en todo el proyecto.