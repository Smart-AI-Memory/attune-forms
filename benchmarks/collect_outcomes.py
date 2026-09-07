"""Collect a separately ratified outcome experiment with per-turn sealing."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from benchmarks.evidence import (
    _commit_bundle,
    _json_bytes,
    _require_safe_id,
    _validate_provider_metadata,
    verify_manifest,
)
from benchmarks.outcome_loop import ROOT, build_plan, load_cases, run_task
from benchmarks.provider import CodexCliProvider


def verify_protocol(path: Path, *, collection: bool) -> dict:
    """Bind the exact fixtures, loop, oracle and collection limits before a call."""
    protocol = json.loads(path.read_text(encoding="utf-8"))
    _require_safe_id(protocol["protocol_id"], "protocol id")
    if protocol["planned_units"] != 72 or protocol["repeats"] != 3:
        raise ValueError("outcome pilot requires the fixed 72-unit balanced plan")
    if protocol["max_model_turns"] != 16 or protocol["max_user_turns"] != 12:
        raise ValueError("unexpected interaction budget")
    for relative, expected in protocol["source_sha256"].items():
        target = (ROOT / relative).resolve()
        if not target.is_relative_to(ROOT.resolve()) or not target.is_file():
            raise ValueError("protocol source must be a file inside the repository")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError(f"frozen source differs: {relative}")
    required = {
        "benchmarks/fixtures/scenarios-v0.json",
        "benchmarks/fixtures/outcome-scenarios-v0.2.json",
        "benchmarks/outcome_loop.py",
        "benchmarks/outcome_judge.py",
        "benchmarks/collect_outcomes.py",
        "benchmarks/provider.py",
    }
    if not required <= protocol["source_sha256"].keys():
        raise ValueError("protocol is missing a required source binding")
    if collection and (protocol["status"] != "ratified" or not protocol["authorization"]):
        raise ValueError("outcome collection requires a recorded protocol authorization")
    return protocol


def collect(
    protocol_path: Path, evidence_root: Path, workspace: Path, executable: Path
) -> list[dict]:
    """Seal every call and run; refuse to repeat a partial or completed unit."""
    protocol = verify_protocol(protocol_path, collection=True)
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    if status:
        raise ValueError("collection requires a clean committed checkout")
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True, text=True
    ).stdout.strip()
    for path in (evidence_root, workspace):
        if path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError("evidence and neutral workspace must be outside the repository")
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = protocol["runtime"]
    provider = CodexCliProvider(
        executable=executable,
        working_directory=workspace,
        cli_version=runtime["cli_version"],
        model=runtime["model"],
        reasoning_effort=runtime["reasoning_effort"],
        service_tier=runtime["service_tier"],
    )
    provider._check_local_contract()  # Version and parser only; no probe model call.
    cases = {case["id"]: case for case in load_cases()}
    receipts = []
    for unit in build_plan():
        run_id = f'{unit["scenario_id"]}--{unit["variant"]}--{unit["condition"]}--r{unit["repeat"]}'
        _require_safe_id(run_id, "run id")
        path = evidence_root / protocol["protocol_id"] / "runs" / run_id
        if path.exists():
            verify_manifest(path / "raw")  # Partial units are never silently restarted.
            if (path / "raw/protocol.json").read_bytes() != protocol_path.read_bytes():
                raise ValueError("retained protocol differs")
            if json.loads((path / "raw/unit.json").read_text(encoding="utf-8")) != unit:
                raise ValueError("retained experimental unit differs")
            trace = json.loads((path / "raw/trace.json").read_text(encoding="utf-8"))
            turn_hashes = json.loads((path / "raw/turn-manifests.json").read_text(encoding="utf-8"))
            if len(turn_hashes) != len(trace["calls"]):
                raise ValueError("retained turn count differs")
            for index, call in enumerate(trace["calls"], 1):
                turn_path = path / "turns" / f"turn-{index:02}"
                if verify_manifest(turn_path) != turn_hashes[index - 1]:
                    raise ValueError("retained turn manifest differs")
                if json.loads((turn_path / "call.json").read_text(encoding="utf-8")) != call:
                    raise ValueError("retained call differs from raw trace")
        else:
            path.mkdir(parents=True, exist_ok=False)
            turn_hashes = []

            def retain_turn(index, call, target=path, hashes=turn_hashes):
                _validate_provider_metadata(call.get("metadata", {}))
                hashes.append(
                    _commit_bundle(
                        target / "turns" / f"turn-{index:02}", {"call.json": _json_bytes(call)}
                    )
                )

            trace = run_task(
                cases[unit["scenario_id"]],
                unit["condition"],
                provider,
                variant=unit["variant"],
                max_turns=protocol["max_model_turns"],
                max_user_turns=protocol["max_user_turns"],
                on_turn=retain_turn,
            )
            _commit_bundle(
                path / "raw",
                {
                    "trace.json": _json_bytes(trace),
                    "turn-manifests.json": _json_bytes(turn_hashes),
                    "protocol.json": protocol_path.read_bytes(),
                    "unit.json": _json_bytes(unit),
                    "environment.json": _json_bytes(
                        {
                            "runner_commit": revision,
                            "clean": True,
                            "runtime": runtime,
                            "command": provider.command(),
                        }
                    ),
                },
            )
        receipt = {
            "run_id": run_id,
            "stop_reason": trace["stop_reason"],
            "outcomes": trace["outcomes"],
            "manifest_sha256": verify_manifest(path / "raw"),
        }
        receipts.append(receipt)
        print(json.dumps(receipt), flush=True)
        if trace["stop_reason"] == "provider_error":
            break
    return receipts


def main() -> None:
    """Dry-run a proposed protocol or collect only after explicit ratification."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--provider-workspace", type=Path)
    parser.add_argument("--codex-executable", type=Path)
    args = parser.parse_args()
    if args.dry_run:
        protocol = verify_protocol(args.protocol, collection=False)
        print(
            json.dumps(
                {
                    "protocol_id": protocol["protocol_id"],
                    "units": build_plan(),
                    "maximum_model_calls": 72 * 16,
                },
                indent=2,
            )
        )
        return
    if not all((args.evidence_root, args.provider_workspace, args.codex_executable)):
        parser.error("collection needs evidence root, provider workspace and Codex executable")
    receipts = collect(
        args.protocol, args.evidence_root, args.provider_workspace, args.codex_executable
    )
    if len(receipts) != 72 or any(row["stop_reason"] == "provider_error" for row in receipts):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
