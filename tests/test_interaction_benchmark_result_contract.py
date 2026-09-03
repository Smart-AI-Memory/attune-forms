"""Serialization and failure-path tests for benchmark results."""

from __future__ import annotations

import json
from pathlib import Path

from benchmarks.runner import (
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    FreeFormAdapter,
    load_scenarios,
    results_to_jsonl,
    run,
    score,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "benchmarks" / "fixtures" / "scenarios-v0.json"
SCHEMA = ROOT / "benchmarks" / "schema" / "result.schema.json"


def _first_scenario():
    return load_scenarios(SCENARIOS)[0]


def test_serialized_result_keys_match_closed_schema() -> None:
    scenario = _first_scenario()

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
    serialized = json.loads(results_to_jsonl([result]))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert set(serialized) == set(schema["properties"])
    assert set(schema["required"]) <= set(serialized)


def test_incomplete_run_is_retained_and_cannot_score_success() -> None:
    scenario = _first_scenario()

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),),
            incomplete=True,
            error="provider timeout after final action event",
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

    assert result.incomplete is True
    assert result.error == "provider timeout after final action event"
    assert result.task_success is False
    assert '"incomplete": true' in results_to_jsonl([result])


def test_evaluator_fields_never_appear_in_result_jsonl() -> None:
    scenario = _first_scenario()

    def actor(actor_scenario, condition):
        return AdapterOutput(events=(BenchmarkEvent(EventKind.ACTION_RESULT, {"success": True}),))

    payload = results_to_jsonl(
        [
            score(
                run(
                    scenario,
                    FreeFormAdapter(),
                    actor,
                    model="test/model",
                    repeat_id="r1",
                ),
                scenario,
            )
        ]
    )
    assert scenario.evaluator.seeded_risk not in payload
    for hidden in scenario.evaluator.hidden_requirements:
        assert hidden not in payload
