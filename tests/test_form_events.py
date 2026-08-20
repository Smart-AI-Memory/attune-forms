"""Error-path coverage for :mod:`attune_forms.form_events` (#1655).

The uncovered statements are exactly the defensive branches — rotation,
the ``except OSError`` arms, and the ``DO_NOT_TRACK`` gate. Telemetry
must never break routing, so these paths are exercised with REAL
filesystem failures (a file where a directory should be, a directory
where the file should be, a read-only parent) rather than mocks,
per the issue's guidance and the "non-mocked round-trip" lesson.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from attune_forms.form_events import (
    _MAX_BYTES,
    _rotate_if_huge,
    inference_rate,
    log_submission,
    log_surface_decision,
    maybe_keyboard_hint,
    submission_count,
    surface_mix,
)

_POSIX_NON_ROOT = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="read-only-dir semantics need non-root POSIX",
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ATTUNE_HOME at tmp and clear the consent env vars."""
    home = tmp_path / "attune-home"
    monkeypatch.setenv("ATTUNE_HOME", str(home))
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    monkeypatch.delenv("ATTUNE_FORM_TELEMETRY", raising=False)
    return home


def _events_file(home: Path) -> Path:
    return home / "telemetry" / "form_events.jsonl"


class TestRotation:
    def test_rotates_when_over_limit(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * (_MAX_BYTES + 1))

        _rotate_if_huge(path)

        assert not path.exists()
        rotated = list(path.parent.glob("form_events.*.jsonl"))
        assert len(rotated) == 1
        assert rotated[0].stat().st_size == _MAX_BYTES + 1

    def test_dated_sibling_collision_appends_counter(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * (_MAX_BYTES + 1))
        # First rotation claims the dated name…
        _rotate_if_huge(path)
        (dated,) = path.parent.glob("form_events.*.jsonl")
        # …second rotation the same day must not clobber it.
        path.write_bytes(b"y" * (_MAX_BYTES + 1))
        _rotate_if_huge(path)

        assert dated.read_bytes()[:1] == b"x"  # first rotation intact
        rotated = sorted(p.name for p in path.parent.glob("form_events.*.jsonl"))
        assert len(rotated) == 2
        assert any(".1.jsonl" in name for name in rotated)

    def test_small_file_untouched(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_text("{}\n", encoding="utf-8")
        _rotate_if_huge(path)
        assert path.exists()
        assert not list(path.parent.glob("form_events.*.jsonl"))

    @_POSIX_NON_ROOT
    def test_rotation_oserror_swallowed(self, _isolated_home: Path) -> None:
        """A failed rename is a nicety lost, never an exception raised."""
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_bytes(b"x" * (_MAX_BYTES + 1))
        path.parent.chmod(0o500)  # rename needs write on the dir
        try:
            _rotate_if_huge(path)  # must not raise
            assert path.exists()  # rotation failed, file left in place
        finally:
            path.parent.chmod(0o700)


class TestLogSurfaceDecisionErrorPaths:
    def test_oserror_on_mkdir_swallowed(self, _isolated_home: Path) -> None:
        """A FILE squatting on the telemetry dir path → OSError → silent."""
        _isolated_home.mkdir(parents=True)
        (_isolated_home / "telemetry").write_text("not a dir", encoding="utf-8")

        log_surface_decision("widget", reason="test")  # must not raise

        assert (_isolated_home / "telemetry").is_file()  # unchanged

    def test_do_not_track_disables(self, _isolated_home: Path, monkeypatch) -> None:
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        log_surface_decision("widget")
        assert not _events_file(_isolated_home).exists()

    def test_falsey_do_not_track_still_records(self, _isolated_home: Path, monkeypatch) -> None:
        monkeypatch.setenv("DO_NOT_TRACK", "0")
        log_surface_decision("ask", reason="test")
        lines = _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        assert json.loads(lines[0])["surface"] == "ask"

    def test_do_not_track_disables_submission_log(self, _isolated_home: Path, monkeypatch) -> None:
        monkeypatch.setenv("DO_NOT_TRACK", "yes")
        log_submission()
        assert not _events_file(_isolated_home).exists()


class TestSurfaceMixErrorPaths:
    def test_unopenable_log_returns_empty(self, _isolated_home: Path) -> None:
        """A DIRECTORY squatting on the log path → OSError → {}."""
        _events_file(_isolated_home).mkdir(parents=True)
        assert surface_mix() == {}

    def test_missing_log_returns_empty(self, _isolated_home: Path) -> None:
        assert surface_mix() == {}

    def test_malformed_tail_skipped(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"event":"form_surface","surface":"widget"}\n{not json\n',
            encoding="utf-8",
        )
        assert surface_mix() == {"widget": 1}

    def test_explicit_home_overrides_process_env(
        self, _isolated_home: Path, tmp_path: Path
    ) -> None:
        """A reader with its own configured home (the ops dashboard,
        #1653) reads THAT store, not the process's ATTUNE_HOME."""
        other_home = tmp_path / "other-home"
        path = other_home / "telemetry" / "form_events.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"event":"form_surface","surface":"widget"}\n'
            '{"event":"form_surface","surface":"ask"}\n'
            '{"event":"form_surface","surface":"widget"}\n',
            encoding="utf-8",
        )
        assert surface_mix(home=other_home) == {"widget": 2, "ask": 1}
        assert surface_mix() == {}  # env-scoped home is still empty


