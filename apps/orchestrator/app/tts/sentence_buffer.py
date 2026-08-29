"""Trocea el stream de tokens del LLM en oraciones completas, para poder sintetizar audio
antes de que el mensaje entero termine de generarse (ver docs/ARCHITECTURE.md, Fase 5).
"""

import re

SENTENCE_END_RE = re.compile(r"[.!?;:]+[\s\n]|\n+")


class SentenceBuffer:
    def __init__(self) -> None:
        self.buffer = ""

    def feed(self, token: str) -> list[str]:
        """Agrega un fragmento de texto y devuelve las oraciones que quedaron completas."""
        self.buffer += token
        oraciones = []

        while True:
            match = SENTENCE_END_RE.search(self.buffer)
            if not match:
                break
            fin = match.end()
            oracion = self.buffer[:fin].strip()
            self.buffer = self.buffer[fin:]
            if oracion:
                oraciones.append(oracion)

        return oraciones

    def flush(self) -> str | None:
        """Al terminar el turno: lo que haya quedado sin un delimitador de fin de oración."""
        resto = self.buffer.strip()
        self.buffer = ""
        return resto or None
