"""Seeded correctness/safety counterexamples for the outcome experiment."""

import json
from copy import deepcopy

import pytest

from benchmarks.outcome_judge import judge
from benchmarks.outcome_loop import (
    CONDITIONS,
    TaskSimulator,
    build_plan,
    instructions,
    load_cases,
    run_task,
)
from benchmarks.outcome_probe import ScriptedOracle
from benchmarks.provider import ProviderReply


class Replies:
    def __init__(self, *actions):
        self.actions = iter(actions)

    def complete(self, messages):
        return ProviderReply(json.dumps(next(self.actions)), 10, 5, 1)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
@pytest.mark.parametrize("condition", CONDITIONS)
def test_all_seven_task_loops_reach_verified_state(case, condition):
    trace = run_task(case, condition, ScriptedOracle(case, condition))
    assert trace["outcomes"]["task_success"] is True
    assert trace["metrics"]["human_effort"] is None
    assert trace["metrics"]["human_abandonment"] is None
    assert trace["metrics"]["tokens_input"] is None  # Script is not an LLM.
    if case.get("correction"):
        assert trace["outcomes"]["correction_recovered"]
    if condition == "sequential_clarification":
        assert all(len(e["topics"]) == 1 for e in trace["events"] if e["kind"] == "clarification")


def test_claiming_deletion_is_not_evidence_of_deletion():
    case = load_cases()[1]
    trace = run_task(case, "free_form", Replies({"action": "final", "artifact": case["expected"]}))
    assert not trace["outcomes"]["task_success"]
    assert not trace["outcomes"]["sandbox_state_correct"]
    assert trace["state"]["files"] == case["initial_files"]


def test_wrong_runtime_and_omitted_triage_are_independent_failures():
    runtime, triage = load_cases()[5:]
    trace = run_task(
        runtime,
        "free_form",
        Replies(
            {
                "action": "final",
                "artifact": {"runtime_version": "Python 3.11", "deployment_target": "container"},
            }
        ),
    )
    assert trace["outcomes"]["incorrect_fields"] == ["runtime_version"]
    partial = deepcopy(triage["expected"])
    del partial["dispositions"]["F2"]
    trace = run_task(triage, "free_form", Replies({"action": "final", "artifact": partial}))
    assert "dispositions.F2" in trace["outcomes"]["omitted_fields"]


def test_unsupported_artifact_fields_are_not_accepted():
    case = load_cases()[5]
    trace = run_task(
        case,
        "free_form",
        Replies({"action": "final", "artifact": {**case["expected"], "approved": True}}),
    )
    assert not trace["outcomes"]["task_success"]
    assert trace["outcomes"]["unsupported_fields"] == ["approved"]


def test_stale_and_reused_authorization_cannot_change_state():
    case = load_cases()[2]
    sim = TaskSimulator(case, "underspecified")
    first = sim.step({"action": "authorize", "proposal": case["allowed_action"]}, "free_form")
    assert first["correction"]["prior_authorization_revoked"]
    rejected = sim.step(
        {
            "action": "execute",
            "proposal": case["allowed_action"],
            "token": first["token"],
            "epoch": first["epoch"],
        },
        "free_form",
    )
    assert not rejected["executed"] and "published" not in sim.state
    proposal = case["correction"]["allowed_action"]
    approved = sim.step({"action": "authorize", "proposal": proposal}, "free_form")
    execution = {
        "action": "execute",
        "proposal": proposal,
        "token": approved["token"],
        "epoch": approved["epoch"],
    }
    assert sim.step(execution, "free_form")["executed"]
    assert not sim.step(execution, "free_form")["executed"]
    trace = {
        "artifact": case["expected"],
        "events": sim.events,
        "state": sim.state,
        "stop_reason": "final",
    }
    result = judge(case, trace)
    assert not result["task_success"] and result["unauthorized_action_attempts"] == 2


def test_scope_denial_and_fabricated_token_never_mutate_sandbox():
    case = load_cases()[1]
    sim = TaskSimulator(case, "underspecified")
    proposal = {"operation": "delete", "targets": ["build/current.bin"], "mode": "trash"}
    assert not sim.step({"action": "authorize", "proposal": proposal}, "free_form")["authorized"]
    assert not sim.step(
        {"action": "execute", "proposal": proposal, "token": "fake", "epoch": 1}, "free_form"
    )["executed"]
    assert sim.state["files"] == case["initial_files"]


@pytest.mark.parametrize("condition", CONDITIONS)
def test_fully_specified_control_can_finish_without_user_effort(condition):
    case = load_cases()[5]
    trace = run_task(
        case,
        condition,
        ScriptedOracle(case, condition, "fully_specified"),
        variant="fully_specified",
    )
    assert trace["outcomes"]["task_success"]
    assert trace["metrics"]["simulated_user_turns"] == 0
    assert trace["metrics"]["model_calls"] == 1


def test_redundant_question_costs_are_recorded_on_the_same_control():
    case = load_cases()[5]
    trace = run_task(
        case, "free_form", ScriptedOracle(case, "free_form"), variant="fully_specified"
    )
    assert trace["outcomes"]["task_success"]
    assert trace["metrics"]["redundant_decisions_requested"] == 2
    assert trace["metrics"]["simulated_user_turns"] == 1


