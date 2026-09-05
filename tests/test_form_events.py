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
    log_form_build,
    log_form_rendered,
    log_submission,
    log_surface_decision,
    maybe_keyboard_hint,
    stage_latency,
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


class TestStageLoggers:
    """The three lifecycle loggers write joinable, well-formed records."""

    def test_log_form_build_record(self, _isolated_home: Path) -> None:
        log_form_build("abc123", source="template:session-contract", question_count=4)
        (line,) = _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        record = json.loads(line)
        assert record["event"] == "form_build"
        assert record["form_id"] == "abc123"
        assert record["source"] == "template:session-contract"
        assert record["question_count"] == 4
        assert record["v"] == "1.0" and "ts" in record

    def test_log_form_rendered_record(self, _isolated_home: Path) -> None:
        log_form_rendered("abc123", duration_ms=1.23456, html_bytes=2048)
        record = json.loads(_events_file(_isolated_home).read_text(encoding="utf-8"))
        assert record["event"] == "form_rendered"
        assert record["form_id"] == "abc123"
        assert record["duration_ms"] == 1.235
        assert record["html_bytes"] == 2048

    def test_log_submission_carries_form_id(self, _isolated_home: Path) -> None:
        log_submission(form_id="abc123")
        record = json.loads(_events_file(_isolated_home).read_text(encoding="utf-8"))
        assert record["event"] == "form_submitted"
        assert record["form_id"] == "abc123"

    def test_log_submission_zero_arg_still_works(self, _isolated_home: Path) -> None:
        """Pre-0.8 call sites (attune-ai <= 14.1.0) pass no form_id."""
        log_submission()
        record = json.loads(_events_file(_isolated_home).read_text(encoding="utf-8"))
        assert record["event"] == "form_submitted"
        assert "form_id" not in record
        assert submission_count() == 1

    def test_stage_loggers_honor_consent(
        self, _isolated_home: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ATTUNE_FORMS_TELEMETRY", "0")
        log_form_build("x", source="dict", question_count=1)
        log_form_rendered("x", duration_ms=1.0, html_bytes=1)
        log_submission(form_id="x")
        assert not _events_file(_isolated_home).exists()

    def test_form_id_truncated_to_64(self, _isolated_home: Path) -> None:
        log_submission(form_id="z" * 200)
        record = json.loads(_events_file(_isolated_home).read_text(encoding="utf-8"))
        assert record["form_id"] == "z" * 64


class TestFormIdLifecycle:
    """form_id joins the pipeline stages without the agent threading it."""

    FORM = {
        "title": "Scope",
        "fields": [
            {"id": "goal", "text": "Goal?", "type": "text_input"},
        ],
    }

    def test_same_dict_same_id_different_dict_different_id(self) -> None:
        from attune_forms.bridge import form_from_dict

        first = form_from_dict(dict(self.FORM))
        second = form_from_dict(dict(self.FORM))
        other = form_from_dict({**self.FORM, "title": "Other"})
        assert first.form_id and first.form_id == second.form_id
        assert other.form_id != first.form_id

    def test_explicit_form_id_wins(self) -> None:
        from attune_forms.bridge import form_from_dict

        form = form_from_dict({**self.FORM, "form_id": "my-form.v1"})
        assert form.form_id == "my-form.v1"

    def test_invalid_form_id_is_a_definition_problem(self) -> None:
        from attune_forms.bridge import FormValidationError, form_from_dict

        with pytest.raises(FormValidationError) as exc:
            form_from_dict({**self.FORM, "form_id": "../escape"})
        assert any("form_id" in p for p in exc.value.problems)

    def test_build_event_logged_with_source_dict(self, _isolated_home: Path) -> None:
        from attune_forms.bridge import form_from_dict

        form = form_from_dict(dict(self.FORM))
        records = [
            json.loads(line)
            for line in _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        ]
        builds = [r for r in records if r["event"] == "form_build"]
        assert builds and builds[0]["form_id"] == form.form_id
        assert builds[0]["source"] == "dict"
        assert builds[0]["question_count"] == 1

    def test_template_cast_logs_template_source(self, _isolated_home: Path) -> None:
        from attune_forms.template_store import form_from_template

        form = form_from_template("session-contract", {"project": "attune-ai"})
        records = [
            json.loads(line)
            for line in _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        ]
        builds = [r for r in records if r["event"] == "form_build"]
        assert builds and builds[-1]["source"] == "template:session-contract"
        assert builds[-1]["form_id"] == form.form_id

    def test_surface_decision_carries_form_id(self, _isolated_home: Path) -> None:
        from attune_forms.bridge import form_from_dict, select_form_surface

        form = form_from_dict(dict(self.FORM))
        select_form_surface(form, widget_capable=True, keyboard_mode=False)
        records = [
            json.loads(line)
            for line in _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        ]
        surfaces = [r for r in records if r["event"] == "form_surface"]
        assert surfaces and surfaces[-1]["form_id"] == form.form_id

    def test_render_and_collect_join_on_one_form_id(self, _isolated_home: Path) -> None:
        """The pipeline receipt: dict → widget → collect, one form_id."""
        import asyncio

        from attune_forms.bridge import form_from_dict
        from attune_forms.mcp_server import handle_collect_response
        from attune_forms.widget import form_to_widget_html

        form = form_from_dict(dict(self.FORM))
        html = form_to_widget_html(form)
        result = asyncio.run(
            handle_collect_response({"form": dict(self.FORM), "answers": {"goal": "ship"}})
        )
        assert result["success"] is True

        records = [
            json.loads(line)
            for line in _events_file(_isolated_home).read_text(encoding="utf-8").splitlines()
        ]
        rendered = [r for r in records if r["event"] == "form_rendered"]
        submitted = [r for r in records if r["event"] == "form_submitted"]
        assert rendered[-1]["form_id"] == form.form_id
        assert rendered[-1]["html_bytes"] == len(html.encode("utf-8"))
        assert rendered[-1]["duration_ms"] >= 0
        assert submitted[-1]["form_id"] == form.form_id


class TestStageLatency:
    def _write(self, home: Path, records: list[dict]) -> None:
        path = _events_file(home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    def test_empty_store_returns_zeros(self) -> None:
        stats = stage_latency()
        assert stats["builds"] == stats["renders"] == stats["submissions"] == 0
        assert stats["joined"] == 0
        assert stats["render_ms"] is None and stats["submit_seconds"] is None

    def test_joins_and_percentiles(self, _isolated_home: Path) -> None:
        self._write(
            _isolated_home,
            [
                {"event": "form_build", "form_id": "a", "instance_id": "a" * 32, "source": "dict"},
                {
                    "event": "form_build",
                    "form_id": "b",
                    "instance_id": "b" * 32,
                    "source": "template:x",
                },
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T10:00:00.000000Z",
                    "duration_ms": 2.0,
                },
                {
                    "event": "form_rendered",
                    "form_id": "b",
                    "instance_id": "b" * 32,
                    "ts": "2026-08-24T10:01:00.000000Z",
                    "duration_ms": 4.0,
                },
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T10:00:10.000000Z",
                },
                {
                    "event": "form_submitted",
                    "form_id": "b",
                    "instance_id": "b" * 32,
                    "ts": "2026-08-24T10:01:30.000000Z",
                },
                # No render for this one — counted, never joined.
                {
                    "event": "form_submitted",
                    "form_id": "orphan",
                    "ts": "2026-08-24T10:02:00.000000Z",
                },
            ],
        )
        stats = stage_latency()
        assert stats["builds"] == 2
        assert stats["build_sources"] == {"dict": 1, "template:x": 1}
        assert stats["renders"] == 2 and stats["submissions"] == 3
        assert stats["joined"] == 2
        assert stats["render_ms"] == {"p50": 2.0, "p95": 4.0, "n": 2}
        assert stats["submit_seconds"] == {"p50": 10.0, "p95": 30.0, "n": 2}

    def test_submission_before_render_not_joined(self, _isolated_home: Path) -> None:
        self._write(
            _isolated_home,
            [
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T10:00:00.000000Z",
                    "duration_ms": 1.0,
                },
                # Stale submission from an earlier run of the same
                # content-addressed form — must not produce a negative wait.
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T09:59:00.000000Z",
                },
            ],
        )
        stats = stage_latency()
        assert stats["joined"] == 0
        assert stats["submit_seconds"] is None

    def test_malformed_lines_and_values_skipped(self, _isolated_home: Path) -> None:
        path = _events_file(_isolated_home)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "not json\n"
            + json.dumps(["not", "a", "dict"])
            + "\n"
            + json.dumps(
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "garbage",
                    "duration_ms": "fast",
                }
            )
            + "\n"
            + json.dumps({"event": "form_rendered", "form_id": 42, "duration_ms": -1})
            + "\n",
            encoding="utf-8",
        )
        stats = stage_latency()
        assert stats["renders"] == 2
        assert stats["render_ms"] is None  # no valid duration among them
        assert stats["joined"] == 0

    def test_reads_configured_home(self, tmp_path: Path, _isolated_home: Path) -> None:
        other = tmp_path / "dashboard-home"
        self._write(
            other,
            [{"event": "form_build", "form_id": "a", "instance_id": "a" * 32, "source": "dict"}],
        )
        assert stage_latency()["builds"] == 0
        assert stage_latency(home=other)["builds"] == 1

    def test_repeated_form_yields_one_pair_per_cycle(self, _isolated_home: Path) -> None:
        """Codex finding 1 (2026-08-24): form_id is content-derived, so a
        template cast every session shares one id — lifetime-first joining
        measured only the first cycle ever. Sequential pairing yields one
        wait sample per render→submit cycle."""
        self._write(
            _isolated_home,
            [
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-23T10:00:00.000000Z",
                    "duration_ms": 1.0,
                },
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-23T10:00:05.000000Z",
                },
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "c" * 32,
                    "ts": "2026-08-24T09:00:00.000000Z",
                    "duration_ms": 1.0,
                },
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "c" * 32,
                    "ts": "2026-08-24T09:00:15.000000Z",
                },
            ],
        )
        stats = stage_latency()
        assert stats["joined"] == 2
        assert stats["submit_seconds"] == {"p50": 5.0, "p95": 15.0, "n": 2}

    def test_stale_submission_does_not_block_later_valid_pair(self, _isolated_home: Path) -> None:
        """Codex finding 2 (2026-08-24): a submission predating every render
        (same content hash from an earlier run) must not consume or block the
        join — the later render→submit cycle still pairs."""
        self._write(
            _isolated_home,
            [
                # Stale submission from before this run's render.
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T09:00:00.000000Z",
                },
                {
                    "event": "form_rendered",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T10:00:00.000000Z",
                    "duration_ms": 1.0,
                },
                {
                    "event": "form_submitted",
                    "form_id": "a",
                    "instance_id": "a" * 32,
                    "ts": "2026-08-24T10:00:20.000000Z",
                },
            ],
        )
        stats = stage_latency()
        assert stats["joined"] == 1
        assert stats["submit_seconds"] == {"p50": 20.0, "p95": 20.0, "n": 1}


