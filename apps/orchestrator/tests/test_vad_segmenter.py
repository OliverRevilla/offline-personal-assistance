from app.stt.vad_segmenter import FRAME_BYTES, VadSegmenter


def test_silence_never_triggers_an_utterance() -> None:
    segmenter = VadSegmenter(aggressiveness=2, window_ms=300)
    silence_frame = b"\x00" * FRAME_BYTES

    # varios segundos de silencio puro: no debería triggerear nunca ni tirar excepciones
    for _ in range(200):
        assert segmenter.feed(silence_frame) is None


def test_feed_buffers_partial_frames() -> None:
    segmenter = VadSegmenter(aggressiveness=2, window_ms=300)
    silence_frame = b"\x00" * FRAME_BYTES

    # alimentar de a mitades de frame no debería romper el framing interno
    for _ in range(50):
        assert segmenter.feed(silence_frame[: FRAME_BYTES // 2]) is None
        assert segmenter.feed(silence_frame[FRAME_BYTES // 2 :]) is None
