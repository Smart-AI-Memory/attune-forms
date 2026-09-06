"""Tests for the authorized protocol succeeding the retained v0.1.1 failure."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.protocol import assert_ready_for_collection, load_run_protocol

ROOT = Path(__file__).resolve().parents[1]
FAILED_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.1.json"
CORRECTED_PATH = ROOT / "benchmarks" / "protocols" / "baseline-pilot-v0.1.2.json"
SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "run-protocol.schema.json"


def test_corrected_protocol_validates_and_is_authorized() -> None:
    payload = json.loads(CORRECTED_PATH.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    protocol = load_run_protocol(CORRECTED_PATH, project_root=ROOT)
    assert_ready_for_collection(protocol)
    assert payload["checkpoint"] == {
        "id": "B.1",
        "ruling": "COLLECTION_AUTHORIZED",
        "authorized_by": "Patrick Roebuck",
        "authorized_at": "2026-09-06T13:48:49-04:00",
    }


def test_corrected_protocol_changes_only_identity_and_authorization_time() -> None:
    failed = json.loads(FAILED_PATH.read_text(encoding="utf-8"))
    corrected = json.loads(CORRECTED_PATH.read_text(encoding="utf-8"))

    normalized_failed = deepcopy(failed)
    normalized_corrected = deepcopy(corrected)
    for payload in (normalized_failed, normalized_corrected):
        payload.pop("protocol_version")
        payload.pop("protocol_id")
        payload["checkpoint"].pop("authorized_at")

    assert normalized_corrected == normalized_failed