class TestDerivedFormIdNeverRaises:
    def test_hostile_str_value_degrades_to_empty_id(self) -> None:
        """Codex finding 3 (2026-08-24): json.dumps(default=str) re-raises
        whatever a value's __str__ raises — the telemetry id must degrade to
        empty, never make a valid definition fail to parse."""
        from attune_forms.bridge import form_from_dict

        class Hostile:
            def __str__(self) -> str:
                raise RuntimeError("boom")

        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {
                        "id": "q",
                        "text": "Q?",
                        "type": "text_input",
                        "help_text": Hostile(),
                    }
                ],
            }
        )
        assert form.form_id == ""


def test_overlapping_instances_join_exactly_once(_isolated_home: Path) -> None:
    """Identical definitions can finish in either order, including duplicate delivery."""
    records = []
    for event, instance, second in [
        ("form_rendered", "a", 0),
        ("form_rendered", "b", 10),
        ("form_submitted", "a", 20),
        ("form_submitted", "a", 30),
        ("form_submitted", "b", 100),
    ]:
        records.append(
            {
                "event": event,
                "form_id": "same",
                "instance_id": instance * 32,
                "ts": f"2026-09-04T00:{second // 60:02}:{second % 60:02}.000000Z",
            }
        )
    TestStageLatency()._write(_isolated_home, records)
    assert stage_latency()["submit_seconds"] == {"p50": 20.0, "p95": 90.0, "n": 2}


