"""Real append-only files, interruption guards, and analysis denominators."""

import hashlib
import json
from types import SimpleNamespace

import pytest

from benchmarks import collect_outcomes as collector
from benchmarks.evidence import verify_manifest
from benchmarks.outcome_loop import build_plan, load_cases, run_task
from benchmarks.outcome_probe import ScriptedOracle
from benchmarks.outcome_report import summarize_traces


def protocol_file(tmp_path, status="ratified"):
    names = [
        "benchmarks/fixtures/scenarios-v0.json",
        "benchmarks/fixtures/outcome-scenarios-v0.1.json",
        "benchmarks/outcome_loop.py",
        "benchmarks/outcome_judge.py",
        "benchmarks/collect_outcomes.py",
        "benchmarks/provider.py",
    ]
    p = tmp_path / "protocol.json"
    p.write_text(
        json.dumps(
            {
                "protocol_id": "test-outcomes",
                "status": status,
                "authorization": "test-only",
                "planned_units": 72,
                "repeats": 3,
                "max_model_turns": 16,
                "max_user_turns": 12,
                "source_sha256": {
                    name: hashlib.sha256((collector.ROOT / name).read_bytes()).hexdigest()
                    for name in names
                },
                "runtime": {
                    "cli_version": "test",
                    "model": "scripted",
                    "reasoning_effort": "medium",
                    "service_tier": "test",
                },
            }
        )
    )
    return p


def install_scripted_provider(monkeypatch):
    calls = []

    class ScriptedRuntime:
        def __init__(self, **kwargs):
            pass

        def _check_local_contract(self):
            pass

        def command(self):
            return ("scripted-oracle-control",)

        def complete(self, messages):
            calls.append(messages)
            if len(messages) == 2:
                context = json.loads(messages[1]["content"])
                case = next(c for c in load_cases() if c["task"] == context["task"])
                text = messages[0]["content"]
                condition = (
                    "typed_interaction"
                    if '"form"' in text
                    else "sequential_clarification" if "exactly one topic" in text else "free_form"
                )
                variant = "fully_specified" if context["facts"] else "underspecified"
                self.actor = ScriptedOracle(case, condition, variant)
            return self.actor.complete(messages)

    monkeypatch.setattr(collector, "CodexCliProvider", ScriptedRuntime)
    monkeypatch.setattr(
        collector.subprocess,
        "run",
        lambda args, **kwargs: SimpleNamespace(stdout="" if "status" in args else "a" * 40),
    )
    return calls


def test_all_units_seal_turns_resume_without_calls_and_detect_tampering(
    monkeypatch, tmp_path, capsys
):
    protocol = protocol_file(tmp_path)
    calls = install_scripted_provider(monkeypatch)
    root = tmp_path / "evidence"
    receipts = collector.collect(protocol, root, tmp_path / "workspace", tmp_path / "codex")
    assert len(receipts) == 72 and all(r["outcomes"]["task_success"] for r in receipts)
    count = len(calls)
    again = collector.collect(protocol, root, tmp_path / "workspace", tmp_path / "codex")
    assert again == receipts and len(calls) == count
    from benchmarks.outcome_report import main as report_main

    capsys.readouterr()
    monkeypatch.setattr(
        "sys.argv", ["report", "--protocol", str(protocol), "--evidence-root", str(root)]
    )
    report_main()
    report = json.loads(capsys.readouterr().out)
    assert report["retained"] == 72
    assert all(g["metrics"]["task_success"]["true_count"] == 3 for g in report["groups"])
    raw = next(root.glob("*/runs/*/raw"))
    verify_manifest(raw)
    turn = raw.parent / "turns/turn-01/call.json"
    turn.write_text("{}")
    with pytest.raises(ValueError):
        collector.collect(protocol, root, tmp_path / "workspace", tmp_path / "codex")
    assert len(calls) == count


def test_partial_unit_is_not_restarted(monkeypatch, tmp_path):
    protocol = protocol_file(tmp_path)
    calls = install_scripted_provider(monkeypatch)
    first = build_plan()[0]
    runid = f'{first["scenario_id"]}--{first["variant"]}--{first["condition"]}--r{first["repeat"]}'
    (tmp_path / "evidence/test-outcomes/runs" / runid / "turns").mkdir(parents=True)
    with pytest.raises(ValueError, match="manifest"):
        collector.collect(
            protocol, tmp_path / "evidence", tmp_path / "workspace", tmp_path / "codex"
        )
    assert not calls


