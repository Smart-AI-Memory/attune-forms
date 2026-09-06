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
