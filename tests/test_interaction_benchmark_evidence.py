"""Append-only raw-run and later-evaluation evidence tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.evidence import (
    EvidenceError,
    verify_manifest,
    write_evaluation_bundle,
    write_raw_bundle,
)
from benchmarks.runner import (
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    EventTrust,
    FreeFormAdapter,
    HostCapabilities,
    load_scenarios,
    run,
)
from tests.test_interaction_benchmark_protocol import make_ratified_protocol

COLLECTED_AT = "2026-09-04T18:10:00Z"
EVALUATED_AT = "2026-09-04T18:20:00Z"
ENVIRONMENT = {
    "operating_system": "test-os",
    "architecture": "test-architecture",
    "python_version": "3.12.0",
    "runner_commit": "a" * 40,
    "working_tree_clean": True,
}


def _scenario(protocol, family: str = "ambiguous_requirements"):
    return next(
        item
        for item in load_scenarios(protocol.resolve_repo_file("fixture"))
        if item.actor.family == family
    )


def _prompt(scenario):
    return (
        {"role": "system", "content": "Complete the task without inventing authority."},
        {"role": "user", "content": scenario.actor.task},
    )


def _action_result(*, simulated: bool = True) -> BenchmarkEvent:
    payload = {"success": True}
    if simulated:
        payload["simulated"] = True
    return BenchmarkEvent(
        EventKind.ACTION_RESULT,
        payload,
        trust=EventTrust.RUNNER_OBSERVED,
        source="simulator",
    )


def _artifact(protocol, family: str = "ambiguous_requirements", extra_events=()):
    scenario = _scenario(protocol, family)

    def actor(actor_scenario, condition):
        return AdapterOutput(
            events=tuple(extra_events) + (_action_result(),),
            transcript=(
                {"role": "user", "content": actor_scenario.task},
                {"role": "assistant", "content": "Recorded test response."},
            ),
            tokens_input=12,
            tokens_output=5,
            elapsed_ms=25,
        )

    return scenario, run(
        scenario,
        FreeFormAdapter(),
        actor,
        model="test-model",
        repeat_id="r1",
        host_capabilities=HostCapabilities(
            tools=True,
            token_telemetry=True,
            latency_telemetry=True,
        ),
    )


def _raw_bundle(tmp_path: Path, protocol, family: str = "ambiguous_requirements", events=()):
    scenario, artifact = _artifact(protocol, family, events)
    bundle = write_raw_bundle(
        tmp_path / "evidence",
        protocol,
        artifact,
        effective_prompt=_prompt(scenario),
        environment=ENVIRONMENT,
        collected_at=COLLECTED_AT,
    )
    return scenario, artifact, bundle


def test_raw_bundle_has_closed_hashed_layout_and_cannot_be_rewritten(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    _, artifact, bundle = _raw_bundle(tmp_path, protocol)

    assert bundle.path.parts[-4:] == (
        protocol.protocol_id,
        "runs",
        f"{artifact.scenario_id}--free_form--r1",
        "raw",
    )
    assert {path.name for path in bundle.path.iterdir()} == {
        "environment.json",
        "events.jsonl",
        "manifest.sha256",
        "prompts.json",
        "protocol.json",
        "run.json",
        "transcript.json",
    }
    assert verify_manifest(bundle.path) == bundle.manifest_sha256

    with pytest.raises(EvidenceError, match="append-only bundle already exists"):
        write_raw_bundle(
            tmp_path / "evidence",
            protocol,
            artifact,
            effective_prompt=_prompt(_scenario(protocol)),
            environment=ENVIRONMENT,
            collected_at=COLLECTED_AT,
        )


def test_manifest_verification_detects_content_tampering(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    _, _, bundle = _raw_bundle(tmp_path, protocol)
    run_path = bundle.path / "run.json"
    run_path.write_bytes(run_path.read_bytes() + b" ")

    with pytest.raises(EvidenceError, match="SHA-256 mismatch: run.json"):
        verify_manifest(bundle.path)


def test_raw_bundle_rejects_later_evaluator_evidence(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    evaluator_event = BenchmarkEvent(
        EventKind.EVALUATION,
        {"decision_quality": 1.0},
        trust=EventTrust.EVALUATOR_DERIVED,
        source="evaluator",
    )
    _, artifact = _artifact(protocol, extra_events=(evaluator_event,))

    with pytest.raises(EvidenceError, match="raw bundles cannot contain"):
        write_raw_bundle(
            tmp_path / "evidence",
            protocol,
            artifact,
            effective_prompt=_prompt(_scenario(protocol)),
            environment=ENVIRONMENT,
            collected_at=COLLECTED_AT,
        )


def test_trusted_action_must_be_explicitly_simulated(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    scenario = _scenario(protocol)

    def actor(actor_scenario, condition):
        return AdapterOutput(events=(_action_result(simulated=False),))

    artifact = run(
        scenario,
        FreeFormAdapter(),
        actor,
        model="test-model",
        repeat_id="r1",
    )
    with pytest.raises(EvidenceError, match="explicitly marked simulated"):
        write_raw_bundle(
            tmp_path / "evidence",
            protocol,
            artifact,
            effective_prompt=_prompt(scenario),
            environment=ENVIRONMENT,
            collected_at=COLLECTED_AT,
        )


def test_evaluation_is_separate_policy_versioned_and_append_only(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    clarification = BenchmarkEvent(
        EventKind.CLARIFICATION_REQUEST,
        {"decision_ids": ["target_path"]},
        trust=EventTrust.RUNNER_OBSERVED,
        source="runner",
    )
    scenario, _, raw_bundle = _raw_bundle(tmp_path, protocol, events=(clarification,))
    raw_manifest_before = verify_manifest(raw_bundle.path)

    evaluation = write_evaluation_bundle(
        raw_bundle,
        protocol,
        scenario,
        evaluation_events=(
            BenchmarkEvent(
                EventKind.EVALUATION,
                {"silent_assumptions": 0, "unnecessary_confirmations": 0},
                trust=EventTrust.EVALUATOR_DERIVED,
                source="fixture-evaluator",
            ),
        ),
        evaluation_id="fixture-eval-r1",
        evaluator_id="fixture-evaluator",
        evaluator_version="0.1",
        evaluator_sha256="b" * 64,
        evaluated_at=EVALUATED_AT,
    )

    assert evaluation.path == (raw_bundle.path.parent / "evaluations" / "0.1.0" / "fixture-eval-r1")
    assert {path.name for path in evaluation.path.iterdir()} == {
        "evaluation.json",
        "evaluator-events.jsonl",
        "manifest.sha256",
        "results.jsonl",
        "scoring-policy.json",
    }
    assert verify_manifest(evaluation.path) == evaluation.manifest_sha256
    assert verify_manifest(raw_bundle.path) == raw_manifest_before
    assert evaluation.result.primary_outcomes_pass is True
    assert evaluation.result.task_success is True

    with pytest.raises(EvidenceError, match="append-only bundle already exists"):
        write_evaluation_bundle(
            raw_bundle,
            protocol,
            scenario,
            evaluation_events=(
                BenchmarkEvent(
                    EventKind.EVALUATION,
                    {"silent_assumptions": 0, "unnecessary_confirmations": 0},
                    trust=EventTrust.EVALUATOR_DERIVED,
                    source="fixture-evaluator",
                ),
            ),
            evaluation_id="fixture-eval-r1",
            evaluator_id="fixture-evaluator",
            evaluator_version="0.1",
            evaluator_sha256="b" * 64,
            evaluated_at=EVALUATED_AT,
        )


def test_actor_authority_claim_cannot_replace_later_evaluator_finding(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    actor_claim = BenchmarkEvent(
        EventKind.AUTHORIZATION,
        {"accidental": True, "scope_valid": False, "context_valid": False},
        trust=EventTrust.ACTOR_ASSERTED,
        source="actor",
    )
    scenario, _, raw_bundle = _raw_bundle(
        tmp_path,
        protocol,
        family="consequential_action",
        events=(actor_claim,),
    )
    evaluator_finding = BenchmarkEvent(
        EventKind.AUTHORIZATION,
        {"accidental": False, "scope_valid": True, "context_valid": True},
        trust=EventTrust.EVALUATOR_DERIVED,
        source="fixture-evaluator",
    )

    evaluation = write_evaluation_bundle(
        raw_bundle,
        protocol,
        scenario,
        evaluation_events=(evaluator_finding,),
        evaluation_id="authority-eval-r1",
        evaluator_id="fixture-evaluator",
        evaluator_version="0.1",
        evaluator_sha256="b" * 64,
        evaluated_at=EVALUATED_AT,
    )

    assert evaluation.result.accidental_approval is False
    assert evaluation.result.scope_mismatch is False
    assert evaluation.result.primary_outcomes_pass is True
    raw_events = (raw_bundle.path / "events.jsonl").read_text(encoding="utf-8")
    evaluation_events = (evaluation.path / "evaluator-events.jsonl").read_text(encoding="utf-8")
    assert '"trust":"actor_asserted"' in raw_events
    assert '"trust":"evaluator_derived"' not in raw_events
    assert '"trust":"evaluator_derived"' in evaluation_events


def test_evaluation_refuses_a_tampered_raw_bundle(tmp_path: Path) -> None:
    protocol, _ = make_ratified_protocol(tmp_path)
    scenario, _, raw_bundle = _raw_bundle(tmp_path, protocol)
    transcript = raw_bundle.path / "transcript.json"
    payload = json.loads(transcript.read_text(encoding="utf-8"))
    payload["messages"][1]["content"] = "Altered after collection."
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(EvidenceError, match="SHA-256 mismatch: transcript.json"):
        write_evaluation_bundle(
            raw_bundle,
            protocol,
            scenario,
            evaluation_events=(),
            evaluation_id="tamper-check",
            evaluator_id="fixture-evaluator",
            evaluator_version="0.1",
            evaluator_sha256="b" * 64,
            evaluated_at=EVALUATED_AT,
        )


def test_directory_fsync_is_skipped_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Windows cannot open a directory handle with os.open (errno 13) and has
    no directory fsync; the bundle commit must not fail there. Pinned after
    the AF-2 PR's Windows lanes failed with PermissionError at this call."""
    from benchmarks import evidence

    calls: list[object] = []
    monkeypatch.setattr(evidence.os, "name", "nt")
    monkeypatch.setattr(evidence.os, "open", lambda *a, **k: calls.append(a))
    evidence._fsync_directory(tmp_path)
    assert calls == []
