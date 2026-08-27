import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)")

# Umbral simple para no dejar crecer una sección indefinidamente. No hay overlap entre
# chunks: para el tamaño de un vault personal, perder algo de contexto en el borde de un
# chunk no vale la complejidad extra de solaparlos (revisar si el recall se vuelve un problema real).
MAX_CHUNK_CHARS = 1200


@dataclass(frozen=True)
class Chunk:
    path: str  # ruta relativa al vault (posix), única fuente de verdad para citar la nota
    title: str
    heading: str
    index: int
    text: str


def iter_markdown_files(vault_path: Path) -> Iterator[Path]:
    """Todos los .md del vault, salvo carpetas ocultas (ej. .obsidian, .git)."""
    for md_file in sorted(vault_path.rglob("*.md")):
        relative_parts = md_file.relative_to(vault_path).parts
        if any(part.startswith(".") for part in relative_parts):
            continue
        yield md_file


def extract_title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped:
            break  # la primera línea no vacía no es un título H1: usar el fallback
    return fallback


def chunk_file(path: Path, vault_path: Path) -> list[Chunk]:
    text = path.read_text(encoding="utf-8")
    relpath = path.relative_to(vault_path).as_posix()
    title = extract_title(text, fallback=path.stem)

    chunks: list[Chunk] = []
    current_heading = title
    buffer: list[str] = []
    buffer_len = 0

    def flush() -> None:
        nonlocal buffer, buffer_len
        content = "\n".join(buffer).strip()
        if content:
            chunks.append(
                Chunk(path=relpath, title=title, heading=current_heading, index=len(chunks), text=content)
            )
        buffer = []
        buffer_len = 0

    for line in text.splitlines():
        heading_match = HEADING_RE.match(line)
        if heading_match:
            flush()
            current_heading = heading_match.group(2).strip()

        buffer.append(line)
        buffer_len += len(line) + 1
        if buffer_len >= MAX_CHUNK_CHARS:
            flush()

    flush()
    return chunks