def test_legacy_events_do_not_invent_a_pair(_isolated_home: Path) -> None:
    TestStageLatency()._write(
        _isolated_home,
        [
            {"event": "form_rendered", "form_id": "same", "ts": "2026-09-04T00:00:00Z"},
            {"event": "form_submitted", "form_id": "same", "ts": "2026-09-04T00:00:10Z"},
        ],
    )
    stats = stage_latency()
    assert stats["renders"] == stats["submissions"] == 1
    assert stats["joined"] == 0
    assert stats["submit_seconds"] is None


def test_real_collect_preserves_instance_and_rejects_invalid_answers(_isolated_home: Path) -> None:
    import asyncio
    import re

    from attune_forms.mcp_server import handle_collect_response, handle_render_widget

    definition = {
        "title": "Repeated",
        "fields": [
            {
                "id": "choice",
                "text": "Choose",
                "type": "single_select",
                "options": ["yes", "no"],
                "required": True,
            }
        ],
    }
    first = asyncio.run(handle_render_widget({"form": definition}))
    second = asyncio.run(handle_render_widget({"form": definition}))
    ids = [
        re.search(r'instance_id: "([a-f0-9]{32})"', result["html"]).group(1)
        for result in (first, second)
    ]
    assert ids[0] != ids[1]
    bad = asyncio.run(
        handle_collect_response(
            {"form": definition, "answers": {"choice": "bad"}, "instance_id": ids[0]}
        )
    )
    assert bad["success"] is False
    assert stage_latency()["submissions"] == 0
    for instance in ids:
        good = asyncio.run(
            handle_collect_response(
                {"form": definition, "answers": {"choice": "yes"}, "instance_id": instance}
            )
        )
        assert good["success"] is True
    assert stage_latency()["joined"] == 2


