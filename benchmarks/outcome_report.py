"""Descriptive task outcomes and costs with missingness and matched-pair counts."""

from __future__ import annotations

from typing import Any

from benchmarks.aggregation import summarize
from benchmarks.outcome_loop import CONDITIONS, build_plan

METRICS = (
    "model_calls",
    "simulated_user_turns",
    "clarification_round_trips",
    "elapsed_ms",
    "decisions_answered",
    "redundant_decisions_requested",
    "payload_characters",
    "tokens_input",
    "tokens_output",
    "human_effort",
    "human_abandonment",
)


def summarize_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe one frozen protocol; never pool scenarios or imply human effects."""
    plan = build_plan()
    expected = {(u["scenario_id"], u["variant"], u["condition"], u["repeat"]) for u in plan}
    observed = {}
    protocols = {t["protocol_id"] for t in traces}
    if len(protocols) > 1:
        raise ValueError("cannot pool protocols")
    for trace in traces:
        key = (trace["scenario_id"], trace["variant"], trace["condition"], trace["repeat"])
        if key not in expected or key in observed:
            raise ValueError("unplanned or duplicate experimental unit")
        observed[key] = {**trace["metrics"], **trace["outcomes"]}
    groups = []
    pairs = []
    metrics = (*METRICS, "task_success", "unauthorized_action_attempts")
    for scenario, variant in dict.fromkeys((u["scenario_id"], u["variant"]) for u in plan):
        for condition in CONDITIONS:
            rows = [
                observed[(scenario, variant, condition, repeat)]
                for repeat in (1, 2, 3)
                if (scenario, variant, condition, repeat) in observed
            ]
            groups.append(
                {
                    "scenario_id": scenario,
                    "variant": variant,
                    "condition": condition,
                    "metrics": {
                        m: summarize([r.get(m) for r in rows], planned=3, attempted=len(rows))
                        for m in metrics
                    },
                }
            )
        for baseline in CONDITIONS[:2]:
            for metric in metrics:
                values = []
                for repeat in (1, 2, 3):
                    a = observed.get((scenario, variant, baseline, repeat))
                    b = observed.get((scenario, variant, "typed_interaction", repeat))
                    if a is None or b is None:
                        continue
                    left, right = a.get(metric), b.get(metric)
                    values.append(None if left is None or right is None else right - left)
                pairs.append(
                    {
                        "scenario_id": scenario,
                        "variant": variant,
                        "baseline": baseline,
                        "direction": "typed_minus_baseline",
                        "metric": metric,
                        **summarize(values, planned=3, attempted=len(values)),
                    }
                )
    return {
        "protocol_id": next(iter(protocols), None),
        "planned": 72,
        "retained": len(traces),
        "descriptive_only": True,
        "groups": groups,
        "pairs": pairs,
        "limits": [
            "deterministic user policy, not human effort or behavior",
            "scripted controls are not model performance results",
            "no population-level significance or superiority claim",
        ],
    }


def main() -> None:
    """Verify retained bundles and print the approved descriptive report."""
    import argparse
    import json
    from pathlib import Path

    from benchmarks.collect_outcomes import verify_protocol
    from benchmarks.evidence import verify_manifest

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = verify_protocol(args.protocol, collection=False)
    rows = []
    for unit in build_plan():
        run_id = f'{unit["scenario_id"]}--{unit["variant"]}--{unit["condition"]}--r{unit["repeat"]}'
        root = args.evidence_root / protocol["protocol_id"] / "runs" / run_id
        if not root.exists():
            continue
        verify_manifest(root / "raw")
        if (root / "raw/protocol.json").read_bytes() != args.protocol.read_bytes():
            raise ValueError("retained protocol differs")
        if json.loads((root / "raw/unit.json").read_text(encoding="utf-8")) != unit:
            raise ValueError("retained unit differs")
        trace = json.loads((root / "raw/trace.json").read_text(encoding="utf-8"))
        rows.append({**trace, "protocol_id": protocol["protocol_id"], "repeat": unit["repeat"]})
    report = summarize_traces(rows)
    report["protocol_id"] = protocol["protocol_id"]
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
