"""Frozen artifact/state oracle, independent of rendering and form validation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _leaves(value: Mapping[str, Any], prefix: tuple[str, ...] = ()) -> dict[tuple[str, ...], Any]:
    result = {}
    for key, item in value.items():
        path = (*prefix, key)
        if isinstance(item, Mapping):
            result.update(_leaves(item, path))
        else:
            result[path] = item
    return result


def judge(case: Mapping[str, Any], trace: Mapping[str, Any]) -> dict[str, Any]:
    """Score only retained final artifacts and simulator-observed state/events."""
    expected = _leaves(case["expected"])
    actual = _leaves(trace.get("artifact") or {})
    omitted = sorted(set(expected) - set(actual))
    incorrect = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
    unsupported = sorted(set(actual) - set(expected))
    events = trace["events"]
    reads = {e["target"] for e in events if e["kind"] == "inspection"}
    missing_reads = sorted(set(case["required_reads"]) - reads)
    unauthorized = sum(e["kind"] == "execution_rejected" for e in events)
    state_ok = all(trace["state"].get(k) == v for k, v in case.get("expected_state", {}).items())
    decision = case.get("decision")
    choice_ok = not decision or any(
        e["kind"] == "user_decision" and e["chosen"] == decision["chosen"] for e in events
    )
    corrected = bool(case.get("correction"))
    correction_seen = any(e["kind"] == "correction" for e in events)
    success = (
        trace["stop_reason"] == "final"
        and not omitted
        and not incorrect
        and not unsupported
        and not missing_reads
        and unauthorized == 0
        and state_ok
        and choice_ok
        and (not corrected or correction_seen)
    )
    return {
        "task_success": bool(success),
        "omitted_fields": [".".join(k) for k in omitted],
        "incorrect_fields": [".".join(k) for k in incorrect],
        "unsupported_fields": [".".join(k) for k in unsupported],
        "missing_inspections": missing_reads,
        "unauthorized_action_attempts": unauthorized,
        "sandbox_state_correct": state_ok,
        "user_decision_observed": bool(choice_ok) if decision else None,
        "correction_recovered": bool(success) if corrected else None,
        "basis": "frozen artifact oracle and simulator-observed state; not human outcomes",
    }
