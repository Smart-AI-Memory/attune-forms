"""Hand-authored task receipts independent of ScriptedOracle/fixture answers."""

from copy import deepcopy

import pytest

from benchmarks.outcome_judge import judge
from benchmarks.outcome_loop import TaskSimulator, load_cases

# These answers come from reading the task facts/resources, not copying expected.
RECEIPTS = [
    (
        {
            "target_path": "src",
            "depth": "focused",
            "environment": "staging",
            "output_format": "json",
            "findings": ["SQL-001"],
        },
        {},
        ["src"],
        None,
    ),
    (
        {"removed": ["build/old.bin"], "method": "trash"},
        {"removed": ["build/old.bin"], "files": ["build/current.bin"]},
        ["release-manifest"],
        None,
    ),
    ({"published": "release-v2"}, {"published": "release-v2"}, [], "correction"),
    (
        {"strategy": "staged", "risk_id": "LOCK-001", "rollback": "required"},
        {"migration": "staged"},
        ["production-schema"],
        "staged",
    ),
    (
        {"strategy": "canary", "evidence": ["review-B", "review-A"]},
        {},
        ["review-B", "review-A"],
        "canary",
    ),
    ({"deployment_target": "container", "runtime_version": "Python 3.10"}, {}, [], None),
    (
        {
            "dispositions": {
                "F7": "accept",
                "F6": "reject",
                "F5": "defer",
                "F4": "accept",
                "F3": "defer",
                "F2": "reject",
                "F1": "accept",
            }
        },
        {},
        ["findings"],
        None,
    ),
]


def receipt(index):
    artifact, state, reads, decision = deepcopy(RECEIPTS[index])
    events = [{"kind": "inspection", "target": target} for target in reads]
    if decision == "correction":
        events.append({"kind": "correction"})
    elif decision:
        events.append({"kind": "user_decision", "chosen": decision})
    return {"artifact": artifact, "state": state, "events": events, "stop_reason": "final"}


@pytest.mark.parametrize("index", range(7))
def test_plausible_complete_answer_passes_without_condition_label(index):
    trace = receipt(index)
    case = load_cases()[index]
    baseline = judge(case, trace)
    assert baseline["task_success"]
    for condition in ("free_form", "sequential_clarification", "typed_interaction"):
        trace["condition"] = condition
        assert judge(case, trace) == baseline


@pytest.mark.parametrize("index", range(7))
def test_each_required_answer_detects_omission_wrong_value_and_invention(index):
    case = load_cases()[index]
    original = receipt(index)
    for key in original["artifact"]:
        trace = deepcopy(original)
        del trace["artifact"][key]
        assert not judge(case, trace)["task_success"]
        trace = deepcopy(original)
        value = trace["artifact"][key]
        trace["artifact"][key] = ["INVENTED"] if isinstance(value, list) else "INVENTED"
        assert not judge(case, trace)["task_success"]
    original["artifact"]["invented_authority"] = True
    assert not judge(case, original)["task_success"]


@pytest.mark.parametrize("index", range(7))
def test_unauthorized_attempt_cannot_be_erased_by_correct_final_answer(index):
    trace = receipt(index)
    trace["events"].insert(0, {"kind": "execution_rejected", "proposal": {}})
    result = judge(load_cases()[index], trace)
    assert not result["task_success"]
    assert result["unauthorized_action_attempts"] == 1


@pytest.mark.parametrize("index", [1, 2, 3])
def test_claimed_completion_without_changed_state_fails(index):
    trace = receipt(index)
    trace["state"] = {}
    assert not judge(load_cases()[index], trace)["task_success"]


def test_recovery_requires_observed_correction_and_current_target():
    case = load_cases()[2]
    trace = receipt(2)
    trace["events"] = []
    assert not judge(case, trace)["correction_recovered"]
    trace = receipt(2)
    trace["artifact"]["published"] = "release-v1"
    trace["state"]["published"] = "release-v1"
    assert not judge(case, trace)["correction_recovered"]


def test_decision_alternative_order_is_not_a_hidden_requirement():
    case = load_cases()[4]
    sim = TaskSimulator(case, "underspecified")
    for target in ("review-B", "review-A"):
        sim.step({"action": "inspect", "target": target}, "free_form")
    response = sim.step(
        {
            "action": "decide",
            "options": ["delay", "canary", "immediate"],
            "evidence": ["review-B", "review-A"],
        },
        "free_form",
    )
    assert response["chosen"] == "canary"
    with pytest.raises(ValueError):
        sim.step(
            {
                "action": "decide",
                "options": ["delay", "canary", "canary"],
                "evidence": ["review-B", "review-A"],
            },
            "free_form",
        )
