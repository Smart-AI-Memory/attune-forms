"""Shared test isolation for attune-forms.

Routes every default ``~/.attune`` resolution (form-events telemetry,
keyboard-mode config) to a per-test tmp dir so the suite never touches
the developer's real home.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_attune_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ATTUNE_HOME", str(tmp_path / ".attune"))
    monkeypatch.delenv("ATTUNE_KEYBOARD_MODE", raising=False)
    monkeypatch.delenv("ATTUNE_FORM_TELEMETRY", raising=False)
    monkeypatch.delenv("ATTUNE_FORMS_KEYBOARD_MODE", raising=False)
    monkeypatch.delenv("ATTUNE_FORMS_TELEMETRY", raising=False)
    monkeypatch.delenv("ATTUNE_FORMS_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
