"""Test lệnh `callops ui` (không mở server)."""

from __future__ import annotations

import sys

import pytest

pytest.importorskip("gradio")

from callops.cli import main  # noqa: E402


def test_ui_command_calls_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    got: dict = {}
    monkeypatch.setattr("callops.ui.app.launch", lambda **kw: got.update(kw))
    assert main(["ui", "--port", "7861"]) == 0
    assert got == {"host": "127.0.0.1", "port": 7861, "share": False}


def test_ui_command_missing_extra(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setitem(sys.modules, "callops.ui.app", None)  # import -> ImportError
    assert main(["ui"]) == 2
    assert "pip install" in capsys.readouterr().err