def test_unratified_or_changed_protocol_makes_no_provider_call(monkeypatch, tmp_path):
    p = protocol_file(tmp_path, "chair_required")
    calls = install_scripted_provider(monkeypatch)
    with pytest.raises(ValueError, match="authorization"):
        collector.collect(p, tmp_path / "evidence", tmp_path / "workspace", tmp_path / "codex")
    data = json.loads(p.read_text())
    data["source_sha256"]["benchmarks/outcome_loop.py"] = "0" * 64
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="frozen source differs"):
        collector.verify_protocol(p, collection=False)
    assert not calls


def test_protocol_path_escape_and_missing_bindings_are_rejected(tmp_path):
    p = protocol_file(tmp_path)
    data = json.loads(p.read_text())
    data["source_sha256"]["/etc/passwd"] = "0" * 64
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="inside"):
        collector.verify_protocol(p, collection=False)
    del data["source_sha256"]["/etc/passwd"]
    del data["source_sha256"]["benchmarks/outcome_loop.py"]
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="required source"):
        collector.verify_protocol(p, collection=False)


def test_missing_units_and_human_metrics_stay_missing_in_report():
    case = load_cases()[5]
    rows = []
    for condition in ("free_form", "typed_interaction"):
        trace = run_task(case, condition, ScriptedOracle(case, condition))
        trace.update(protocol_id="test", repeat=1)
        rows.append(trace)
    result = summarize_traces(rows)
    group = next(
        g
        for g in result["groups"]
        if g["scenario_id"] == case["id"]
        and g["condition"] == "typed_interaction"
        and g["variant"] == "underspecified"
    )
    assert group["metrics"]["task_success"]["observed"] == 1
    assert group["metrics"]["task_success"]["missing"] == 2
    assert group["metrics"]["human_effort"]["observed"] == 0
    pair = next(
        p
        for p in result["pairs"]
        if p["scenario_id"] == case["id"]
        and p["variant"] == "underspecified"
        and p["baseline"] == "free_form"
        and p["metric"] == "model_calls"
    )
    assert pair["observed"] == 1 and pair["missing"] == 2
    with pytest.raises(ValueError, match="duplicate"):
        summarize_traces(rows + rows)
    rows[1]["protocol_id"] = "different"
    with pytest.raises(ValueError, match="pool"):
        summarize_traces(rows)


def test_cli_dry_run_and_collection_failure_are_explicit(monkeypatch, tmp_path, capsys):
    protocol = protocol_file(tmp_path)
    calls = install_scripted_provider(monkeypatch)
    monkeypatch.setattr("sys.argv", ["collect", "--protocol", str(protocol), "--dry-run"])
    collector.main()
    plan = json.loads(capsys.readouterr().out)
    assert len(plan["units"]) == 72 and plan["maximum_model_calls"] == 1152
    assert not calls

    def fail(self, messages):
        calls.append(messages)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(collector.CodexCliProvider, "complete", fail)
    monkeypatch.setattr(
        "sys.argv",
        [
            "collect",
            "--protocol",
            str(protocol),
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--provider-workspace",
            str(tmp_path / "workspace"),
            "--codex-executable",
            str(tmp_path / "codex"),
        ],
    )
    with pytest.raises(SystemExit) as exc:
        collector.main()
    assert exc.value.code == 2 and len(calls) == 1
    # A failed sealed unit is still failed on resume; no repeat invocation.
    with pytest.raises(SystemExit):
        collector.main()
    assert len(calls) == 1


def test_collection_refuses_dirty_checkout_and_internal_evidence(monkeypatch, tmp_path):
    protocol = protocol_file(tmp_path)
    install_scripted_provider(monkeypatch)
    monkeypatch.setattr(
        collector.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout=" M file")
    )
    with pytest.raises(ValueError, match="clean"):
        collector.collect(
            protocol, tmp_path / "evidence", tmp_path / "workspace", tmp_path / "codex"
        )
    install_scripted_provider(monkeypatch)
    with pytest.raises(ValueError, match="outside"):
        collector.collect(
            protocol, collector.ROOT / "evidence", tmp_path / "workspace", tmp_path / "codex"
        )
