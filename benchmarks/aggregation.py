"""Descriptive aggregation for the chair-approved AF-3 pilot policy."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any

CONDITIONS = ("free_form", "sequential_clarification")
METRICS = ("tokens_input", "tokens_output", "elapsed_ms", "task_success")


def summarize(values: Sequence[Any], *, planned: int, attempted: int) -> dict[str, Any]:
    """Keep missing denominators explicit and summarize only observed values."""
    observed = [value for value in values if value is not None]
    if not 0 <= len(observed) <= attempted <= planned or len(values) != attempted:
        raise ValueError("invalid planned/attempted/observed denominators")
    result: dict[str, Any] = {
        "planned": planned,
        "attempted": attempted,
        "observed": len(observed),
        "missing": planned - len(observed),
        "unattempted": planned - attempted,
    }
    if not observed:
        return {**result, "median": None, "min": None, "max": None}
    if all(isinstance(value, bool) for value in observed):
        return {**result, "true_count": sum(observed)}
    if any(
        isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value)
        for value in observed
    ):
        raise ValueError("metric values must be consistently Boolean or finite numeric")
    return {**result, "median": median(observed), "min": min(observed), "max": max(observed)}


def aggregate(
    rows: Sequence[Mapping[str, Any]],
    *,
    scenario_ids: Sequence[str],
    repeats: int = 3,
) -> dict[str, Any]:
    """Group one protocol's results by scenario and condition, with exact pairs."""
    if repeats < 1 or len(set(scenario_ids)) != len(scenario_ids):
        raise ValueError("invalid scenario/repeat plan")
    keys = {}
    for row in rows:
        key = (row["scenario_id"], row["condition"], row["repeat_id"])
        if key in keys:
            raise ValueError(f"duplicate experimental unit: {key}")
        if (
            key[0] not in scenario_ids
            or key[1] not in CONDITIONS
            or key[2] not in {f"r{index}" for index in range(1, repeats + 1)}
        ):
            raise ValueError(f"unplanned experimental unit: {key}")
        keys[key] = row
    identities = {
        (row["model"], row["scoring_policy_version"], row["benchmark_version"]) for row in rows
    }
    if len(identities) > 1:
        raise ValueError("mixed model or scoring identities")
    grouped = []
    paired = []
    for scenario in scenario_ids:
        scenario_rows = [row for row in rows if row["scenario_id"] == scenario]
        primary = sorted({name for row in scenario_rows for name in row["primary_outcomes"]})
        metrics = [*METRICS, *primary]
        for condition in CONDITIONS:
            selected = [row for row in scenario_rows if row["condition"] == condition]
            values = {
                metric: summarize(
                    [
                        (
                            row["primary_outcomes"].get(metric)
                            if metric in primary
                            else row.get(metric)
                        )
                        for row in selected
                    ],
                    planned=repeats,
                    attempted=len(selected),
                )
                for metric in metrics
            }
            grouped.append({"scenario_id": scenario, "condition": condition, "metrics": values})
        for metric in metrics:
            differences = []
            paired_attempts = 0
            for index in range(1, repeats + 1):
                pair = [keys.get((scenario, condition, f"r{index}")) for condition in CONDITIONS]
                if any(row is None for row in pair):
                    continue
                paired_attempts += 1
                a, b = [
                    row["primary_outcomes"].get(metric) if metric in primary else row.get(metric)
                    for row in pair
                ]
                differences.append(None if a is None or b is None else b - a)
            paired.append(
                {
                    "scenario_id": scenario,
                    "metric": metric,
                    "direction": "sequential_minus_free_form",
                    **summarize(differences, planned=repeats, attempted=paired_attempts),
                }
            )
    return {
        "aggregation_policy_version": "0.1.0",
        "descriptive_only": True,
        "limitations": [
            "clarification_round_trips is the frozen count of typed request events; this text-only pilot does not measure conversational question counts or human round trips"
        ],
        "groups": grouped,
        "paired": paired,
    }
