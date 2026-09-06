"""Collect the ratified 42-run baseline pilot through Codex CLI."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from benchmarks.evidence import verify_manifest, write_raw_bundle
from benchmarks.protocol import RunProtocol, assert_ready_for_collection, load_run_protocol
from benchmarks.provider import BaselineActor, CodexCliProvider
from benchmarks.runner import (
    ConditionAdapter,
    FreeFormAdapter,
    HostCapabilities,
    Scenario,
    SequentialClarificationAdapter,
    load_scenarios,
    run_resilient,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.2.json"


@dataclass(frozen=True)
class PlannedRun:
    scenario: Scenario
    adapter: ConditionAdapter
    repeat_id: str

    @property
    def run_id(self) -> str:
        return f"{self.scenario.actor.id}--{self.adapter.condition}--{self.repeat_id}"


def build_plan(protocol: RunProtocol) -> tuple[PlannedRun, ...]:
    scenarios = load_scenarios(protocol.resolve_repo_file("fixture"))
    adapters: tuple[ConditionAdapter, ...] = (
        FreeFormAdapter(),
        SequentialClarificationAdapter(),
    )
    return tuple(
        PlannedRun(scenario, adapter, f"r{repeat}")
        for scenario in scenarios
        for adapter in adapters
        for repeat in range(1, protocol.repeats + 1)
    )


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    )
    return completed.stdout.strip()


def runner_environment(provider: CodexCliProvider) -> dict[str, object]:
    status = _git_output("status", "--porcelain")
    if status:
        raise ValueError("raw collection requires a clean runner worktree")
    return {
        "operating_system": platform.platform(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "runner_commit": _git_output("rev-parse", "HEAD"),
        "working_tree_clean": True,
        "codex_executable": str(provider.executable.resolve()),
        "codex_cli_version": provider.cli_version,
        "codex_model": provider.model,
        "codex_reasoning_effort": provider.reasoning_effort,
        "codex_service_tier": provider.service_tier,
        "provider_working_directory": str(provider.working_directory.resolve()),
        "project_doc_max_bytes": 0,
        "sandbox": "read-only",
        "approval_policy": "never",
        "user_config_loaded": False,
        "execpolicy_rules_loaded": False,
    }


def validate_provider(protocol: RunProtocol, provider: CodexCliProvider) -> None:
    declared_provider = protocol.payload["provider"]
    sampling = protocol.payload["sampling"]
    other = sampling["other_parameters"]
    observed = {
        "provider_id": provider.provider_id,
        "model_id": provider.model,
        "client_version": provider.cli_version,
        "model_reasoning_effort": provider.reasoning_effort,
        "service_tier": provider.service_tier,
    }
    declared = {
        "provider_id": declared_provider["provider_id"],
        "model_id": declared_provider["model_id"],
        "client_version": other["client_version"],
        "model_reasoning_effort": other["model_reasoning_effort"],
        "service_tier": other["service_tier"],
    }
    if observed != declared:
        raise ValueError(f"provider does not match ratified protocol: {observed!r}")


def collect(
    protocol: RunProtocol,
    provider: CodexCliProvider,
    evidence_root: Path,
) -> tuple[dict[str, object], ...]:
    assert_ready_for_collection(protocol)
    validate_provider(protocol, provider)
    plan = build_plan(protocol)
    if len(plan) != 42:
        raise ValueError(f"ratified pilot must contain 42 runs; observed {len(plan)}")
    environment = runner_environment(provider)
    capabilities = HostCapabilities(
        tools=True,
        native_structured_input=False,
        token_telemetry=True,
        latency_telemetry=True,
    )
    receipts: list[dict[str, object]] = []
    for index, planned in enumerate(plan, start=1):
        raw_path = evidence_root / protocol.protocol_id / "runs" / planned.run_id / "raw"
        if raw_path.exists():
            manifest_sha256 = verify_manifest(raw_path)
            if (raw_path / "protocol.json").read_bytes() != protocol.source_path.read_bytes():
                raise ValueError(f"sealed run has a different protocol snapshot: {planned.run_id}")
            receipts.append(
                {
                    "index": index,
                    "run_id": planned.run_id,
                    "status": "already_sealed",
                    "manifest_sha256": manifest_sha256,
                }
            )
            continue

        actor = BaselineActor(provider)
        artifact = run_resilient(
            planned.scenario,
            planned.adapter,
            actor,
            model=provider.model,
            repeat_id=planned.repeat_id,
            host_capabilities=capabilities,
        )
        logical_messages = BaselineActor.messages_for(
            planned.scenario.actor, planned.adapter.condition
        )
        compiled_prompt = provider.compile_prompt(logical_messages)
        effective_prompt = (
            *logical_messages,
            {"role": "transport", "content": compiled_prompt},
        )
        collected_at = datetime.now().astimezone().isoformat(timespec="seconds")
        bundle = write_raw_bundle(
            evidence_root,
            protocol,
            artifact,
            effective_prompt=effective_prompt,
            environment=environment,
            collected_at=collected_at,
        )
        receipt = {
            "index": index,
            "run_id": bundle.run_id,
            "status": "incomplete" if artifact.incomplete else "sealed",
            "manifest_sha256": bundle.manifest_sha256,
        }
        receipts.append(receipt)
        print(json.dumps(receipt, sort_keys=True), flush=True)
    return tuple(receipts)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL_PATH)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--provider-workspace", type=Path, required=True)
    parser.add_argument(
        "--codex-executable",
        type=Path,
        default=Path("/Users/patrickroebuck/.npm-global/bin/codex"),
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _require_external_directory(path: Path, label: str) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(ROOT.resolve())
    except ValueError:
        return
    raise ValueError(f"{label} must be outside the repository: {resolved}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    protocol = load_run_protocol(args.protocol, project_root=ROOT)
    assert_ready_for_collection(protocol)
    provider = CodexCliProvider(
        executable=args.codex_executable,
        working_directory=args.provider_workspace,
    )
    validate_provider(protocol, provider)
    plan = build_plan(protocol)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "protocol_id": protocol.protocol_id,
                    "protocol_sha256": protocol.source_sha256,
                    "run_count": len(plan),
                    "run_ids": [item.run_id for item in plan],
                    "command": list(provider.command()),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    _require_external_directory(args.evidence_root, "evidence root")
    _require_external_directory(args.provider_workspace, "provider workspace")
    args.evidence_root.mkdir(parents=True, exist_ok=True)
    args.provider_workspace.mkdir(parents=True, exist_ok=True)
    os.chmod(args.provider_workspace, 0o700)
    receipts = collect(protocol, provider, args.evidence_root)
    incomplete = sum(item["status"] == "incomplete" for item in receipts)
    print(
        json.dumps(
            {
                "protocol_id": protocol.protocol_id,
                "retained_run_count": len(receipts),
                "incomplete_run_count": incomplete,
            },
            sort_keys=True,
        )
    )
    return 0 if incomplete == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
