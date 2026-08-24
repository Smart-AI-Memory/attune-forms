"""Local-only log of form-surface routing decisions.

The decay guard for D21 (round table ``q-forms-default-vs-latency-001``,
Claude seat): flipping the default to the rich widget is only worth
something if the behaviour actually changes, so record what
:func:`attune.elicitation.select_form_surface` decided and let a later
read answer "did the mix move?" instead of assuming it did.

One event = one JSON line: ``v`` / ``ts`` / ``event`` / ``surface``
plus optional routing context.

**Stage events.** Beyond the routing decision, the pipeline emits one
event per lifecycle stage, joinable on ``form_id`` (derived
deterministically from the definition by
:func:`~attune_forms.bridge.form_from_dict`, so the render call and the
collect call — which each re-parse the same dict — land on the same id
without the agent threading anything):

- ``form_build`` — a definition was cast into a validated
  ``FormSchema`` (``source`` says how: ``"dict"`` or
  ``"template:<name>"``).
- ``form_rendered`` — the widget HTML was produced (``duration_ms``,
  ``html_bytes``).
- ``form_submitted`` — answers validated; carries ``form_id`` when the
  caller has one.

:func:`stage_latency` reads them back as per-stage p50/p95.

**What this can and cannot measure.** The live call site is the pair of
MCP elicitation handlers, where the tool the agent invoked *is* its
choice — so each record carries the router's recommendation (``surface``
/ ``reason``), what the agent actually did (``chosen``), and whether
they matched (``agreed``). That makes disagreement visible, not just
volume.

It still does NOT see a raw ``AskUserQuestion`` turn the agent wrote by
hand without building a ``FormSchema`` at all — that path never enters
Python. So the forms-vs-no-form ratio remains only partially observable
from here, and the missing half has to come from transcript inspection.
What *is* now observable is the narrower and more actionable signal:
when a form was built and the agent then flattened it anyway.

Consent model matches :mod:`attune.telemetry.memory_events`: LOCAL
recording is default-on and nothing ever leaves the machine.
``DO_NOT_TRACK`` or ``ATTUNE_FORM_TELEMETRY=0`` disables the log.
Never raises — routing must not fail because telemetry did.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_FALSEY = {"", "0", "false", "no", "off"}

#: Rotate when the live file exceeds this. Mirrors ``memory_events``.
_MAX_BYTES = 5 * 1024 * 1024


def _enabled() -> bool:
    """False when local form telemetry is switched off via env.

    ``ATTUNE_FORMS_TELEMETRY`` is the public name (P1 naming ruling);
    the legacy ``ATTUNE_FORM_TELEMETRY`` stays honored. A set new name
    wins; otherwise the legacy name decides.
    """
    new = os.environ.get("ATTUNE_FORMS_TELEMETRY")
    if new is not None:
        if new.strip().lower() in _FALSEY:
            return False
    elif os.environ.get("ATTUNE_FORM_TELEMETRY", "1").strip().lower() in _FALSEY:
        return False
    dnt = os.environ.get("DO_NOT_TRACK")
    return dnt is None or dnt.strip().lower() in _FALSEY


def _events_path(home: Path | None = None) -> Path:
    """Resolve the live events file under ``home`` (an attune-home base).

    Defaults to ATTUNE_HOME (or ``~/.attune``) — the write path. Readers
    with their own configured home (the ops dashboard) pass it
    explicitly so they read the store they display, not the process env.
    """
    if home is None:
        home = _default_home()
    return Path(home) / "telemetry" / "form_events.jsonl"


def _default_home() -> Path:
    """Resolve the data home (P1 naming ruling, spec D2).

    Precedence: ``ATTUNE_FORMS_HOME`` > legacy ``ATTUNE_HOME`` > an
    EXISTING ``~/.attune`` (keeps every current attune-ai machine
    byte-identical) > the XDG state dir
    (``$XDG_STATE_HOME/attune-forms``, default
    ``~/.local/state/attune-forms``) for standalone installs.
    """
    for var in ("ATTUNE_FORMS_HOME", "ATTUNE_HOME"):
        env = os.environ.get(var)
        if env:
            return Path(env).expanduser()
    legacy = Path.home() / ".attune"
    if legacy.exists():
        return legacy
    xdg = os.environ.get("XDG_STATE_HOME")
    state = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    return state / "attune-forms"


def _rotate_if_huge(path: Path) -> None:
    """Best-effort size backstop: rotate to a dated sibling when huge."""
    try:
        if path.stat().st_size < _MAX_BYTES:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rotated = path.with_name(f"form_events.{stamp}.jsonl")
        counter = 1
        while rotated.exists():
            rotated = path.with_name(f"form_events.{stamp}.{counter}.jsonl")
            counter += 1
        path.replace(rotated)
    except OSError:
        pass  # rotation is a nicety; the append below still works


def _append(record: dict[str, object]) -> None:
    """Append one record to the live log. Best-effort, never raises.

    The single write path every logger below shares: consent gate,
    directory creation, size rotation, compact one-line JSON.
    """
    try:
        if not _enabled():
            return
        path = _events_path()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        _rotate_if_huge(path)
        with path.open("a", encoding="utf-8") as fh:
            json.dump(record, fh, separators=(",", ":"), default=str)
            fh.write("\n")
    except Exception:
        # Telemetry is best-effort and this runs on live pipeline
        # paths: "never raises" must hold for MORE than OSError —
        # json.dump raises ValueError on a circular context and
        # ``default=str`` re-raises whatever a value's __str__ raises
        # (confirmation pass 1, 2026-08-20).
        pass


def _base_record(event: str) -> dict[str, object]:
    """Version + UTC timestamp + event kind — every record's spine."""
    return {
        "v": "1.0",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "event": event,
    }


