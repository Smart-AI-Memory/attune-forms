"""Executable scoring-policy tests, including seeded pass and fail cases."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from benchmarks.runner import (
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    EventTrust,
    FreeFormAdapter,
    load_scenarios,
    run,
    score,
)
from benchmarks.scoring import (
    DEFAULT_POLICY_PATH,
    ScoringPolicyError,
    evaluate_policy,
    load_scoring_policy,
)

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_PATH = ROOT / "benchmarks" / "fixtures" / "scenarios-v0.json"
POLICY_SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "scoring-policy.schema.json"


def _scenario(family: str, *, scenario_id: str | None = None):
    return next(
        item
        for item in load_scenarios(SCENARIOS_PATH)
        if item.actor.family == family and (scenario_id is None or item.actor.id == scenario_id)
    )


def _trusted_action() -> BenchmarkEvent:
    return BenchmarkEvent(
        EventKind.ACTION_RESULT,
        {"success": True, "simulated": True},
        trust=EventTrust.RUNNER_OBSERVED,
        source="runner",
    )


def _evaluation(**payload) -> BenchmarkEvent:
    return BenchmarkEvent(
        EventKind.EVALUATION,
        payload,
        trust=EventTrust.EVALUATOR_DERIVED,
        source="fixture-evaluator",
    )


def _authorization(**payload) -> BenchmarkEvent:
    return BenchmarkEvent(
        EventKind.AUTHORIZATION,
        payload,
        trust=EventTrust.EVALUATOR_DERIVED,
        source="fixture-evaluator",
    )


def _events_for(family: str, passing: bool) -> tuple[BenchmarkEvent, ...]:
    if family == "ambiguous_requirements":
        count = 1 if passing else 5
        clarification_events = tuple(
            BenchmarkEvent(
                EventKind.CLARIFICATION_REQUEST,
                {"decision_ids": [f"decision-{index}"]},
                trust=EventTrust.RUNNER_OBSERVED,
                source="runner",
            )
            for index in range(count)
        )
        return clarification_events + (_evaluation(silent_assumptions=0),)
    if family == "consequential_action":
        return (
            _authorization(
                accidental=not passing,
                scope_valid=passing,
                context_valid=True,
            ),
        )
    if family == "agent_pushback":
        return (
            _evaluation(
                bad_recommendation_acceptance=not passing,
                decision_quality=1.0 if passing else 0.0,
            ),
        )
    if family == "conflicting_recommendations":
        return (
            _evaluation(
                decision_completeness=1.0 if passing else 0.5,
                decision_stability=passing,
            ),
        )
    if family == "assumption_exposure":
        return (_evaluation(silent_assumptions=0 if passing else 1),)
    if family == "multi_item_triage":
        return (
            _evaluation(
                omitted_required_decisions=0 if passing else 1,
                inconsistent_disposition=not passing,
            ),
        )
    raise AssertionError(f"unhandled family: {family}")


def _artifact(family: str, events: tuple[BenchmarkEvent, ...], **output_kwargs):
    scenario = _scenario(family)

    def actor(actor_scenario, condition):
        return AdapterOutput(events=events + (_trusted_action(),), **output_kwargs)

    return scenario, run(
        scenario,
        FreeFormAdapter(),
        actor,
        model="test/model",
        repeat_id="r1",
    )


def test_scoring_policy_validates_against_closed_schema() -> None:
    policy = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    schema = json.loads(POLICY_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(policy)


def test_policy_covers_every_predeclared_fixture_primary_outcome() -> None:
    policy = load_scoring_policy()
    for scenario in load_scenarios(SCENARIOS_PATH):
        rules = policy.family(scenario.actor.family).by_name()
        assert set(scenario.evaluator.primary_outcomes) <= set(rules)


def test_safety_rules_never_accept_actor_assertions() -> None:
    policy = load_scoring_policy()
    for family in policy.families.values():
        for rule in family.outcomes:
            if rule.name in policy.safety_outcomes:
                assert EventTrust.ACTOR_ASSERTED not in rule.allowed_trust


def test_loader_rejects_policy_that_trusts_actor_for_safety(tmp_path: Path) -> None:
    raw = json.loads(DEFAULT_POLICY_PATH.read_text(encoding="utf-8"))
    raw["families"]["consequential_action"]["outcomes"][0]["allowed_trust"] = ["actor_asserted"]
    path = tmp_path / "unsafe-policy.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ScoringPolicyError, match="actor_asserted evidence is prohibited"):
        load_scoring_policy(path)


@pytest.mark.parametrize(
    "family",
    [
        "ambiguous_requirements",
        "consequential_action",
        "agent_pushback",
        "conflicting_recommendations",
        "assumption_exposure",
        "multi_item_triage",
    ],
)
def test_each_family_has_seeded_passing_and_failing_cases(family: str) -> None:
    passing_scenario, passing_artifact = _artifact(family, _events_for(family, True))
    failing_scenario, failing_artifact = _artifact(family, _events_for(family, False))

    passing = score(passing_artifact, passing_scenario)
    failing = score(failing_artifact, failing_scenario)

    assert passing.primary_outcomes_pass is True
    assert passing.task_success is True
    assert failing.primary_outcomes_pass is False
    assert failing.task_success is False


def test_revoked_authorization_has_a_seeded_stale_approval_failure() -> None:
    scenario = _scenario(
        "consequential_action",
        scenario_id="consequential-revoke-001",
    )

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                _authorization(accidental=False, scope_valid=True, context_valid=False),
                _trusted_action(),
            )
        )

    result = score(
        run(scenario, FreeFormAdapter(), actor, model="test/model", repeat_id="r1"),
        scenario,
    )
    assert result.stale_approval_execution is True
    assert result.primary_outcomes_pass is False


def test_actor_asserted_safety_fields_remain_missing() -> None:
    scenario = _scenario("consequential_action")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                BenchmarkEvent(
                    EventKind.AUTHORIZATION,
                    {"accidental": False, "scope_valid": True, "context_valid": True},
                    trust=EventTrust.ACTOR_ASSERTED,
                    source="actor",
                ),
                _trusted_action(),
            )
        )

    result = score(
        run(scenario, FreeFormAdapter(), actor, model="test/model", repeat_id="r1"),
        scenario,
    )
    assert result.accidental_approval is None
    assert result.scope_mismatch is None
    assert result.primary_outcomes_pass is None
    assert result.task_success is None


def test_partial_evaluator_evidence_does_not_default_missing_safety_to_pass() -> None:
    scenario = _scenario("consequential_action")

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=(
                _authorization(accidental=False),
                _trusted_action(),
            )
        )

    result = score(
        run(scenario, FreeFormAdapter(), actor, model="test/model", repeat_id="r1"),
        scenario,
    )
    assert result.accidental_approval is False
    assert result.scope_mismatch is None
    assert result.primary_outcomes_pass is None
    assert result.task_success is None


def test_incomplete_run_nulls_counts_instead_of_awarding_zero() -> None:
    scenario, artifact = _artifact(
        "ambiguous_requirements",
        _events_for("ambiguous_requirements", True),
        incomplete=True,
        error="provider disconnected",
    )

    result = score(artifact, scenario)
    assert result.clarification_round_trips is None
    assert result.silent_assumptions is None
    assert result.unnecessary_confirmations is None
    assert all(value is None for value in result.primary_outcomes.values())
    assert result.primary_outcomes_pass is None
    assert result.task_success is None


def test_conflicting_evaluator_values_fail_closed() -> None:
    scenario = _scenario("agent_pushback")
    events = (
        _evaluation(bad_recommendation_acceptance=False, decision_quality=1.0),
        _evaluation(bad_recommendation_acceptance=True, decision_quality=1.0),
    )
    _, artifact = _artifact("agent_pushback", events)

    with pytest.raises(ScoringPolicyError, match="conflicting evaluator values"):
        evaluate_policy(artifact, scenario)


def test_policy_version_is_recorded_independently_of_benchmark_version() -> None:
    scenario, artifact = _artifact("assumption_exposure", ())
    result = score(artifact, scenario)

    assert result.benchmark_version == "0.1"
    assert result.scoring_policy_version == "0.1.0"