def test_workspace_latency_separates_revision_and_event_family(_isolated_home: Path):
    from attune_forms.form_events import workspace_latency

    records = []
    for event, revision, second in [
        ("workspace_rendered", 1, 0),
        ("workspace_accepted", 2, 10),
        ("form_submitted", 1, 15),
        ("workspace_accepted", 1, 20),
        ("workspace_accepted", 1, 30),
    ]:
        records.append(
            {
                "event": event,
                "workspace_id": "w",
                "form_id": "w",
                "instance_id": "a" * 32,
                "revision": revision,
                "ts": f"2026-09-04T00:00:{second:02}.000000Z",
            }
        )
    TestStageLatency()._write(_isolated_home, records)
    stats = workspace_latency(_isolated_home)
    assert stats["accepted"] == 3
    assert stats["joined"] == 1
    assert stats["accept_seconds"] == {"p50": 20.0, "p95": 20.0, "n": 1}
    assert stage_latency()["joined"] == 0


def test_workspace_telemetry_rejects_invalid_metadata(_isolated_home: Path):
    from attune_forms.form_events import log_workspace_stage, workspace_latency

    for stage, token in [("clicked", "a" * 32), ("accepted", "bad")]:
        log_workspace_stage(
            stage, workspace_id="w", revision=1, instance_id=token, adapter_id="roundtable"
        )
    assert workspace_latency(_isolated_home)["accepted"] == 0


def test_workspace_stage_log_round_trip_and_failure_isolation(_isolated_home, monkeypatch):
    import attune_forms.form_events as events

    events.log_workspace_stage(
        "rendered",
        workspace_id="w",
        revision=1,
        instance_id="a" * 32,
        adapter_id="roundtable",
        duration_ms=2.0,
    )
    events.log_workspace_stage(
        "accepted",
        workspace_id="w",
        revision=1,
        instance_id="a" * 32,
        adapter_id="roundtable",
        action="decline",
    )
    assert events.workspace_latency(_isolated_home)["joined"] == 1
    assert events.workspace_latency(_isolated_home)["render_ms"]["p50"] == 2.0

    def unavailable(record):
        raise OSError("disk unavailable")

    monkeypatch.setattr(events, "_append", unavailable)
    events.log_workspace_stage(
        "accepted", workspace_id="w", revision=1, instance_id="a" * 32, adapter_id="roundtable"
    )


def test_workspace_reader_does_not_join_malformed_revision(_isolated_home):
    from attune_forms.form_events import workspace_latency

    TestStageLatency()._write(
        _isolated_home,
        [
            {
                "event": "workspace_rendered",
                "workspace_id": "w",
                "revision": True,
                "instance_id": "a" * 32,
                "ts": "2026-09-04T00:00:00.000000Z",
            },
            {
                "event": "workspace_accepted",
                "workspace_id": "w",
                "revision": True,
                "instance_id": "a" * 32,
                "ts": "2026-09-04T00:00:10.000000Z",
            },
        ],
    )
    assert workspace_latency(_isolated_home)["joined"] == 0
