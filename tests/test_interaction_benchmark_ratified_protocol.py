"""Tests for the chair-ratified baseline protocol."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.protocol import assert_ready_for_collection, collection_blockers, load_run_protocol

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.1.json"
PROTOCOL_SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "run-protocol.schema.json"
RECORD_PATH = ROOT / "docs" / "research" / "checkpoint-b1-authorization-v0.1.1.md"
MANIFEST_PATH = ROOT / "docs" / "research" / "checkpoint-b1-v0.1.1-manifest.sha256"


def test_ratified_protocol_validates_and_passes_collection_preflight() -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    schema = json.loads(PROTOCOL_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    protocol = load_run_protocol(PROTOCOL_PATH, project_root=ROOT)
    assert collection_blockers(protocol) == ()
    assert_ready_for_collection(protocol)


def test_ratified_protocol_records_the_chair_ruling() -> None:
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))

    assert payload["status"] == "ratified"
    assert payload["checkpoint"] == {
        "id": "B.1",
        "ruling": "COLLECTION_AUTHORIZED",
        "authorized_by": "Patrick Roebuck",
        "authorized_at": "2026-09-06T13:20:45-04:00",
    }


def test_checkpoint_manifest_covers_exact_files_and_matches_bytes() -> None:
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
