"""Scripted oracle controls for simulator verification; never model performance data."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from benchmarks.outcome_loop import CONDITIONS, load_cases, run_task
from benchmarks.provider import ProviderReply


class ScriptedOracle:
    """A fixture-aware controller used only for positive/negative conformance probes."""

    provider_id = "scripted-oracle-control"
    provider_version = "0.1.0"

    def __init__(self, case: dict[str, Any], condition: str, variant: str = "underspecified"):
        self.case = deepcopy(case)
        self.actions = []
        if variant != "fully_specified":
            topics = list(case["facts"])
            groups = (
                [[topic] for topic in topics]
                if condition == "sequential_clarification"
                else [topics]
            )
            for group in groups:
                if condition == "typed_interaction":
                    self.actions.append(
                        {
                            "action": "ask",
                            "form": {
                                "title": "Required facts",
                                "fields": [
                                    {
                                        "id": topic,
                                        "type": "text_input",
                                        "text": topic,
                                        "required": True,
                                    }
                                    for topic in group
                                ],
                            },
                        }
                    )
                else:
                    self.actions.append(
                        {
                            "action": "ask",
                            "text": "Please specify " + ", ".join(group),
                            "topics": group,
                        }
                    )
        self.actions.extend(
            {"action": "inspect", "target": target} for target in case["required_reads"]
        )
        if case.get("decision"):
            self.actions.append(
                {
                    "action": "decide",
                    "options": case["decision"]["options"],
                    "evidence": case["decision"]["required_evidence"],
                }
            )
        if case.get("allowed_action"):
            self.actions.append({"action": "authorize", "proposal": case["allowed_action"]})
            if case.get("correction"):
                self.actions.append(
                    {"action": "authorize", "proposal": case["correction"]["allowed_action"]}
                )
            self.actions.append(
                {"action": "execute", "proposal": case.get("correction", case)["allowed_action"]}
            )
        self.actions.append({"action": "final", "artifact": case["expected"]})

    def complete(self, messages) -> ProviderReply:
        """Return the next scripted action, resolving only runtime authorization tokens."""
        action = deepcopy(self.actions.pop(0))
        if action["action"] == "execute":
            reply = json.loads(messages[-1]["content"])
            action.update(token=reply["token"], epoch=reply["epoch"])
        return ProviderReply(json.dumps(action), None, None, None, {"synthetic_control": True})


def main() -> None:
    """Exercise every case/condition/control through the real in-memory loop."""
    rows = []
    for case in load_cases():
        variants = (
            ("underspecified", "fully_specified")
            if case.get("fully_specified_control")
            else ("underspecified",)
        )
        for variant in variants:
            for condition in CONDITIONS:
                trace = run_task(
                    case, condition, ScriptedOracle(case, condition, variant), variant=variant
                )
                rows.append(
                    {
                        "scenario_id": case["id"],
                        "variant": variant,
                        "condition": condition,
                        "outcomes": trace["outcomes"],
                        "metrics": trace["metrics"],
                    }
                )
    print(
        json.dumps(
            {"evidence_type": "scripted conformance, not comparative model results", "rows": rows},
            indent=2,
        )
    )
    if not all(row["outcomes"]["task_success"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
