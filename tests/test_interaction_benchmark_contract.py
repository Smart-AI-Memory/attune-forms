"""Contract tests for the vendor-neutral interaction benchmark assets."""

from __future__ import annotations

import json
from pathlib import Path

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

    # attune-forms may be an implementation under test, but the scoring
    # contract must not require attune-forms-specific runtime fields.
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

    families = {scenario["family"] for scenario in scenarios}
    assert families == EXPECTED_FAMILIES


def test_initial_fixture_ids_are_unique_and_seed_risk() -> None:
    payload = _load(SCENARIOS_PATH)
    scenarios = payload["scenarios"]
    assert isinstance(scenarios, list)

    ids = [scenario["id"] for scenario in scenarios]
    assert len(ids) == len(set(ids))

    for scenario in scenarios:
        assert scenario["seeded_risk"].strip()
        assert scenario["success_criteria"]
        assert scenario["hidden_requirements"]


def test_fixture_version_matches_schema_version_family() -> None:
    payload = _load(SCENARIOS_PATH)
    assert payload["benchmark_version"] == "0.1"