class TestSubmissionPathsErrorArms:
    def test_log_submission_oserror_swallowed(self, _isolated_home: Path) -> None:
        """A FILE squatting on the telemetry dir path → OSError → silent."""
        _isolated_home.mkdir(parents=True)
        (_isolated_home / "telemetry").write_text("not a dir", encoding="utf-8")
        log_submission()  # must not raise
        assert (_isolated_home / "telemetry").is_file()

    def test_submission_count_missing_log_is_zero(self, _isolated_home: Path) -> None:
        assert submission_count() == 0

    def test_submission_count_skips_malformed_lines(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"event":"form_submitted"}\n'
            "{not json\n"
            '"just a string"\n'
            '{"event":"form_surface","surface":"ask"}\n'
            '{"event":"form_submitted"}\n',
            encoding="utf-8",
        )
        assert submission_count() == 2

    @_POSIX_NON_ROOT
    def test_keyboard_hint_oserror_returns_none(self, _isolated_home: Path) -> None:
        """Marker write failing must degrade to 'no hint', not an error."""
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_text('{"event":"form_submitted"}\n' * 10, encoding="utf-8")
        path.parent.chmod(0o500)  # marker write_text will fail
        try:
            assert maybe_keyboard_hint() is None
        finally:
            path.parent.chmod(0o700)


class TestInferenceRate:
    def test_missing_log_returns_zeros(self, _isolated_home: Path) -> None:
        rate = inference_rate()
        assert rate["forms"] == 0
        assert rate["inferred_share"] == 0.0

    def test_unopenable_log_returns_zeros(self, _isolated_home: Path) -> None:
        _events_file(_isolated_home).mkdir(parents=True)
        assert inference_rate()["forms"] == 0

    def test_counts_inferred_fields(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"event":"form_surface","question_count":4,"inferred_fields":2}\n'
            '{"event":"form_surface","question_count":2,"inferred_fields":2,'
            '"fully_inferred":true}\n'
            "{not json\n"
            '{"event":"form_submitted"}\n',
            encoding="utf-8",
        )
        rate = inference_rate()
        assert rate["forms"] == 2
        assert rate["fields"] == 6
        assert rate["fields_inferred"] == 4
        assert rate["fully_inferred"] == 1
        assert rate["inferred_share"] == round(4 / 6, 3)


