"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AudioCapture } from "@/lib/audio-capture";
import { AudioPlayback } from "@/lib/audio-playback";
import { ServerMessage } from "@/lib/protocol";
import { WsClient } from "@/lib/ws-client";

interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "error";
  text: string;
}

interface PendingConfirmation {
  id: string;
  nombre: string;
  argumentos: Record<string, unknown>;
}

/** Estado visual de la "bola" de actividad — ver assistant-ball en globals.css.
 * Las actividades (hablando/pensando) pisan al modo de entrada porque son transitorias y
 * más relevantes en el momento; teclado/escuchando son los dos estados de reposo. */
type BallState = "conectando" | "desconectado" | "escuchando" | "pensando" | "hablando" | "teclado";

const BALL_LABELS: Record<BallState, string> = {
  conectando: "Conectando...",
  desconectado: "Desconectado",
  escuchando: "Escuchando...",
  pensando: "Pensando...",
  hablando: "Hablando...",
  teclado: "Modo teclado",
};

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/chat";

function nuevoId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function ChatApp() {
  const [connectionState, setConnectionState] = useState<"connecting" | "open" | "closed">("connecting");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [micActive, setMicActive] = useState(false);
  // "voz": el mic está (o debería estar) escuchando por defecto. "teclado": el usuario dijo
  // "todo por teclado" (o tocó el botón de mic, o el permiso de mic falló) y el server no
  // recibe más audio hasta que se reactive a mano o se reabra la app.
  const [inputMode, setInputMode] = useState<"voz" | "teclado">("voz");
  const [voiceOutputEnabled, setVoiceOutputEnabled] = useState(true);
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  const wsRef = useRef<WsClient | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);
  const captureRef = useRef<AudioCapture>(new AudioCapture());
  const currentAssistantTextRef = useRef("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const ballRef = useRef<HTMLDivElement | null>(null);
  // El efecto de abajo conecta una sola vez (deps estables) — el closure de onOpen no ve
  // actualizaciones de `voiceOutputEnabled` vía el state directamente, por eso este ref.
  const voiceOutputEnabledRef = useRef(true);
  // Se lee dentro del callback de cada frame de mic (no re-renderiza, tiene que ser instantáneo):
  // mientras el asistente está hablando por los parlantes, no mandamos audio del mic al server.
  // No hay cancelación de eco acústico (AEC) en este proyecto — sin este mute, el mic
  // capturaría la propia voz del asistente y la retranscribiría, generando un eco/loop.
  const isSpeakingRef = useRef(false);

  useEffect(() => {
    voiceOutputEnabledRef.current = voiceOutputEnabled;
  }, [voiceOutputEnabled]);

  const appendMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  const onMicFrame = useCallback((pcm16: Int16Array) => {
    if (!isSpeakingRef.current) {
      wsRef.current?.sendAudioFrame(pcm16);
    }

    // RMS del frame, normalizado a ~0-1 para el pulso de la bola (ver .ball-escuchando en
    // globals.css) — se escribe directo al DOM vía CSS custom property para no re-renderizar
    // en cada frame (el worklet manda muchos por segundo).
    let sumaCuadrados = 0;
    for (let i = 0; i < pcm16.length; i++) {
      const muestra = pcm16[i] / 32768;
      sumaCuadrados += muestra * muestra;
    }
    const rms = Math.sqrt(sumaCuadrados / pcm16.length);
    const nivel = Math.min(1, rms * 6);
    ballRef.current?.style.setProperty("--nivel", nivel.toFixed(3));
  }, []);

  const iniciarEscucha = useCallback(async () => {
    const capture = captureRef.current;
    if (capture.isActive) return;

    try {
      await capture.start(onMicFrame);
      setMicActive(true);
      setInputMode("voz");
    } catch (err) {
      setInputMode("teclado");
      appendMessage({
        id: nuevoId(),
        role: "error",
        text: `No se pudo acceder al micrófono, seguís por teclado: ${err}`,
      });
    }
  }, [appendMessage, onMicFrame]);

  useEffect(() => {
    const client = new WsClient(WS_URL, {
      onOpen: (wasReconnect) => {
        setConnectionState("open");
        // el server arranca cada conexión con voz_salida=true por default — si el usuario
        // ya la había apagado, hay que volver a avisarle (primera conexión incluida, es
        // inofensivo mandarlo aunque coincida con el default).
        client.sendVozSalida(voiceOutputEnabledRef.current);
        if (wasReconnect) {
          currentAssistantTextRef.current = "";
          appendMessage({
            id: nuevoId(),
            role: "system",
            text: "Reconectado — el contexto de la conversación anterior a este punto se perdió (el server empieza una sesión nueva por conexión).",
          });
        }
      },
      onClose: () => setConnectionState("closed"),
      onError: () => setConnectionState("closed"),
      onAudioOut: (pcm16) => {
        if (!voiceOutputEnabledRef.current) return;
        // set directo del ref (no solo del state): lo lee onMicFrame en el próximo frame de
        // mic, que puede llegar antes de que React llegue a aplicar el re-render de abajo.
        isSpeakingRef.current = true;
        setIsSpeaking(true);
        playbackRef.current?.enqueue(pcm16);
      },
      onServerMessage: (msg: ServerMessage) => {
        switch (msg.tipo) {
          case "audio_meta": {
            const playback = new AudioPlayback(msg.sample_rate);
            playback.init().catch((err) => console.error("No se pudo iniciar el audio de salida:", err));
            playbackRef.current = playback;
            break;
          }
          case "turn_start":
            currentAssistantTextRef.current = "";
            isSpeakingRef.current = false;
            setAssistantBusy(true);
            setIsSpeaking(false);
            break;
          case "transcript_final":
            appendMessage({ id: nuevoId(), role: "user", text: msg.texto });
            break;
          case "token":
            currentAssistantTextRef.current += msg.texto;
            break;
          case "tool_call":
            appendMessage({
              id: nuevoId(),
              role: "system",
              text: `🔧 ${msg.nombre}(${JSON.stringify(msg.argumentos)})`,
            });
            break;
          case "tool_result":
            appendMessage({
              id: nuevoId(),
              role: "system",
              text: `→ ${msg.nombre}: ${JSON.stringify(msg.resultado)}`,
            });
            break;
          case "confirmacion_requerida":
            setPendingConfirmation({ id: msg.id, nombre: msg.nombre, argumentos: msg.argumentos });
            break;
          case "turn_end":
            if (currentAssistantTextRef.current.trim()) {
              appendMessage({ id: nuevoId(), role: "assistant", text: currentAssistantTextRef.current });
            }
            currentAssistantTextRef.current = "";
            isSpeakingRef.current = false;
            setAssistantBusy(false);
            setIsSpeaking(false);
            break;
          case "modo_entrada":
            if (msg.modo === "teclado") {
              captureRef.current.stop();
              setMicActive(false);
              setInputMode("teclado");
            }
            break;
          case "error":
            appendMessage({ id: nuevoId(), role: "error", text: msg.mensaje });
            break;
        }
      },
    });

    client.connect();
    wsRef.current = client;

    return () => {
      client.close();
      playbackRef.current?.close();
      captureRef.current.stop();
    };
  }, [appendMessage]);

  // El mic escucha por defecto apenas se abre la app — no hace falta ningún click para
  // activarlo (decisión de producto: la bola es solo indicador, no un botón de encendido).
  // Pedir permiso de getUserMedia sin gesto previo del usuario puede ser bloqueado por el
  // navegador/webview en algunos entornos; si eso pasa, `iniciarEscucha` ya cae a modo teclado.
  useEffect(() => {
    iniciarEscucha();
  }, [iniciarEscucha]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const enviarTexto = useCallback(() => {
    const texto = inputText.trim();
    if (!texto || !wsRef.current) return;

    appendMessage({ id: nuevoId(), role: "user", text: texto });
    wsRef.current.sendUserMessage(texto);
    setInputText("");
  }, [inputText, appendMessage]);

  const toggleMic = useCallback(async () => {
    const capture = captureRef.current;
    if (capture.isActive) {
      capture.stop();
      setMicActive(false);
      setInputMode("teclado");
      return;
    }

    await iniciarEscucha();
  }, [iniciarEscucha]);

  const responderConfirmacion = useCallback(
    (aprobado: boolean) => {
      if (!pendingConfirmation || !wsRef.current) return;
      wsRef.current.sendConfirmacion(pendingConfirmation.id, aprobado);
      setPendingConfirmation(null);
    },
    [pendingConfirmation],
  );

  const toggleVoiceOutput = useCallback(() => {
    setVoiceOutputEnabled((prev) => {
      const next = !prev;
      wsRef.current?.sendVozSalida(next);
      return next;
    });
  }, []);

  const ballState: BallState =
    connectionState === "connecting"
      ? "conectando"
      : connectionState === "closed"
        ? "desconectado"
        : isSpeaking
          ? "hablando"
          : assistantBusy
            ? "pensando"
            : inputMode === "teclado"
              ? "teclado"
              : "escuchando";

  return (
    <div className="app">
      <div className="assistant-indicator">
        <div ref={ballRef} className={`assistant-ball ball-${ballState}`} />
        <span>{BALL_LABELS[ballState]}</span>
      </div>

      <div className="messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            {msg.text}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {pendingConfirmation && (
        <div className="confirmation-bar">
          <span>
            Confirmar {pendingConfirmation.nombre}({JSON.stringify(pendingConfirmation.argumentos)})?
          </span>
          <button className="approve" onClick={() => responderConfirmacion(true)}>
            Aprobar
          </button>
          <button className="reject" onClick={() => responderConfirmacion(false)}>
            Rechazar
          </button>
        </div>
      )}

      <div className="input-bar">
        <button
          onClick={toggleVoiceOutput}
          title={voiceOutputEnabled ? "Desactivar la voz de las respuestas" : "Activar la voz de las respuestas"}
        >
          {voiceOutputEnabled ? "🔊" : "🔇"}
        </button>
        <button className={micActive ? "mic-active" : ""} onClick={toggleMic} title="Activar/desactivar micrófono">
          {micActive ? "🎙️ Escuchando..." : "🎙️"}
        </button>
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && enviarTexto()}
          placeholder="Escribí un mensaje..."
        />
        <button onClick={enviarTexto}>Enviar</button>
      </div>
    </div>
  );
}