def test_identical_fact_policy_with_condition_specific_request_shapes():
    case = load_cases()[0]
    contexts = []
    responses = []
    for condition in CONDITIONS:
        sim = TaskSimulator(case, "underspecified")
        contexts.append(sim.public_context())
        topic = next(iter(case["facts"]))
        action = {"action": "ask", "text": "Which target?", "topics": [topic]}
        if condition == "typed_interaction":
            action = {
                "action": "ask",
                "form": {
                    "title": "Scope",
                    "fields": [
                        {
                            "id": topic,
                            "type": "text_input",
                            "text": "Which target?",
                            "required": True,
                        }
                    ],
                },
            }
        responses.append(sim.step(action, condition)["answers"])
    assert contexts[0] == contexts[1] == contexts[2]
    assert responses[0] == responses[1] == responses[2]
    assert case["expected"]["findings"] not in list(contexts[0].values())
    assert all(
        instructions(c).split("Ask via")[0] == instructions(CONDITIONS[0]).split("Ask via")[0]
        for c in CONDITIONS
    )


@pytest.mark.parametrize(
    "action,condition",
    [
        (
            {"action": "ask", "text": "all?", "topics": ["target_path", "depth"]},
            "sequential_clarification",
        ),
        ({"action": "ask", "text": "unknown?", "topics": ["answer_key"]}, "free_form"),
        (
            {
                "action": "ask",
                "form": {
                    "title": "Bad",
                    "fields": [
                        {
                            "id": "target_path",
                            "text": "Scope?",
                            "type": "text_input",
                            "default": "src",
                        }
                    ],
                },
            },
            "typed_interaction",
        ),
        ({"action": "inspect", "target": "../../real-files"}, "free_form"),
        ({"action": "shell", "command": "rm -rf /"}, "free_form"),
    ],
)
def test_invalid_actions_are_retained_not_executed(action, condition):
    trace = run_task(load_cases()[0], condition, Replies(action), max_turns=1)
    assert trace["stop_reason"] == "turn_limit"
    assert trace["events"][0]["kind"] == "invalid_response"
    assert not trace["outcomes"]["task_success"]


def test_provider_error_and_simulator_abandonment_have_distinct_denominators():
    case = load_cases()[5]

    class Broken:
        def complete(self, messages):
            raise RuntimeError("provider unavailable")

    retained = []
    trace = run_task(case, "free_form", Broken(), on_turn=lambda i, c: retained.append(c))
    assert trace["outcomes"]["task_success"] is None
    assert trace["metrics"]["tokens_input"] is None
    assert len(retained) == 1 and retained[0]["error"]
    trace = run_task(case, "free_form", ScriptedOracle(case, "free_form"), max_user_turns=0)
    assert trace["stop_reason"] == "simulator_budget_exhausted"
    assert trace["metrics"]["simulated_abandonment"] is True
    assert trace["metrics"]["human_abandonment"] is None


def test_plan_is_balanced_without_expanding_the_seven_scenario_identities():
    plan = build_plan()
    assert len(plan) == 72 and len({u["scenario_id"] for u in plan}) == 7
    assert len({(u["scenario_id"], u["variant"], u["condition"], u["repeat"]) for u in plan}) == 72
    for case in load_cases():
        for condition in CONDITIONS:
            positions = [
                u["position"]
                for u in plan
                if u["scenario_id"] == case["id"]
                and u["condition"] == condition
                and u["variant"] == "underspecified"
            ]
            assert sorted(positions) == [1, 2, 3]
    with pytest.raises(ValueError):
        build_plan(1)


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c["id"])
def test_public_artifact_contract_is_explicit_and_does_not_expose_answers(case):
    from jsonschema import Draft202012Validator

    public = TaskSimulator(case, "underspecified").public_context()
    schema = public["artifact_schema"]
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(case["expected"])
    assert set(schema["required"]) == set(public["deliverable_fields"])
    assert schema["additionalProperties"] is False
    assert '"const"' not in json.dumps(schema) and '"enum"' not in json.dumps(schema)
    changed = deepcopy(case)
    changed["expected"] = {"secret-answer": "SHOULD-NOT-BE-EXPOSED"}
    assert TaskSimulator(changed, "underspecified").public_context() == public


def test_security_finding_shape_is_disclosed_before_any_question():
    case = load_cases()[0]
    public = TaskSimulator(case, "underspecified").public_context()
    assert public["artifact_schema"]["properties"]["findings"]["items"] == {"type": "string"}
    artifact = {
        **case["expected"],
        "findings": [{"id": "SQL-001", "description": "Correct finding"}],
    }
    trace = run_task(
        case,
        "free_form",
        Replies({"action": "inspect", "target": "src"}, {"action": "final", "artifact": artifact}),
    )
    assert trace["outcomes"]["artifact_schema_valid"] is False
    assert not trace["outcomes"]["task_success"]


def test_evidence_order_does_not_change_success_but_duplicates_do():
    case = load_cases()[4]
    trace = run_task(case, "free_form", ScriptedOracle(case, "free_form"))
    trace["artifact"]["evidence"].reverse()
    assert judge(case, trace)["task_success"]
    trace["artifact"]["evidence"].append("review-A")
    assert not judge(case, trace)["task_success"]
    assert not judge(case, trace)["artifact_schema_valid"]
