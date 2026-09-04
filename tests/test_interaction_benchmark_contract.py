"""Contract tests for the vendor-neutral interaction benchmark assets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.runner import load_scenarios

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "result.schema.json"
SCENARIOS_PATH = ROOT / "benchmarks" / "fixtures" / "scenarios-v0.json"

EXPECTED_FAMILIES = {
    "ambiguous_requirements",
    "consequential_action",
    "agent_pushback",
    "conflicting_recommendations",
    "assumption_exposure",
    "multi_item_triage",
}
EXPECTED_CONDITIONS = {
    "free_form",
    "sequential_clarification",
    "typed_interaction",
    "host_native_structured",
}


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_result_schema_is_vendor_neutral() -> None:
    schema = _load(SCHEMA_PATH)
    serialized = json.dumps(schema).lower()
    assert "attune_forms" not in serialized
    assert schema["additionalProperties"] is False


def test_result_schema_declares_all_conditions() -> None:
    schema = _load(SCHEMA_PATH)
    properties = schema["properties"]
    assert isinstance(properties, dict)
    condition = properties["condition"]
    assert isinstance(condition, dict)
    assert set(condition["enum"]) == EXPECTED_CONDITIONS


def test_result_schema_requires_core_safety_metrics() -> None:
    schema = _load(SCHEMA_PATH)
    required = set(schema["required"])
    assert {
        "task_success",
        "silent_assumptions",
        "accidental_approval",
        "scope_mismatch",
        "stale_approval_execution",
    } <= required


def test_initial_fixtures_cover_every_scenario_family() -> None:
    payload = _load(SCENARIOS_PATH)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    families = {scenario["actor"]["family"] for scenario in scenarios}
    assert families == EXPECTED_FAMILIES


def test_actor_projection_contains_no_evaluator_secrets() -> None:
    payload = _load(SCENARIOS_PATH)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)

    forbidden = {"seeded_risk", "hidden_requirements", "success_criteria", "primary_outcomes"}
    for scenario in scenarios:
        actor = scenario["actor"]
        evaluator = scenario["evaluator"]
        assert forbidden.isdisjoint(actor)
        assert evaluator["seeded_risk"].strip()
        assert evaluator["success_criteria"]
        assert evaluator["hidden_requirements"]
        assert evaluator["primary_outcomes"]


def test_initial_fixture_ids_are_unique() -> None:
    payload = _load(SCENARIOS_PATH)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)
    ids = [scenario["actor"]["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))


def test_fixture_version_matches_schema_version_family() -> None:
    payload = _load(SCENARIOS_PATH)
    assert payload["benchmark_version"] == "0.1"


def test_loader_rejects_a_fixture_missing_a_required_family(tmp_path: Path) -> None:
    payload = _load(SCENARIOS_PATH)
    payload["scenarios"] = [
        scenario
        for scenario in payload["scenarios"]
        if scenario["actor"]["family"] != "multi_item_triage"
    ]
    fixture = tmp_path / "missing-family.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing required families: multi_item_triage"):
        load_scenarios(fixture)


def test_loader_rejects_an_unknown_family(tmp_path: Path) -> None:
    payload = _load(SCENARIOS_PATH)
    payload["scenarios"][0]["actor"]["family"] = "product_favoring_shortcut"
    fixture = tmp_path / "unknown-family.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown scenario family: product_favoring_shortcut"):
        load_scenarios(fixture)
