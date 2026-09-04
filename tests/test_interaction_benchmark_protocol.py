"""Tests for predeclared baseline protocol identity and collection gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from benchmarks.protocol import (
    DEFAULT_PROTOCOL_PATH,
    ProtocolError,
    assert_ready_for_collection,
    collection_blockers,
    load_run_protocol,
)
from benchmarks.scoring import DEFAULT_POLICY_PATH

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "benchmarks" / "fixtures" / "scenarios-v0.json"
PROTOCOL_SCHEMA_PATH = ROOT / "benchmarks" / "schema" / "run-protocol.schema.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_ratified_protocol(tmp_path: Path):
    project = tmp_path / "project"
    fixture = project / "benchmarks" / "fixtures" / "scenarios-v0.json"
    policy = project / "benchmarks" / "policies" / "scoring-v0.1.json"
    protocol_path = project / "benchmarks" / "protocols" / "baseline-pilot-v0.1.json"
    fixture.parent.mkdir(parents=True)
    policy.parent.mkdir(parents=True)
    protocol_path.parent.mkdir(parents=True)
    fixture.write_bytes(FIXTURE_PATH.read_bytes())
    policy.write_bytes(DEFAULT_POLICY_PATH.read_bytes())

    raw = json.loads(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
    raw["status"] = "ratified"
    raw["fixture"]["sha256"] = _digest(fixture)
    raw["scoring_policy"]["sha256"] = _digest(policy)
    raw["provider"] = {
        "provider_id": "test-provider",
        "provider_api_version": "2026-09-01",
        "model_id": "test-model",
        "model_version": "test-model-2026-09-01",
    }
    raw["sampling"] = {
        "mode": "deterministic",
        "temperature": 0,
        "top_p": 1,
        "seed": 17,
        "max_output_tokens": 2048,
        "other_parameters": {"reasoning_effort": "medium"},
        "unsupported_or_unavailable": {},
    }
    raw["checkpoint"] = {
        "id": "B.1",
        "ruling": "COLLECTION_AUTHORIZED",
        "authorized_by": "test-chair",
        "authorized_at": "2026-09-04T18:00:00Z",
    }
    protocol_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return load_run_protocol(protocol_path, project_root=project), project


def test_draft_protocol_validates_against_closed_schema() -> None:
    protocol = json.loads(DEFAULT_PROTOCOL_PATH.read_text(encoding="utf-8"))
    schema = json.loads(PROTOCOL_SCHEMA_PATH.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(protocol)


def test_repository_protocol_is_deliberately_blocked_pending_chair_fields() -> None:
    protocol = load_run_protocol()
    blockers = collection_blockers(protocol)

    assert "protocol status is not ratified" in blockers
    assert "Checkpoint B.1 does not authorize collection" in blockers
    assert "provider.provider_id is unresolved" in blockers
    assert "sampling.mode is unresolved" in blockers
    with pytest.raises(ProtocolError, match="collection blocked"):
        assert_ready_for_collection(protocol)


def test_fully_declared_ratified_protocol_passes_preflight(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)

    assert collection_blockers(protocol) == ()
    assert_ready_for_collection(protocol)


def test_protocol_payload_is_immutable_after_loading(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)

    with pytest.raises(TypeError):
        protocol.payload["status"] = "retired"
    with pytest.raises(TypeError):
        protocol.payload["provider"]["model_id"] = "different-model"


def test_changed_fixture_breaks_preflight_even_at_same_path(tmp_path: Path) -> None:
    protocol, project = make_ratified_protocol(tmp_path)
    fixture = project / "benchmarks" / "fixtures" / "scenarios-v0.json"
    fixture.write_bytes(fixture.read_bytes() + b"\n")

    assert "fixture SHA-256 does not match the protocol" in collection_blockers(protocol)


def test_changed_policy_breaks_preflight_even_at_same_version(tmp_path: Path) -> None:
    protocol, project = make_ratified_protocol(tmp_path)
    policy = project / "benchmarks" / "policies" / "scoring-v0.1.json"
    policy.write_bytes(policy.read_bytes() + b"\n")

    assert "scoring policy SHA-256 does not match the protocol" in collection_blockers(protocol)


def test_protocol_file_change_after_load_breaks_preflight(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    protocol.source_path.write_bytes(protocol.source_path.read_bytes() + b"\n")

    assert "protocol file changed after it was loaded" in collection_blockers(protocol)


def test_unavailable_sampling_control_requires_an_explicit_reason(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    raw = protocol.as_dict()
    raw["sampling"]["seed"] = None
    raw["sampling"]["unsupported_or_unavailable"] = {}
    protocol.source_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    reloaded = load_run_protocol(protocol.source_path, project_root=protocol.project_root)

    assert "sampling.seed is neither set nor declared unavailable" in collection_blockers(reloaded)


def test_unavailable_sampling_control_can_be_predeclared(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    raw = protocol.as_dict()
    raw["sampling"]["seed"] = None
    raw["sampling"]["unsupported_or_unavailable"] = {
        "seed": "The provider API exposes no seed control."
    }
    protocol.source_path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    reloaded = load_run_protocol(protocol.source_path, project_root=protocol.project_root)

    assert collection_blockers(reloaded) == ()
