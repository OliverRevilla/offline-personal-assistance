"""Métricas mínimas en memoria (sin Prometheus, ver logging_config.py para el porqué).

No persiste entre reinicios del proceso — es intencional, alcanza para diagnosticar latencia
durante una sesión de testeo/desarrollo, no para series históricas de largo plazo.
"""

from collections import deque
from dataclasses import dataclass, field

MAX_SAMPLES = 200


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    return {
        "count": len(values),
        "avg_ms": round(sum(values) / len(values), 1),
        "p50_ms": round(ordered[len(ordered) // 2], 1),
        "max_ms": round(max(values), 1),
    }


@dataclass
class Metrics:
    llm_ttfb_ms: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    stt_latency_ms: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))
    tts_latency_ms: deque = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))

    def record_llm_ttfb(self, ms: float) -> None:
        self.llm_ttfb_ms.append(ms)

    def record_stt_latency(self, ms: float) -> None:
        self.stt_latency_ms.append(ms)

    def record_tts_latency(self, ms: float) -> None:
        self.tts_latency_ms.append(ms)

    def snapshot(self) -> dict:
        return {
            "llm_ttfb": _stats(list(self.llm_ttfb_ms)),
            "stt_latency": _stats(list(self.stt_latency_ms)),
            "tts_latency": _stats(list(self.tts_latency_ms)),
        }


metrics = Metrics()
