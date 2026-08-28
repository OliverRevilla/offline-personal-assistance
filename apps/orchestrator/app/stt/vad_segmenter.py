"""Segmentación de turnos de habla sobre un stream de audio en vivo, con webrtcvad.

Cada conexión WS tiene su propia instancia (mantiene estado: en qué punto del turno está).
No confundir con faster-whisper: acá no se transcribe nada, solo se decide "el usuario
empezó/terminó de hablar" para saber cuándo mandar el audio acumulado a transcribir.
"""

import collections
from collections.abc import Sequence

import webrtcvad

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME_BYTES = (SAMPLE_RATE * FRAME_MS // 1000) * 2  # 2 bytes por muestra (PCM16)

# Umbrales del algoritmo (idéntico en espíritu al ejemplo clásico de py-webrtcvad):
# se dispara el inicio de turno cuando >90% de la ventana viene marcada como voz, y se da
# por terminado cuando >90% de la ventana viene marcada como silencio.
TRIGGER_RATIO = 0.9


class VadSegmenter:
    def __init__(self, *, aggressiveness: int = 2, window_ms: int = 300) -> None:
        self.vad = webrtcvad.Vad(aggressiveness)
        window_frames = max(1, window_ms // FRAME_MS)
        self.ring_buffer: collections.deque[tuple[bytes, bool]] = collections.deque(maxlen=window_frames)
        self.triggered = False
        self.voiced_frames: list[bytes] = []
        self.pending = b""

    def feed(self, pcm16: bytes) -> bytes | None:
        """Alimenta más audio PCM16 mono @16kHz. Devuelve la utterance completa cuando
        detecta que el usuario terminó de hablar, o None si el turno sigue en curso."""
        self.pending += pcm16
        utterance: bytes | None = None

        while len(self.pending) >= FRAME_BYTES:
            frame = self.pending[:FRAME_BYTES]
            self.pending = self.pending[FRAME_BYTES:]
            is_speech = self.vad.is_speech(frame, SAMPLE_RATE)

            if not self.triggered:
                self.ring_buffer.append((frame, is_speech))
                if self.ring_buffer.maxlen and len(self.ring_buffer) == self.ring_buffer.maxlen:
                    if _ratio_true(self.ring_buffer) > TRIGGER_RATIO:
                        self.triggered = True
                        self.voiced_frames = [f for f, _ in self.ring_buffer]
                        self.ring_buffer.clear()
            else:
                self.voiced_frames.append(frame)
                self.ring_buffer.append((frame, is_speech))
                if self.ring_buffer.maxlen and len(self.ring_buffer) == self.ring_buffer.maxlen:
                    if _ratio_false(self.ring_buffer) > TRIGGER_RATIO:
                        utterance = b"".join(self.voiced_frames)
                        self.triggered = False
                        self.voiced_frames = []
                        self.ring_buffer.clear()

        return utterance


def _ratio_true(buffer: Sequence[tuple[bytes, bool]]) -> float:
    if not buffer:
        return 0.0
    return sum(1 for _, speech in buffer if speech) / len(buffer)


def _ratio_false(buffer: Sequence[tuple[bytes, bool]]) -> float:
    if not buffer:
        return 0.0
    return sum(1 for _, speech in buffer if not speech) / len(buffer)