def log_surface_decision(surface: str, **fields: object) -> None:
    """Append one surface-routing decision. Best-effort, never raises.

    Args:
        surface: The chosen surface — ``"widget"`` or ``"ask"``.
        **fields: Routing context (e.g. ``reason``, ``question_count``).
    """
    try:
        record = _base_record("form_surface")
        record["surface"] = str(surface)[:32]
        # Reserved keys always win: a caller kwarg named v/ts/event/
        # surface would forge records every reader keys on (e.g. a fake
        # "form_submitted" advancing the keyboard-hint counter) —
        # confirmation pass 1, 2026-08-20.
        record.update({k: v for k, v in fields.items() if k not in record})
        _append(record)
    except Exception:
        pass  # str(surface) runs caller __str__; same contract as _append


def log_form_build(form_id: str, *, source: str = "dict", question_count: int = 0) -> None:
    """Record that a definition was cast into a validated form.

    Args:
        form_id: The lifecycle join key (see ``form_from_dict``).
        source: How the cast happened — ``"dict"`` for a hand-built
            definition, ``"template:<name>"`` for a template cast. The
            V7 adoption signal: the mix of the two is the receipt that
            the template library is (or is not) actually used.
        question_count: Number of fields in the validated form.
    """
    try:
        record = _base_record("form_build")
        record["form_id"] = str(form_id)[:64]
        record["source"] = str(source)[:64]
        record["question_count"] = int(question_count)
        _append(record)
    except Exception:
        pass  # never-raises contract; coercions run caller code


def log_form_rendered(form_id: str, *, duration_ms: float, html_bytes: int) -> None:
    """Record that widget HTML was produced for a form.

    Args:
        form_id: The lifecycle join key.
        duration_ms: Wall-clock render time in milliseconds.
        html_bytes: Size of the rendered HTML in bytes.
    """
    try:
        record = _base_record("form_rendered")
        record["form_id"] = str(form_id)[:64]
        record["duration_ms"] = round(float(duration_ms), 3)
        record["html_bytes"] = int(html_bytes)
        _append(record)
    except Exception:
        pass  # never-raises contract; coercions run caller code


#: Form submissions before the one-time keyboard-mode hint fires. D17
#: ratified usage-triggered discovery ("after N form submissions"), not a
#: calendar timer — someone who never feels the friction never sees it.
_HINT_AFTER_SUBMISSIONS = 10

#: Shown to a user who has answered enough forms to have an opinion.
_KEYBOARD_HINT = (
    "You've answered several forms. If you'd rather answer with the "
    "keyboard than the mouse, turn on keyboard mode — "
    "`attune config set keyboard_mode true` — and asks that fit a plain "
    "question will come back as button turns instead of forms."
)


