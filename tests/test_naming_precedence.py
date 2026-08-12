"""P1 naming shims (attune-forms-plugin spec R1.1/R1.2, D2 ruling).

Precedence pinned: new name > legacy name > default — and a repo (or
machine) with only the legacy names keeps working byte-identically.
"""

from __future__ import annotations

import json
from pathlib import Path

from attune_forms import form_events
from attune_forms.bridge import keyboard_mode_enabled, set_keyboard_mode


class TestConfigFilePrecedence:
    def test_new_config_wins_over_legacy(self, tmp_path: Path) -> None:
        (tmp_path / "attune-forms.config.json").write_text(json.dumps({"keyboard_mode": True}))
        (tmp_path / "attune.config.json").write_text(json.dumps({"keyboard_mode": False}))
        assert keyboard_mode_enabled(tmp_path) is True

    def test_legacy_only_still_works(self, tmp_path: Path) -> None:
        (tmp_path / "attune.config.json").write_text(json.dumps({"keyboard_mode": True}))
        assert keyboard_mode_enabled(tmp_path) is True

    def test_neither_file_defaults_off(self, tmp_path: Path) -> None:
        assert keyboard_mode_enabled(tmp_path) is False


class TestEnvPrecedence:
    def test_new_env_wins_over_legacy(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_KEYBOARD_MODE", "true")
        monkeypatch.setenv("ATTUNE_KEYBOARD_MODE", "false")
        assert keyboard_mode_enabled(tmp_path) is True

    def test_new_env_falsey_wins(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_KEYBOARD_MODE", "false")
        monkeypatch.setenv("ATTUNE_KEYBOARD_MODE", "true")
        assert keyboard_mode_enabled(tmp_path) is False

    def test_legacy_env_alone_still_works(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ATTUNE_KEYBOARD_MODE", "true")
        assert keyboard_mode_enabled(tmp_path) is True


class TestWriteTarget:
    def test_fresh_write_uses_legacy_default(self, tmp_path: Path) -> None:
        """Deliberate (D2): the fresh-write default stays legacy so
        attune-ai needs ZERO changes at 0.2.0; public surfaces pin
        ``config_name`` explicitly."""
        path = set_keyboard_mode(True, tmp_path)
        assert path.name == "attune.config.json"

    def test_existing_new_file_is_written(self, tmp_path: Path) -> None:
        (tmp_path / "attune-forms.config.json").write_text("{}")
        path = set_keyboard_mode(True, tmp_path)
        assert path.name == "attune-forms.config.json"
        assert json.loads(path.read_text())["keyboard_mode"] is True

    def test_explicit_config_name_overrides(self, tmp_path: Path) -> None:
        path = set_keyboard_mode(True, tmp_path, config_name="attune-forms.config.json")
        assert path.name == "attune-forms.config.json"

    def test_write_then_read_round_trips_on_new_name(self, tmp_path: Path) -> None:
        set_keyboard_mode(True, tmp_path, config_name="attune-forms.config.json")
        assert keyboard_mode_enabled(tmp_path) is True


class TestDataHome:
    def test_new_home_env_wins(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_HOME", str(tmp_path / "new-home"))
        monkeypatch.setenv("ATTUNE_HOME", str(tmp_path / "old-home"))
        assert form_events._events_path() == (
            tmp_path / "new-home" / "telemetry" / "form_events.jsonl"
        )

    def test_legacy_home_env_still_works(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.setenv("ATTUNE_HOME", str(tmp_path / "old-home"))
        assert form_events._events_path() == (
            tmp_path / "old-home" / "telemetry" / "form_events.jsonl"
        )

    def test_existing_dot_attune_honored(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ATTUNE_HOME", raising=False)
        monkeypatch.delenv("ATTUNE_FORMS_HOME", raising=False)
        home = tmp_path / "fake-home"
        (home / ".attune").mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        assert form_events._default_home() == home / ".attune"

    def test_standalone_falls_to_xdg_state(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ATTUNE_HOME", raising=False)
        monkeypatch.delenv("ATTUNE_FORMS_HOME", raising=False)
        home = tmp_path / "fake-home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        assert form_events._default_home() == home / ".local" / "state" / "attune-forms"

    def test_xdg_state_home_env_respected(self, monkeypatch, tmp_path: Path) -> None:
        monkeypatch.delenv("ATTUNE_HOME", raising=False)
        monkeypatch.delenv("ATTUNE_FORMS_HOME", raising=False)
        home = tmp_path / "fake-home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("USERPROFILE", str(home))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
        assert form_events._default_home() == tmp_path / "xdg-state" / "attune-forms"


class TestTelemetryEnv:
    def test_new_telemetry_env_disables(self, monkeypatch) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_TELEMETRY", "0")
        assert form_events._enabled() is False

    def test_new_env_set_truthy_wins_over_legacy_falsey(self, monkeypatch) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_TELEMETRY", "1")
        monkeypatch.setenv("ATTUNE_FORM_TELEMETRY", "0")
        assert form_events._enabled() is True

    def test_legacy_telemetry_env_still_disables(self, monkeypatch) -> None:
        monkeypatch.setenv("ATTUNE_FORM_TELEMETRY", "0")
        assert form_events._enabled() is False
