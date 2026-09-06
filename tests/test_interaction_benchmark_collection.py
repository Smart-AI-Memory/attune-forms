"""Tests for the AF-3 Codex pilot collection entry point."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.collect_codex_pilot import (
    _require_external_directory,
    build_plan,
    main,
    validate_provider,
)
from benchmarks.protocol import load_run_protocol
from benchmarks.provider import CodexCliProvider

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.2.json"


def test_ratified_plan_has_exact_protocol_order() -> None:
    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)

    plan = build_plan(protocol)

    assert len(plan) == 42
    assert plan[0].run_id == "ambiguous-security-audit-001--free_form--r1"
    assert plan[2].run_id == "ambiguous-security-audit-001--free_form--r3"
    assert plan[3].run_id == "ambiguous-security-audit-001--sequential_clarification--r1"
    assert plan[-1].run_id == "triage-review-findings-001--sequential_clarification--r3"
    assert len({item.run_id for item in plan}) == 42


def test_provider_must_match_every_ratified_runtime_field(tmp_path: Path) -> None:
    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)
    executable = tmp_path / "codex"
    executable.touch()
    provider = CodexCliProvider(
        executable=executable,
        working_directory=tmp_path,
        reasoning_effort="high",
    )

    with pytest.raises(ValueError, match="does not match ratified protocol"):
        validate_provider(protocol, provider)


def test_dry_run_prints_complete_plan_without_calling_provider(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    provider_workspace = tmp_path / "provider"
    evidence_root = tmp_path / "evidence"

    def fail_complete(*args, **kwargs):
        raise AssertionError("dry-run must not call the provider")

    monkeypatch.setattr(CodexCliProvider, "complete", fail_complete)

    exit_code = main(
        (
            "--protocol",
            str(PROTOCOL_PATH),
            "--evidence-root",
            str(evidence_root),
            "--provider-workspace",
            str(provider_workspace),
            "--codex-executable",
            str(executable),
            "--dry-run",
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["run_count"] == 42
    assert len(payload["run_ids"]) == 42
    assert not evidence_root.exists()
    assert not provider_workspace.exists()


def test_collection_directories_must_be_outside_repository() -> None:
    with pytest.raises(ValueError, match="outside the repository"):
        _require_external_directory(ROOT / "evidence", "evidence root")

    _require_external_directory(ROOT.parent / "external-evidence", "evidence root")


def test_failure_is_sealed_and_resume_does_not_repeat_or_hide_it(monkeypatch, tmp_path):
    from benchmarks.collect_codex_pilot import collect
    from benchmarks.evidence import verify_manifest
    from benchmarks.provider import ProviderExecutionError
    from tests.test_interaction_benchmark_evidence import ENVIRONMENT

    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)
    provider = CodexCliProvider(executable=tmp_path / "codex", working_directory=tmp_path)
    calls = []

    def fail(self, messages):
        calls.append(messages)
        raise ProviderExecutionError("runtime incompatible", {"exit_code": 1})

    monkeypatch.setattr(CodexCliProvider, "complete", fail)
    monkeypatch.setattr("benchmarks.collect_codex_pilot.runner_environment", lambda _: ENVIRONMENT)
    first = collect(protocol, provider, tmp_path / "evidence")
    assert len(first) == 1
    assert first[0]["status"] == "incomplete"
    raw = tmp_path / "evidence" / protocol.protocol_id / "runs" / first[0]["run_id"] / "raw"
    digest = verify_manifest(raw)
    resumed = collect(protocol, provider, tmp_path / "evidence")
    assert resumed == first
    assert len(calls) == 1
    assert verify_manifest(raw) == digest


def test_complete_cohort_resume_verifies_all_42_without_new_calls(monkeypatch, tmp_path):
    from benchmarks.collect_codex_pilot import collect
    from benchmarks.provider import ProviderReply
    from tests.test_interaction_benchmark_evidence import ENVIRONMENT

    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)
    provider = CodexCliProvider(executable=tmp_path / "codex", working_directory=tmp_path)
    calls = []

    def reply(self, messages):
        calls.append(messages)
        return ProviderReply("Please clarify the scope.", 10, 5, 1)

    monkeypatch.setattr(CodexCliProvider, "complete", reply)
    monkeypatch.setattr("benchmarks.collect_codex_pilot.runner_environment", lambda _: ENVIRONMENT)
    first = collect(protocol, provider, tmp_path / "evidence")
    assert len(first) == 42
    assert all(row["status"] == "sealed" for row in first)
    resumed = collect(protocol, provider, tmp_path / "evidence")
    assert len(resumed) == 42
    assert all(row["status"] == "already_sealed" for row in resumed)
    assert len(calls) == 42


def test_provider_version_tracks_protocol_pin(tmp_path):
    provider = CodexCliProvider(
        executable=tmp_path / "codex", working_directory=tmp_path, cli_version="0.153.4"
    )
    assert provider.provider_version == "0.153.4"
