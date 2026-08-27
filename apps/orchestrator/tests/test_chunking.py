from pathlib import Path

from app.rag.chunking import chunk_file, iter_markdown_files


def test_chunk_file_splits_by_heading_and_tracks_metadata(tmp_path: Path) -> None:
    vault = tmp_path
    note = vault / "notas-de-prueba.md"
    note.write_text(
        "# Notas de prueba\n\n"
        "Intro sin heading propio.\n\n"
        "## Dato de prueba\n\n"
        "El nombre en clave del proyecto es Centinela.\n",
        encoding="utf-8",
    )

    chunks = chunk_file(note, vault)

    assert len(chunks) == 2
    assert chunks[0].path == "notas-de-prueba.md"
    assert chunks[0].title == "Notas de prueba"
    assert chunks[0].heading == "Notas de prueba"
    assert "Intro sin heading propio" in chunks[0].text

    assert chunks[1].heading == "Dato de prueba"
    assert "Centinela" in chunks[1].text


def test_iter_markdown_files_skips_hidden_dirs(tmp_path: Path) -> None:
    (tmp_path / "visible.md").write_text("# Visible\n", encoding="utf-8")
    hidden_dir = tmp_path / ".obsidian"
    hidden_dir.mkdir()
    (hidden_dir / "config.md").write_text("# Oculto\n", encoding="utf-8")

    found = list(iter_markdown_files(tmp_path))

    assert [p.name for p in found] == ["visible.md"]
