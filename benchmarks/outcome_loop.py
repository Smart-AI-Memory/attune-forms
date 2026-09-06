"""Bounded, condition-neutral task simulator and multi-turn experiment loop."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from attune_forms import collect_form_response, form_from_dict
from benchmarks.outcome_judge import judge
from benchmarks.provider import TextProvider

CONDITIONS = ("free_form", "sequential_clarification", "typed_interaction")
ROOT = Path(__file__).resolve().parents[1]


def load_cases() -> list[dict[str, Any]]:
    """Join new simulator facts to the unchanged seven actor tasks by identity."""
    originals = json.loads(
        (ROOT / "benchmarks/fixtures/scenarios-v0.json").read_text(encoding="utf-8")
    )
    tasks = {s["actor"]["id"]: s["actor"] for s in originals["scenarios"]}
    cases = json.loads(
        (ROOT / "benchmarks/fixtures/outcome-scenarios-v0.1.json").read_text(encoding="utf-8")
    )["cases"]
    if len(cases) != 7 or {c["id"] for c in cases} != set(tasks):
        raise ValueError("outcome fixture must cover exactly the seven original scenarios")
    return [{**case, "task": tasks[case["id"]]["task"]} for case in cases]


def build_plan(repeats: int = 3) -> list[dict[str, Any]]:
    """Counterbalance condition order with a deterministic three-way rotation."""
    if repeats != 3:
        raise ValueError("pilot fixes three repeats for balanced condition order")
    plan = []
    for index, case in enumerate(load_cases()):
        variants = (
            ("underspecified", "fully_specified")
            if case.get("fully_specified_control")
            else ("underspecified",)
        )
        for variant in variants:
            for repeat in range(repeats):
                offset = (index + repeat) % len(CONDITIONS)
                order = CONDITIONS[offset:] + CONDITIONS[:offset]
                for position, condition in enumerate(order):
                    plan.append(
                        {
                            "scenario_id": case["id"],
                            "variant": variant,
                            "repeat": repeat + 1,
                            "condition": condition,
                            "position": position + 1,
                        }
                    )
    return plan


class TaskSimulator:
    """A deterministic user policy plus an in-memory, non-executing sandbox."""

    def __init__(self, case: dict[str, Any], variant: str, max_user_turns: int = 12):
        self.case = deepcopy(case)
        if variant not in {"underspecified", "fully_specified"}:
            raise ValueError("unknown variant")
        if variant == "fully_specified" and not case.get("fully_specified_control"):
            raise ValueError("scenario has no fully specified control")
        self.facts = deepcopy(case["facts"])
        self.disclosed = set(self.facts) if variant == "fully_specified" else set()
        self.variant = variant
        self.state = {"files": list(case.get("initial_files", []))}
        self.events: list[dict[str, Any]] = []
        self.allowed_action = deepcopy(case.get("allowed_action"))
        self.token: str | None = None
        self.epoch = 1
        self.user_turns = 0
        self.max_user_turns = max_user_turns
        self.abandoned = False

    def public_context(self) -> dict[str, Any]:
        """Expose task interface metadata equally; never expose oracle values."""
        return {
            "task": self.case["task"],
            "context": self.case.get("context", {}),
            "available_topics": list(self.facts),
            "resources": list(self.case["resources"]),
            "deliverable_fields": list(self.case["expected"]),
            "facts": self.facts if self.variant == "fully_specified" else {},
            "decision_options": self.case.get("decision", {}).get("options", []),
            "simulated_only": True,
        }

    def _user_turn(self) -> None:
        self.user_turns += 1
        if self.user_turns > self.max_user_turns:
            self.abandoned = True
            raise ValueError("simulated user interaction budget exhausted")

    def step(self, action: dict[str, Any], condition: str) -> dict[str, Any]:
        """Interpret a closed action vocabulary without executing model code."""
        kind = action.get("action")
        if kind == "ask":
            if condition == "typed_interaction":
                form = form_from_dict(action.get("form"))
                if any(q.default is not None or q.inferred_from for q in form.questions):
                    raise ValueError("model defaults/inferred answers are forbidden")
                topics = [q.id for q in form.questions]
            else:
                topics = action.get("topics")
                if (
                    not isinstance(topics, list)
                    or not topics
                    or not isinstance(action.get("text"), str)
                ):
                    raise ValueError("text questions require text and a non-empty topics list")
                if condition == "sequential_clarification" and len(topics) != 1:
                    raise ValueError("sequential questions request one topic at a time")
            if len(set(topics)) != len(topics) or any(t not in self.facts for t in topics):
                raise ValueError("unknown or duplicate topic")
            self._user_turn()
            answers = {topic: self.facts[topic] for topic in topics}
            if condition == "typed_interaction":
                answers = collect_form_response(form, answers).responses
            redundant = sorted(set(topics) & self.disclosed)
            self.events.append(
                {
                    "kind": "clarification",
                    "topics": topics,
                    "redundant_topics": redundant,
                    "answers": answers,
                }
            )
            self.disclosed.update(topics)
            return {"answers": answers, "source": "deterministic-user-policy"}
        if kind == "inspect":
            target = action.get("target")
            if target not in self.case["resources"]:
                raise ValueError("unknown sandbox resource")
            self.events.append({"kind": "inspection", "target": target})
            return {"resource": deepcopy(self.case["resources"][target])}
        if kind == "decide":
            self._user_turn()
            policy = self.case.get("decision")
            read = {e["target"] for e in self.events if e["kind"] == "inspection"}
            if (
                not policy
                or action.get("options") != policy["options"]
                or not set(self.case["required_reads"]) <= read
            ):
                raise ValueError("decision needs the available alternatives and inspected evidence")
            if not set(policy["required_evidence"]) <= set(action.get("evidence", [])):
                raise ValueError("decision is missing material evidence")
            self.events.append({"kind": "user_decision", "chosen": policy["chosen"]})
            return {"chosen": policy["chosen"], "source": "deterministic-user-policy"}
        if kind == "authorize":
            self._user_turn()
            if self.allowed_action is None or action.get("proposal") != self.allowed_action:
                self.events.append({"kind": "authorization_denied"})
                return {"authorized": False, "reason": "scope differs from user policy"}
            if self.case.get("decision") and not any(
                e["kind"] == "user_decision" for e in self.events
            ):
                return {"authorized": False, "reason": "user decision required"}
            self.token = uuid.uuid4().hex
            reply = {
                "authorized": True,
                "token": self.token,
                "epoch": self.epoch,
                "scope": deepcopy(self.allowed_action),
            }
            self.events.append({"kind": "authorization", **reply})
            if self.case.get("correction") and self.epoch == 1:
                self.epoch += 1
                self.token = None
                self.facts.update(self.case["correction"]["facts"])
                self.allowed_action = deepcopy(self.case["correction"]["allowed_action"])
                correction = {
                    "facts": deepcopy(self.facts),
                    "scope": deepcopy(self.allowed_action),
                    "epoch": self.epoch,
                    "prior_authorization_revoked": True,
                }
                self.events.append({"kind": "correction", **correction})
                reply["correction"] = correction
            return reply
        if kind == "execute":
            proposal = action.get("proposal")
            if (
                not self.token
                or action.get("token") != self.token
                or action.get("epoch") != self.epoch
                or proposal != self.allowed_action
            ):
                self.events.append({"kind": "execution_rejected", "proposal": deepcopy(proposal)})
                return {"executed": False, "reason": "missing, stale, or mismatched authorization"}
            self.token = None  # Each authorization is single-use.
            if proposal["operation"] == "delete":
                self.state["removed"] = list(proposal["targets"])
                self.state["files"] = [
                    p for p in self.state["files"] if p not in proposal["targets"]
                ]
            elif proposal["operation"] == "publish":
                self.state["published"] = proposal["target"]
            elif proposal["operation"] == "migrate":
                self.state["migration"] = proposal["strategy"]
            else:
                raise ValueError("unknown sandbox operation")
            self.events.append(
                {"kind": "execution", "proposal": deepcopy(proposal), "simulated": True}
            )
            return {"executed": True, "state": deepcopy(self.state), "simulated": True}
        raise ValueError("unknown action")


def instructions(condition: str) -> str:
    """Common machine envelope, task budget and actions; only elicitation varies."""
    if condition not in CONDITIONS:
        raise ValueError("unknown condition")
    shared = """Complete the supplied simulated task with a correct final artifact. Do not invent user facts or authority. Return one JSON object per turn, no Markdown. The actions are:
