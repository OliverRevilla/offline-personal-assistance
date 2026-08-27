import pytest

from app.tools.vault_tools import resolve_vault_path


def test_resolve_vault_path_allows_paths_inside_vault(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    resolved = resolve_vault_path("proyectos/idea.md")

    assert resolved == (tmp_path / "proyectos" / "idea.md").resolve()


def test_resolve_vault_path_blocks_path_traversal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    with pytest.raises(ValueError, match="fuera del vault"):
        resolve_vault_path("../fuera-del-vault.md")


def test_resolve_vault_path_blocks_reserved_dir(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.tools.vault_tools.settings.vault_path", str(tmp_path))

    with pytest.raises(ValueError, match="reservada"):
        resolve_vault_path(".asistente/audit.jsonl")
