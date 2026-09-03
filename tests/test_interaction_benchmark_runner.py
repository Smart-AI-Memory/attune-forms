"""Tests for the vendor-neutral benchmark runner core."""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.runner import (
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    FreeFormAdapter,
    SequentialClarificationAdapter,
    load_scenarios,
    results_to_jsonl,
    run,
    score,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "benchmarks" / "fixtures" / "scenarios-v0.json"


def _scenario(family: str):
    return next(item for item in load_scenarios(SCENARIOS) if item.actor.family == family)


def test_actor_callable_never_receives_evaluator_projection() -> None:
    scenario = _scenario("consequential_action")
    seen = {}

    def actor(actor_scenario, condition):
        seen["scenario"] = actor_scenario
        seen["condition"] = condition
        return AdapterOutput(events=(BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),))

    run(
        scenario,
        FreeFormAdapter(),
        actor,
        model="test/model",
        repeat_id="r1",
    )

    visible = seen["scenario"]
    assert visible.id == scenario.actor.id
    assert not hasattr(visible, "seeded_risk")
    assert not hasattr(visible, "hidden_requirements")
    assert scenario.evaluator.seeded_risk not in repr(visible)


def test_free_form_allows_batched_clarification() -> None:
    scenario = _scenario("ambiguous_requirements")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(
                    EventKind.CLARIFICATION_REQUEST,
                    {"decision_ids": ["target_path", "depth", "environment"]},
                ),
                BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),
            )
        )

    artifact = run(
        scenario,
        FreeFormAdapter(),
        actor,
        model="test/model",
        repeat_id="r1",
    )
    assert score(artifact, scenario).clarification_round_trips == 1


def test_sequential_adapter_rejects_batched_clarification() -> None:
    scenario = _scenario("ambiguous_requirements")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(
                    EventKind.CLARIFICATION_REQUEST,
                    {"decision_ids": ["target_path", "depth"]},
                ),
            )
        )

    with pytest.raises(ValueError, match="more than one unresolved decision"):
        run(
            scenario,
            SequentialClarificationAdapter(),
            actor,
            model="test/model",
            repeat_id="r1",
        )


def test_sequential_adapter_accepts_one_decision_per_request() -> None:
    scenario = _scenario("ambiguous_requirements")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(EventKind.CLARIFICATION_REQUEST, {"decision_ids": ["target_path"]}),
                BenchmarkEvent(EventKind.CLARIFICATION_REQUEST, {"decision_ids": ["depth"]}),
                BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),
            )
        )

    artifact = run(
        scenario,
        SequentialClarificationAdapter(),
        actor,
        model="test/model",
        repeat_id="r1",
    )
    assert score(artifact, scenario).clarification_round_trips == 2


def test_missing_telemetry_stays_missing_instead_of_becoming_zero() -> None:
    scenario = _scenario("assumption_exposure")

    def actor(actor_scenario, condition):
        return AdapterOutput(events=(BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),))

    result = score(
        run(
            scenario,
            FreeFormAdapter(),
            actor,
            model="test/model",
            repeat_id="r1",
        ),
        scenario,
    )

    assert result.tokens_input is None
    assert result.tokens_output is None
    assert result.elapsed_ms is None
    assert "token telemetry unavailable" in result.notes
    assert "latency telemetry unavailable" in result.notes


def test_invalid_authority_prevents_task_success() -> None:
    scenario = _scenario("consequential_action")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(
                    EventKind.AUTHORIZATION,
                    {"scope_valid": False, "context_valid": True, "accidental": False},
                ),
                BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),
            ),
            tokens_input=10,
            tokens_output=5,
            elapsed_ms=20,
        )

    result = score(
        run(
            scenario,
            FreeFormAdapter(),
            actor,
            model="test/model",
            repeat_id="r1",
        ),
        scenario,
    )
    assert result.scope_mismatch is True
    assert result.task_success is False


def test_unnecessary_confirmation_is_an_adverse_metric() -> None:
    scenario = _scenario("ambiguous_requirements")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(EventKind.AUTHORIZATION, {"unnecessary": True}),
                BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),
            )
        )

    result = score(
        run(
            scenario,
            FreeFormAdapter(),
            actor,
            model="test/model",
            repeat_id="r1",
        ),
        scenario,
    )
    assert result.unnecessary_confirmations == 1


def test_jsonl_keeps_condition_and_adapter_identity_separate() -> None:
    scenario = _scenario("multi_item_triage")

    def actor(actor_scenario, condition):
        return AdapterOutput(events=(BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),))

    result = score(
        run(
            scenario,
            FreeFormAdapter(),
            actor,
            model="test/model",
            repeat_id="r7",
        ),
        scenario,
    )
    payload = results_to_jsonl([result])
    assert '"condition": "free_form"' in payload
    assert '"adapter_id": "baseline/free-form"' in payload
    assert '"repeat_id": "r7"' in payload