class TestInferenceRateMalformedCounts:
    """Discovery-sweep finding (2026-08-20): a corrupt log line with a
    non-numeric question_count raised ValueError out of inference_rate
    while the sibling readers (surface_mix, submission_count) skip
    malformed lines by contract. The whole line is now skipped."""

    def test_non_numeric_count_line_skipped(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        good = {"event": "form_surface", "question_count": 2, "inferred_fields": 1}
        corrupt = {"event": "form_surface", "question_count": "three"}
        path.write_text(json.dumps(good) + "\n" + json.dumps(corrupt) + "\n", encoding="utf-8")
        stats = inference_rate()
        assert stats["forms"] == 1
        assert stats["fields"] == 2
        assert stats["fields_inferred"] == 1


class TestConfirmationPass1:
    """Regressions pinned from the 2026-08-20 confirmation-pass-1 review:
    reserved record keys always win, the never-raises contract covers
    more than OSError, and negative counts are the same malformed class
    as non-numeric ones."""

    def test_reserved_keys_cannot_be_clobbered(self, _isolated_home: Path) -> None:
        log_surface_decision("widget", event="form_submitted", v="9.9", reason="x")
        line = _events_file(_isolated_home).read_text(encoding="utf-8")
        record = json.loads(line)
        assert record["event"] == "form_surface"
        assert record["v"] == "1.0"
        assert record["reason"] == "x"  # honest context still lands
        assert submission_count() == 0  # the forged submission never counted

    def test_never_raises_on_unserializable_context(self, _isolated_home: Path) -> None:
        circular: dict = {}
        circular["self"] = circular  # json.dump -> ValueError, not OSError
        log_surface_decision("widget", ctx=circular)

        class _Hostile:
            def __str__(self) -> str:
                raise RuntimeError("boom")

        log_surface_decision("widget", ctx=_Hostile())  # default=str re-raises

    def test_negative_counts_skipped_like_non_numeric(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        good = {"event": "form_surface", "question_count": 5, "inferred_fields": 0}
        corrupt = {"event": "form_surface", "question_count": -4, "inferred_fields": -2}
        path.write_text(json.dumps(good) + "\n" + json.dumps(corrupt) + "\n", encoding="utf-8")
        stats = inference_rate()
        assert stats["forms"] == 1
        assert stats["fields"] == 5
        assert stats["fields_inferred"] == 0
        assert 0.0 <= stats["inferred_share"] <= 1.0

    def test_fractional_counts_skipped_not_truncated(self, _isolated_home: Path) -> None:
        """Needs-a-look item: ``question_count: 2.7`` was silently
        truncated by int(); a fractional count is now the same
        malformed class as a negative one — skipped whole. An
        INTEGRAL float (5.0) still counts: int() loses nothing."""
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            {"event": "form_surface", "question_count": 2.7, "inferred_fields": 1},
            {"event": "form_surface", "question_count": 3, "inferred_fields": 0.9},
            {"event": "form_surface", "question_count": 5.0, "inferred_fields": 2},
        ]
        path.write_text("".join(json.dumps(rec) + "\n" for rec in lines), encoding="utf-8")
        stats = inference_rate()
        assert stats["forms"] == 1
        assert stats["fields"] == 5
        assert stats["fields_inferred"] == 2

    def test_readers_honor_configured_home(self, tmp_path: Path, _isolated_home: Path) -> None:
        """Needs-a-look item: ``submission_count`` and ``inference_rate``
        took no ``home`` while sibling ``surface_mix`` did, so a
        configured-home reader (the ops dashboard) silently read the
        process-env store instead of the one it displays."""
        other = tmp_path / "dashboard-home"
        events = other / "telemetry" / "form_events.jsonl"
        events.parent.mkdir(parents=True)
        lines = [
            {"event": "form_submitted"},
            {"event": "form_surface", "question_count": 4, "inferred_fields": 3},
        ]
        events.write_text("".join(json.dumps(rec) + "\n" for rec in lines), encoding="utf-8")
        # The process-env home (_isolated_home) is empty: without the
        # explicit home these must see nothing, with it the real store.
        assert submission_count() == 0
        assert submission_count(home=other) == 1
        assert inference_rate()["forms"] == 0
        stats = inference_rate(home=other)
        assert stats["forms"] == 1
        assert stats["fields"] == 4
        assert stats["fields_inferred"] == 3

class TestConfirmationPass2:
    """inferred > fields (2026-08-20): fix 6 skipped negatives but a
    record with more inferred fields than total fields still poisoned
    the aggregate (inferred_share reached 10.4). Same malformed class,
    now skipped whole."""

    def test_inferred_exceeding_fields_skipped(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        good = {"event": "form_surface", "question_count": 4, "inferred_fields": 2}
        corrupt = {"event": "form_surface", "question_count": 1, "inferred_fields": 50}
        path.write_text(json.dumps(good) + "\n" + json.dumps(corrupt) + "\n", encoding="utf-8")
        stats = inference_rate()
        assert stats["forms"] == 1
        assert stats["fields"] == 4
        assert stats["fields_inferred"] == 2
        assert 0.0 <= stats["inferred_share"] <= 1.0