def log_submission(form_id: str | None = None) -> None:
    """Record that a user submitted a form. Best-effort, never raises.

    Args:
        form_id: The lifecycle join key, when the caller has one.
            Optional so pre-0.8 call sites (zero-arg) keep working;
            without it the submission still counts toward the keyboard
            hint but cannot join its ``form_rendered`` event.
    """
    try:
        record = _base_record("form_submitted")
        if form_id:
            record["form_id"] = str(form_id)[:64]
        _append(record)
    except Exception:
        pass  # same never-raises contract as log_surface_decision


def _hint_marker() -> Path:
    """Path of the once-only marker for the keyboard-mode hint."""
    return _events_path().with_name("keyboard_hint_shown")


def maybe_keyboard_hint(keyboard_mode: bool = False) -> str | None:
    """Return the keyboard-mode hint the first time it is earned, else None.

    Fires at most once ever, only after the user has actually answered
    :data:`_HINT_AFTER_SUBMISSIONS` forms, and never when they already
    have keyboard mode on. Writes the marker before returning so a caller
    that fires twice in one session still only shows it once.

    Args:
        keyboard_mode: Whether the user has already opted in.

    Returns:
        The hint text, or ``None``.
    """
    try:
        if keyboard_mode or not _enabled():
            return None
        marker = _hint_marker()
        if marker.exists():
            return None
        if submission_count() < _HINT_AFTER_SUBMISSIONS:
            return None
        marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        marker.write_text("shown\n", encoding="utf-8")
        return _KEYBOARD_HINT
    except OSError:
        return None


def submission_count(home: Path | None = None) -> int:
    """Number of form submissions recorded in the live log.

    Args:
        home: Optional attune-home base to read from; defaults to the
            process's own (ATTUNE_HOME or ``~/.attune``).
    """
    count = 0
    try:
        with _events_path(home).open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("event") == "form_submitted":
                    count += 1
    except OSError:
        return 0
    return count


def inference_rate(home: Path | None = None) -> dict[str, float | int]:
    """How much inference-first is actually happening.

    The decay guard for inference-first: the discipline lives in prompt
    guidance, so the only way to know it is being followed is to count
    it. A ``fields_inferred`` of zero across many forms means the
    instruction is not firing, whatever the docs say.

    Args:
        home: Optional attune-home base to read from; defaults to the
            process's own (ATTUNE_HOME or ``~/.attune``).

    Returns:
        ``forms``, ``fields``, ``fields_inferred``, ``fully_inferred``,
        and ``inferred_share`` (0.0–1.0). All zeros when nothing logged.
    """
    forms = fields = inferred = fully = 0
    try:
        with _events_path(home).open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict) or record.get("event") != "form_surface":
                    continue
                # Same skip-don't-raise contract as surface_mix: a line
                # with non-numeric counts is malformed and skipped whole,
                # so one corrupt record never breaks the read
                # (discovery-sweep finding, 2026-08-20).
                raw_fields = record.get("question_count") or 0
                raw_inferred = record.get("inferred_fields") or 0
                if any(
                    isinstance(raw, float) and not raw.is_integer()
                    for raw in (raw_fields, raw_inferred)
                ):
                    # A fractional count (``question_count: 2.7``) is the
                    # same malformed class: int() would silently truncate
                    # it, so the line is skipped whole
                    # (confirmation pass 1, 2026-08-20).
                    continue
                try:
                    line_fields = int(raw_fields)
                    line_inferred = int(raw_inferred)
                except (TypeError, ValueError):
                    continue
                if line_fields < 0 or line_inferred < 0 or line_inferred > line_fields:
                    # Malformed-record class: a negative count, or more
                    # inferred fields than total fields, is skipped whole
                    # so one corrupt record never pushes inferred_share
                    # outside [0, 1] (confirmation passes 1 and 2,
                    # 2026-08-20 — inferred_fields > question_count drove
                    # the share to 10.4).
                    continue
                forms += 1
                fields += line_fields
                inferred += line_inferred
                fully += 1 if record.get("fully_inferred") else 0
    except OSError:
        return {
            "forms": 0,
            "fields": 0,
            "fields_inferred": 0,
            "fully_inferred": 0,
            "inferred_share": 0.0,
        }
    return {
        "forms": forms,
        "fields": fields,
        "fields_inferred": inferred,
        "fully_inferred": fully,
        "inferred_share": round(inferred / fields, 3) if fields else 0.0,
    }


