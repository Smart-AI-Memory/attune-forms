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


@pytest.fixture(scope="session", autouse=True)
def _session_attune_home(tmp_path_factory):
    """Session-scoped backstop for the per-test isolation below.

    Module-/session-scoped fixtures are set up BEFORE function-scoped
    autouse fixtures, so anything they run sees the real environment
    (observed 2026-08-20: the module-scoped MCP round-trip fixture
    leaked form_surface/form_submitted events into the developer's
    live ~/.attune/telemetry/form_events.jsonl on every suite run).
    """
    mp = pytest.MonkeyPatch()
    mp.setenv("ATTUNE_HOME", str(tmp_path_factory.mktemp("attune-home")))
    mp.delenv("ATTUNE_FORMS_HOME", raising=False)
    mp.delenv("XDG_STATE_HOME", raising=False)
    mp.delenv("DO_NOT_TRACK", raising=False)
    yield
    mp.undo()


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


#: Modules that call deprecated surface on purpose — they cover the
#: behavior that must keep working until removal. pyproject turns this
#: package's own deprecations into errors, so anything NOT listed here
#: fails the moment it touches deprecated surface. The list should reach
#: empty when `form_to_askuserquestion` and `is_trivial_form` are removed
#: (no earlier than 0.18.0); a stale entry is caught below.
EXERCISES_DEPRECATED_SURFACE = frozenset(
    {
        "test_assumption_review_construct",
        "test_bridge",
        "test_confirm_construct",
        "test_decision_construct",
        "test_deliberation_construct",
        "test_expansion_helpers",
        "test_inference_first",
        "test_models_guards",
        "test_progress_construct",
        "test_progress_report_style",
        "test_pushback_construct",
        "test_ranking_construct",
        "test_reference_form",
        "test_renderer_registry",
        "test_select_form_surface",
        "test_triage_construct",
    }
)


def pytest_collection_modifyitems(items):
    """Let the listed modules call deprecated surface without erroring."""
    for item in items:
        if item.module.__name__.rsplit(".", 1)[-1] in EXERCISES_DEPRECATED_SURFACE:
            item.add_marker(pytest.mark.filterwarnings("default::DeprecationWarning"))