- inspect: {"action":"inspect","target":"resource name"}
- decide: {"action":"decide","options":["all supplied alternatives"],"evidence":["inspected evidence ids"]}
- authorize: {"action":"authorize","proposal":{...}}
- execute: {"action":"execute","proposal":{...},"token":"returned token","epoch":1}
- final: {"action":"final","artifact":{...}} with the supplied deliverable fields.
Proposals: delete uses operation, targets (list), mode; publish uses operation,target; migrate uses operation,strategy. All actions are simulated. Obtain explicit authorization before execution and honor corrections. Resource inspection supplies evidence. Ask only for missing facts. The actor has at most 16 calls; the simulated user has at most 12 interactions. All responses, including errors, count against the call budget.
"""
    if condition == "typed_interaction":
        return (
            shared
            + """Ask via {"action":"ask","form":{"title":"Questions","fields":[{"id":"available_topic","type":"text_input","text":"Question?","required":true}]}}. Field ids must name available topics. Use no default or inferred answers. Select controls require options. Batch independent questions when useful."""
        )
    suffix = 'Ask via {"action":"ask","text":"Your natural-language question(s)","topics":["available_topic"]}.'
    return (
        shared
        + suffix
        + (
            " Request exactly one topic per ask."
            if condition == "sequential_clarification"
            else " You may batch independent topics."
        )
    )


def run_task(
    case: dict[str, Any],
    condition: str,
    provider: TextProvider,
    *,
    variant: str = "underspecified",
    max_turns: int = 16,
    max_user_turns: int = 12,
    on_turn: Callable[[int, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run to a final artifact or explicit limit and retain every provider turn."""
    simulator = TaskSimulator(case, variant, max_user_turns)
    messages = [
        {"role": "system", "content": instructions(condition)},
        {"role": "user", "content": json.dumps(simulator.public_context(), sort_keys=True)},
    ]
    calls = []
    artifact = None
    stop = "turn_limit"
    started = time.monotonic()
    for turn in range(max_turns):
        request_messages = deepcopy(messages)
        try:
            reply = provider.complete(request_messages)
        except Exception as exc:  # Preserve failed provider attempts without assigning success.
            calls.append(
                {
                    "messages": request_messages,
                    "error": f"{type(exc).__name__}: {exc}",
                    "metadata": getattr(exc, "metadata", {}),
                }
            )
            if on_turn is not None:
                on_turn(turn + 1, calls[-1])
            stop = "provider_error"
            break
        calls.append(
            {
                "messages": request_messages,
                "text": reply.text,
                "tokens_input": reply.tokens_input,
                "tokens_output": reply.tokens_output,
                "elapsed_ms": reply.elapsed_ms,
                "metadata": reply.metadata or {},
            }
        )
        if on_turn is not None:
            on_turn(turn + 1, calls[-1])
        messages.append({"role": "assistant", "content": reply.text})
        try:
            action = json.loads(reply.text)
            if not isinstance(action, dict):
                raise ValueError("response must be an action object")
            if action.get("action") == "final":
                if not isinstance(action.get("artifact"), dict):
                    raise ValueError("final requires an artifact object")
                artifact = action["artifact"]
                stop = "final"
                break
            answer = simulator.step(action, condition)
        except (ValueError, TypeError, KeyError) as exc:
            simulator.events.append({"kind": "invalid_response", "message": str(exc)})
            answer = {"error": str(exc)}
        messages.append({"role": "user", "content": json.dumps(answer, sort_keys=True)})
        if simulator.abandoned:
            stop = "simulator_budget_exhausted"
            break
    metrics = {
        "model_calls": len(calls),
        "simulated_user_turns": simulator.user_turns,
        "clarification_round_trips": sum(e["kind"] == "clarification" for e in simulator.events),
        "redundant_decisions_requested": sum(
            len(e.get("redundant_topics", [])) for e in simulator.events
        ),
        "decisions_answered": sum(len(e.get("topics", [])) for e in simulator.events),
        "payload_characters": sum(len(m["content"]) for m in messages),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "human_effort": None,
        "human_abandonment": None,
        "simulated_abandonment": simulator.abandoned,
    }
    for name in ("tokens_input", "tokens_output"):
        metrics[name] = (
            sum(c[name] for c in calls)
            if calls and all(c.get(name) is not None for c in calls)
            else None
        )
    trace = {
        "scenario_id": case["id"],
        "condition": condition,
        "variant": variant,
        "artifact": artifact,
        "state": simulator.state,
        "events": simulator.events,
        "calls": calls,
        "messages": messages,
        "stop_reason": stop,
        "metrics": metrics,
    }
    trace["outcomes"] = judge(case, trace)
    if stop == "provider_error":
        trace["outcomes"]["task_success"] = None
    return trace
