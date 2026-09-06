"""Tests for the machine-specific Codex baseline protocol proposal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.protocol import collection_blockers, load_run_protocol

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.1.draft.json"
PROTOCOL_SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "run-protocol.schema.json"
RECORD_PATH = ROOT / "docs" / "research" / "af-2-codex-runtime-record.md"
MANIFEST_PATH = ROOT / "docs" / "research" / "af-2-codex-runtime-manifest.sha256"


def test_codex_protocol_validates_against_closed_schema() -> None:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    schema = json.loads(PROTOCOL_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(protocol)


def test_codex_protocol_resolves_provider_and_sampling_fields() -> None:
    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)

    assert collection_blockers(protocol) == (
        "protocol status is not ratified",
        "Checkpoint B.1 does not authorize collection",
        "Checkpoint B.1 has no authorizing chair",
        "Checkpoint B.1 has no authorization timestamp",
    )


def test_codex_protocol_preserves_the_42_run_design() -> None:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert (
        protocol["fixture"]["scenario_count"]
        * len(protocol["conditions"])
        * protocol["repeats_per_scenario_condition"]
        == 42
    )


def test_codex_runtime_manifest_covers_exact_files_and_matches_bytes() -> None:
    entries = {}
    for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
        digest, relative_path = line.split("  ", 1)
        entries[relative_path] = digest

    assert set(entries) == {
        PROTOCOL_PATH.relative_to(ROOT).as_posix(),
        RECORD_PATH.relative_to(ROOT).as_posix(),
        Path(__file__).resolve().relative_to(ROOT).as_posix(),
    }
    for relative_path, expected_digest in entries.items():
        assert hashlib.sha256((ROOT / relative_path).read_bytes()).hexdigest() == expected_digest
