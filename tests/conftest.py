"""Shared test isolation for attune-forms.

Routes every default ``~/.attune`` resolution (form-events telemetry,
keyboard-mode config) to a per-test tmp dir so the suite never touches
the developer's real home.

Also pins imports to THIS checkout's ``src/``: without this, a stale
editable install (e.g. one pointing at a sibling git worktree) silently
wins the import race and the suite exercises someone else's code
(observed 2026-08-13 — tests here ran a sibling worktree's copy).
"""

import sys
from pathlib import Path

import pytest

_SRC = str(Path(__file__).resolve().parents[1] / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
for _mod in [m for m in sys.modules if m == "attune_forms" or m.startswith("attune_forms.")]:
    del sys.modules[_mod]


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
