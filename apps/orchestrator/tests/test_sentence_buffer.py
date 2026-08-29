from app.tts.sentence_buffer import SentenceBuffer


def test_feed_yields_sentence_only_once_complete() -> None:
    buffer = SentenceBuffer()

    assert buffer.feed("Hola, ¿cómo") == []
    assert buffer.feed(" estás? Bien, gracias") == ["Hola, ¿cómo estás?"]
    assert buffer.feed(". ¿Y vos?") == ["Bien, gracias."]


def test_feed_yields_multiple_sentences_in_one_call() -> None:
    buffer = SentenceBuffer()

    oraciones = buffer.feed("Primera oración. Segunda oración! Tercera sin terminar")

    assert oraciones == ["Primera oración.", "Segunda oración!"]


def test_flush_returns_remaining_text_without_terminator() -> None:
    buffer = SentenceBuffer()
    buffer.feed("texto sin punto final")

    assert buffer.flush() == "texto sin punto final"
    assert buffer.flush() is None  # ya vacío


def test_flush_returns_none_when_buffer_is_empty() -> None:
    buffer = SentenceBuffer()

    assert buffer.flush() is None