def surface_mix(home: Path | None = None) -> dict[str, int]:
    """Return counts per surface from the live log.

    Unreadable or malformed lines are skipped rather than raising, so a
    partially-written tail never breaks the read.

    Args:
        home: Optional attune-home base to read from; defaults to the
            process's own (ATTUNE_HOME or ``~/.attune``).

    Returns:
        A mapping of surface name to count; empty when nothing logged.
    """
    counts: Counter[str] = Counter()
    path = _events_path(home)
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("event") == "form_surface":
                    counts[str(record.get("surface", "(unknown)"))] += 1
    except OSError:
        return {}
    return dict(counts)


def _parse_ts(raw: object) -> datetime | None:
    """Parse a record's ``ts`` back to an aware datetime, or ``None``."""
    try:
        return datetime.strptime(str(raw), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _percentiles(values: list[float]) -> dict[str, float | int] | None:
    """Nearest-rank p50/p95 (plus ``n``) of ``values``, or ``None`` if empty."""
    if not values:
        return None
    ordered = sorted(values)

    def rank(q: float) -> float:
        return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]

    return {"p50": round(rank(0.50), 3), "p95": round(rank(0.95), 3), "n": len(ordered)}


def stage_latency(home: Path | None = None) -> dict[str, object]:
    """Per-stage latency read-back once stage events accrue.

    Joins ``form_rendered`` → ``form_submitted`` on ``form_id`` (first
    render, first submission at-or-after it) — the user-facing wait.
    Render cost comes straight from each ``form_rendered`` record's own
    ``duration_ms``, no join needed. Malformed lines, missing ids, and
    a submission with no matching render are skipped, never raised on —
    same read contract as :func:`surface_mix`.

    Args:
        home: Optional attune-home base to read from; defaults to the
            process's own (ATTUNE_HOME or ``~/.attune``).

    Returns:
        ``builds`` / ``renders`` / ``submissions`` (event counts),
        ``build_sources`` (cast-source mix — the V7 template-adoption
        signal), ``joined`` (render→submit pairs found), ``render_ms``
        and ``submit_seconds`` (each ``{"p50", "p95", "n"}`` or ``None``
        when no data).
    """
    builds = renders = submissions = 0
    sources: Counter[str] = Counter()
    render_ms: list[float] = []
    first_render: dict[str, datetime] = {}
    first_submit: dict[str, datetime] = {}
    try:
        with _events_path(home).open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(record, dict):
                    continue
                event = record.get("event")
                form_id = record.get("form_id")
                keyed = isinstance(form_id, str) and bool(form_id)
                stamp = _parse_ts(record.get("ts"))
                if event == "form_build":
                    builds += 1
                    sources[str(record.get("source", "(unknown)"))] += 1
                elif event == "form_rendered":
                    renders += 1
                    raw = record.get("duration_ms")
                    if isinstance(raw, (int, float)) and not isinstance(raw, bool) and raw >= 0:
                        render_ms.append(float(raw))
                    if (
                        keyed
                        and stamp
                        and stamp
                        < first_render.get(form_id, datetime.max.replace(tzinfo=timezone.utc))
                    ):
                        first_render[form_id] = stamp
                elif event == "form_submitted":
                    submissions += 1
                    if (
                        keyed
                        and stamp
                        and stamp
                        < first_submit.get(form_id, datetime.max.replace(tzinfo=timezone.utc))
                    ):
                        first_submit[form_id] = stamp
    except OSError:
        pass  # empty read below — zeros, not an error
    waits = [
        (first_submit[form_id] - rendered).total_seconds()
        for form_id, rendered in first_render.items()
        if form_id in first_submit and first_submit[form_id] >= rendered
    ]
    return {
        "builds": builds,
        "renders": renders,
        "submissions": submissions,
        "build_sources": dict(sources),
        "joined": len(waits),
        "render_ms": _percentiles(render_ms),
        "submit_seconds": _percentiles(waits),
    }
