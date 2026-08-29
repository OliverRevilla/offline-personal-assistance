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

const WS_URL = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/chat";

function nuevoId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function ChatApp() {
  const [connectionState, setConnectionState] = useState<"connecting" | "open" | "closed">("connecting");
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputText, setInputText] = useState("");
  const [micActive, setMicActive] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState<PendingConfirmation | null>(null);

  const wsRef = useRef<WsClient | null>(null);
  const playbackRef = useRef<AudioPlayback | null>(null);
  const captureRef = useRef<AudioCapture>(new AudioCapture());
  const currentAssistantTextRef = useRef("");
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const appendMessage = useCallback((msg: Message) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  useEffect(() => {
    const client = new WsClient(WS_URL, {
      onOpen: () => setConnectionState("open"),
      onClose: () => setConnectionState("closed"),
      onError: () => setConnectionState("closed"),
      onAudioOut: (pcm16) => playbackRef.current?.enqueue(pcm16),
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
      return;
    }

    try {
      await capture.start((pcm16) => wsRef.current?.sendAudioFrame(pcm16));
      setMicActive(true);
    } catch (err) {
      appendMessage({ id: nuevoId(), role: "error", text: `No se pudo acceder al micrófono: ${err}` });
    }
  }, [appendMessage]);

  const responderConfirmacion = useCallback(
    (aprobado: boolean) => {
      if (!pendingConfirmation || !wsRef.current) return;
      wsRef.current.sendConfirmacion(pendingConfirmation.id, aprobado);
      setPendingConfirmation(null);
    },
    [pendingConfirmation],
  );

  return (
    <div className="app">
      <div className="status-bar">
        <span className={`status-dot ${connectionState}`} />
        <span>{connectionState === "open" ? "Conectado" : connectionState === "closed" ? "Desconectado" : "Conectando..."}</span>
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
