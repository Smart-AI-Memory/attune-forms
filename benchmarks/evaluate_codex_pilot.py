"""Verify and score a complete AF-3 cohort without inventing semantic evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from benchmarks.aggregation import aggregate
from benchmarks.collect_codex_pilot import build_plan
from benchmarks.evidence import RawEvidenceBundle, verify_manifest, write_evaluation_bundle
from benchmarks.protocol import assert_ready_for_collection, load_run_protocol

ROOT = Path(__file__).resolve().parents[1]


def evaluate_cohort(protocol, evidence_root: Path) -> dict:
    """Require exactly the planned raw units and append observed-only evaluations."""
    assert_ready_for_collection(protocol)
    plan = build_plan(protocol)
    runs = evidence_root.resolve() / protocol.protocol_id / "runs"
    expected = {item.run_id for item in plan}
    observed = {p.name for p in runs.iterdir() if p.is_dir()}
    if observed != expected:
        raise ValueError(
            f"cohort differs from plan: missing={expected-observed}, extra={observed-expected}"
        )
    # Validate the full raw cohort before writing any evaluations.
    raw_bundles = []
    for item in plan:
        raw = runs / item.run_id / "raw"
        digest = verify_manifest(raw)
        if (raw / "protocol.json").read_bytes() != protocol.source_path.read_bytes():
            raise ValueError(f"protocol snapshot mismatch: {item.run_id}")
        record = json.loads((raw / "run.json").read_text(encoding="utf-8"))
        if record["run_id"] != item.run_id or record["protocol_sha256"] != protocol.source_sha256:
            raise ValueError(f"raw identity mismatch: {item.run_id}")
        raw_bundles.append(RawEvidenceBundle(raw, protocol.protocol_id, item.run_id, digest))
    implementation = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    rows = []
    index = []
    for item, raw in zip(plan, raw_bundles, strict=True):
        evaluation_path = (
            raw.path.parent / "evaluations" / protocol.scoring_policy_version / "observed-only-v1"
        )
        if evaluation_path.exists():
            evaluation_digest = verify_manifest(evaluation_path)
            metadata = json.loads((evaluation_path / "evaluation.json").read_text(encoding="utf-8"))
            if (
                metadata["raw_bundle"]["manifest_sha256"] != raw.manifest_sha256
                or metadata["evaluator"]["implementation_sha256"] != implementation
            ):
                raise ValueError("existing evaluation identity differs; do not overwrite")
            row = json.loads((evaluation_path / "results.jsonl").read_text(encoding="utf-8"))
        else:
            bundle = write_evaluation_bundle(
                raw,
                protocol,
                item.scenario,
                evaluation_events=(),
                evaluation_id="observed-only-v1",
                evaluator_id="frozen-policy-observed-only",
                evaluator_version="0.1.0",
                evaluator_sha256=implementation,
                evaluated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            row = json.loads(bundle.result.as_json())
            evaluation_digest = bundle.manifest_sha256
        rows.append(row)
        index.append(
            {
                "run_id": item.run_id,
                "raw_manifest_sha256": raw.manifest_sha256,
                "evaluation_manifest_sha256": evaluation_digest,
            }
        )
    scenario_ids = list(dict.fromkeys(item.scenario.actor.id for item in plan))
    return {
        "protocol_id": protocol.protocol_id,
        "protocol_sha256": protocol.source_sha256,
        "planned": len(plan),
        "retained": len(rows),
        "incomplete": sum(row["incomplete"] for row in rows),
        "rows": rows,
        "manifest_index": index,
        "aggregation": aggregate(rows, scenario_ids=scenario_ids, repeats=protocol.repeats),
    }


def main() -> None:
    """Evaluate one explicit protocol and print its descriptive report as JSON."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    protocol = load_run_protocol(args.protocol, project_root=ROOT)
    print(json.dumps(evaluate_cohort(protocol, args.evidence_root), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
