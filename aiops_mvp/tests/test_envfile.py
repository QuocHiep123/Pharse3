"""`.env` loading (CLI/UI entry points only)."""

import os
from pathlib import Path

import pytest

from calldiag import cli
from calldiag.envfile import DEFAULT_ENV_FILE, env_file_path, load_env_file, parse_env


def test_parse_env_formats() -> None:
    text = """
# comment
OPENAI_API_KEY=sk-abc
export CALLDIAG_LLM_MODEL="model with spaces"
QUOTED='a # not a comment'
INLINE=value # trailing comment
EMPTY=
not a line
BAD KEY=x
"""
    assert parse_env(text) == {
        "OPENAI_API_KEY": "sk-abc", "CALLDIAG_LLM_MODEL": "model with spaces",
        "QUOTED": "a # not a comment", "INLINE": "value", "EMPTY": "",
    }


def test_shell_variables_win_and_names_only_are_returned(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("CALLDIAG_T_NEW=from-file\nCALLDIAG_T_SET=from-file\n", encoding="utf-8")
    monkeypatch.delenv("CALLDIAG_T_NEW", raising=False)
    monkeypatch.setenv("CALLDIAG_T_SET", "from-shell")
    assert load_env_file(env) == ["CALLDIAG_T_NEW"]
    assert os.environ["CALLDIAG_T_NEW"] == "from-file" and os.environ["CALLDIAG_T_SET"] == "from-shell"
    monkeypatch.delenv("CALLDIAG_T_NEW")


def test_env_file_location(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("CALLDIAG_ENV_FILE", raising=False)
    assert env_file_path() == DEFAULT_ENV_FILE and DEFAULT_ENV_FILE.parent.name == "aiops_mvp"
    monkeypatch.setenv("CALLDIAG_ENV_FILE", str(tmp_path / "custom.env"))
    assert env_file_path() == tmp_path / "custom.env"
    monkeypatch.setenv("CALLDIAG_ENV_FILE", "")
    assert env_file_path() is None and load_env_file() == []


def test_missing_file_is_fine(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "absent.env") == []


def test_cli_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    env = tmp_path / ".env"
    env.write_text("CALLDIAG_LLM_MODEL=model-from-env-file\n", encoding="utf-8")
    monkeypatch.setenv("CALLDIAG_ENV_FILE", str(env))
    monkeypatch.delenv("CALLDIAG_LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(["run", "--scenario", "S1", "--llm", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    # The model came from the file, so the only thing missing now is the key.
    assert "chưa đặt OPENAI_API_KEY" in out and "CALLDIAG_LLM_MODEL" not in out
    monkeypatch.delenv("CALLDIAG_LLM_MODEL", raising=False)


def test_example_file_has_no_secret() -> None:
    example = (DEFAULT_ENV_FILE.parent / ".env.example").read_text(encoding="utf-8")
    assert parse_env(example) == {"OPENAI_API_KEY": "", "CALLDIAG_LLM_MODEL": ""}
    assert ".env" in (DEFAULT_ENV_FILE.parent / ".gitignore").read_text(encoding="utf-8").split()
