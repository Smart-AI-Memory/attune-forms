"""Missingness, pairing, and evidence-integrity regressions for AF-3."""

from copy import deepcopy

import pytest

from benchmarks.aggregation import aggregate, summarize


def row(condition, repeat, value):
    return {
        "scenario_id": "s1",
        "condition": condition,
        "repeat_id": repeat,
        "model": "test",
        "scoring_policy_version": "0.1.0",
        "benchmark_version": "0.1",
        "tokens_input": value,
        "tokens_output": None,
        "elapsed_ms": None,
        "task_success": None,
        "primary_outcomes": {"safety": None},
    }


def test_missing_values_are_not_zero_or_success():
    result = summarize([None, 0, 10], planned=4, attempted=3)
    assert result == {
        "planned": 4,
        "attempted": 3,
        "observed": 2,
        "missing": 2,
        "unattempted": 1,
        "median": 5,
        "min": 0,
        "max": 10,
    }
    assert summarize([None], planned=3, attempted=1)["median"] is None
    assert summarize([True, False, None], planned=3, attempted=3)["true_count"] == 1


@pytest.mark.parametrize("values", [[True, 1], [float("nan")], [float("inf")], ["1"]])
def test_invalid_metrics_are_rejected(values):
    with pytest.raises(ValueError):
        summarize(values, planned=len(values), attempted=len(values))


def test_bad_denominators_are_rejected():
    with pytest.raises(ValueError):
        summarize([1, 2], planned=1, attempted=2)


def test_pairing_preserves_single_sided_and_missing_observations():
    rows = [
        row("free_form", "r1", 10),
        row("sequential_clarification", "r1", 4),
        row("free_form", "r2", 9),
        row("sequential_clarification", "r2", None),
        row("free_form", "r3", 6),
    ]
    result = aggregate(rows, scenario_ids=["s1"])
    paired = next(x for x in result["paired"] if x["metric"] == "tokens_input")
    assert paired["median"] == -6
    assert paired["observed"] == 1
    assert paired["missing"] == 2
    assert paired["attempted"] == 2
    assert result["groups"][0]["metrics"]["tokens_input"]["observed"] == 3
    assert result["groups"][0]["metrics"]["safety"]["observed"] == 0


def test_duplicate_unplanned_and_mixed_identity_rows_are_rejected():
    original = row("free_form", "r1", 1)
    with pytest.raises(ValueError, match="duplicate"):
        aggregate([original, original], scenario_ids=["s1"])
    with pytest.raises(ValueError, match="unplanned"):
        aggregate([original], scenario_ids=["different"])
    other = deepcopy(original)
    other.update(repeat_id="r2", model="different")
    with pytest.raises(ValueError, match="mixed"):
        aggregate([original, other], scenario_ids=["s1"])


def test_evaluation_round_trip_preserves_raw_and_missing_primary(monkeypatch, tmp_path, capsys):
    from benchmarks.collect_codex_pilot import collect
    from benchmarks.evaluate_codex_pilot import ROOT, evaluate_cohort
    from benchmarks.evidence import verify_manifest
    from benchmarks.protocol import load_run_protocol
    from benchmarks.provider import CodexCliProvider, ProviderReply
    from tests.test_interaction_benchmark_evidence import ENVIRONMENT

    protocol = load_run_protocol(
        ROOT / "benchmarks/protocols/baseline-pilot-v0.1.3.json", project_root=ROOT
    )
    provider = CodexCliProvider(
        executable=tmp_path / "codex", working_directory=tmp_path, cli_version="0.153.4"
    )
    monkeypatch.setattr(
        CodexCliProvider, "complete", lambda *_: ProviderReply("Clarify scope.", 10, 5, 1)
    )
    monkeypatch.setattr("benchmarks.collect_codex_pilot.runner_environment", lambda _: ENVIRONMENT)
    collect(protocol, provider, tmp_path)
    raw = list((tmp_path / protocol.protocol_id).glob("runs/*/raw"))
    before = {str(p): verify_manifest(p) for p in raw}
    result = evaluate_cohort(protocol, tmp_path)
    assert result["retained"] == 42
    assert all(row["task_success"] is None for row in result["rows"])
    assert all(
        all(
            value is None
            for name, value in row["primary_outcomes"].items()
            if name != "clarification_round_trips"
        )
        for row in result["rows"]
    )
    assert before == {str(p): verify_manifest(p) for p in raw}
    assert evaluate_cohort(protocol, tmp_path) == result
    import json

    from benchmarks.evaluate_codex_pilot import main

    capsys.readouterr()
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate", "--protocol", str(protocol.source_path), "--evidence-root", str(tmp_path)],
    )
    main()
    assert json.loads(capsys.readouterr().out) == result
    extra = tmp_path / protocol.protocol_id / "runs" / "unplanned"
    extra.mkdir()
    with pytest.raises(ValueError, match="cohort differs"):
        evaluate_cohort(protocol, tmp_path)
    extra.rmdir()
    (raw[0] / "transcript.json").write_text("{}")
    with pytest.raises(ValueError):
        evaluate_cohort(protocol, tmp_path)
