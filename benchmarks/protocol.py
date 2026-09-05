"""Pre-run protocol loading and baseline-collection readiness checks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from benchmarks.runner import load_scenarios
from benchmarks.scoring import load_scoring_policy

DEFAULT_PROTOCOL_PATH = Path(__file__).parent / "protocols" / "baseline-pilot-v0.1.draft.json"

_BASELINE_CONDITIONS = {
    ("free_form", "baseline/free-form", "0.1"),
    ("sequential_clarification", "baseline/sequential-clarification", "0.1"),
}
_SAMPLING_CONTROLS = ("temperature", "top_p", "seed", "max_output_tokens")
_PLACEHOLDERS = {"", "chair_required", "pending", "tbd", "todo", "unknown"}


class ProtocolError(ValueError):
    """The run protocol is malformed or not authorized for collection."""


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_root_for(path: Path) -> Path:
    for candidate in path.resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "benchmarks").is_dir():
            return candidate
    raise ProtocolError(f"cannot determine project root for protocol: {path}")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProtocolError(f"protocol field {name} must be an object")
    return value


def _concrete_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in _PLACEHOLDERS


def _timestamp_with_offset(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


@dataclass(frozen=True)
class RunProtocol:
    """An immutable snapshot of one protocol file."""

    source_path: Path
    project_root: Path
    source_sha256: str
    payload: Mapping[str, Any]

    @property
    def protocol_id(self) -> str:
        return str(self.payload["protocol_id"])

    @property
    def protocol_version(self) -> str:
        return str(self.payload["protocol_version"])

    @property
    def benchmark_version(self) -> str:
        return str(self.payload["benchmark_version"])

    @property
    def scoring_policy_version(self) -> str:
        section = _mapping(self.payload["scoring_policy"], "scoring_policy")
        return str(section["version"])

    @property
    def repeats(self) -> int:
        return int(self.payload["repeats_per_scenario_condition"])

    def as_dict(self) -> dict[str, Any]:
        """Return a detached JSON-compatible copy."""

        thawed = _thaw(self.payload)
        if not isinstance(thawed, dict):  # pragma: no cover - constructor invariant
            raise ProtocolError("protocol payload must be an object")
        return thawed

    def resolve_repo_file(self, section_name: str) -> Path:
        section = _mapping(self.payload[section_name], section_name)
        raw_path = section.get("path")
        if not isinstance(raw_path, str):
            raise ProtocolError(f"protocol field {section_name}.path must be a string")
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ProtocolError(f"protocol field {section_name}.path must remain in the project")
        resolved = (self.project_root / Path(*relative.parts)).resolve()
        if not resolved.is_relative_to(self.project_root.resolve()):
            raise ProtocolError(f"protocol field {section_name}.path escapes the project")
        return resolved


def load_run_protocol(
    path: Path = DEFAULT_PROTOCOL_PATH,
    *,
    project_root: Path | None = None,
) -> RunProtocol:
    source_path = path.resolve()
    source = source_path.read_bytes()
    try:
        raw = json.loads(source)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"invalid protocol JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ProtocolError("protocol root must be an object")
    required = {
        "protocol_version",
        "protocol_id",
        "status",
        "benchmark_version",
        "fixture",
        "scoring_policy",
        "conditions",
        "provider",
        "sampling",
        "repeats_per_scenario_condition",
        "exclusions",
        "missing_data",
        "falsification_rules",
        "real_external_actions",
        "checkpoint",
    }
    missing = required - set(raw)
    if missing:
        raise ProtocolError(f"protocol is missing fields: {', '.join(sorted(missing))}")
    root = (project_root or _project_root_for(source_path)).resolve()
    return RunProtocol(
        source_path=source_path,
        project_root=root,
        source_sha256=hashlib.sha256(source).hexdigest(),
        payload=_freeze(raw),
    )


def collection_blockers(protocol: RunProtocol) -> tuple[str, ...]:
    """Return every known reason the protocol cannot collect baseline runs."""

    blockers: list[str] = []
    payload = protocol.payload

    if _sha256(protocol.source_path) != protocol.source_sha256:
        blockers.append("protocol file changed after it was loaded")
    if payload.get("status") != "ratified":
        blockers.append("protocol status is not ratified")

    checkpoint = _mapping(payload["checkpoint"], "checkpoint")
    if checkpoint.get("id") != "B.1":
        blockers.append("checkpoint id is not B.1")
    if checkpoint.get("ruling") != "COLLECTION_AUTHORIZED":
        blockers.append("Checkpoint B.1 does not authorize collection")
    if not _concrete_text(checkpoint.get("authorized_by")):
        blockers.append("Checkpoint B.1 has no authorizing chair")
    if not _timestamp_with_offset(checkpoint.get("authorized_at")):
        blockers.append("Checkpoint B.1 has no authorization timestamp")

    provider = _mapping(payload["provider"], "provider")
    for field in ("provider_id", "provider_api_version", "model_id", "model_version"):
        if not _concrete_text(provider.get(field)):
            blockers.append(f"provider.{field} is unresolved")

    sampling = _mapping(payload["sampling"], "sampling")
    if sampling.get("mode") not in {"deterministic", "stochastic", "provider_default"}:
        blockers.append("sampling.mode is unresolved")
    unsupported = _mapping(
        sampling.get("unsupported_or_unavailable"),
        "sampling.unsupported_or_unavailable",
    )
    unknown_controls = set(unsupported) - set(_SAMPLING_CONTROLS)
    if unknown_controls:
        blockers.append(
            "sampling unsupported declarations name unknown controls: "
            + ", ".join(sorted(unknown_controls))
        )
    for field in _SAMPLING_CONTROLS:
        if sampling.get(field) is None and not _concrete_text(unsupported.get(field)):
            blockers.append(f"sampling.{field} is neither set nor declared unavailable")

    try:
        repeats = int(payload["repeats_per_scenario_condition"])
    except (TypeError, ValueError):
        blockers.append("repeats_per_scenario_condition is not an integer")
    else:
        if repeats < 3:
            blockers.append("repeats_per_scenario_condition is less than 3")

    raw_conditions = payload.get("conditions")
    if not isinstance(raw_conditions, tuple):
        blockers.append("conditions is not an array")
    else:
        observed_conditions: set[tuple[str, str, str]] = set()
        for index, raw_condition in enumerate(raw_conditions):
            condition = _mapping(raw_condition, f"conditions[{index}]")
            observed_conditions.add(
                (
                    str(condition.get("condition")),
                    str(condition.get("adapter_id")),
                    str(condition.get("adapter_version")),
                )
            )
        if len(raw_conditions) != 2 or observed_conditions != _BASELINE_CONDITIONS:
            blockers.append("conditions do not exactly match the two AF-1 baseline adapters")

    if payload.get("execution_order") != "scenario_condition_repeat":
        blockers.append("execution order is unresolved")

    exclusions = _mapping(payload["exclusions"], "exclusions")
    if exclusions.get("post_run") != "none":
        blockers.append("post-run exclusions are permitted")
    if exclusions.get("retain_incomplete") is not True:
        blockers.append("incomplete runs are not guaranteed to be retained")

    missing_data = _mapping(payload["missing_data"], "missing_data")
    if missing_data.get("metric_value") != "null":
        blockers.append("missing metric values are not declared null")
    if missing_data.get("task_success_if_primary_missing") != "null":
        blockers.append("missing primary evidence does not force null task success")

    falsification_rules = payload.get("falsification_rules")
    if not isinstance(falsification_rules, tuple) or not falsification_rules:
        blockers.append("no falsification rules are declared")
    else:
        ids = [str(_mapping(rule, "falsification rule").get("id")) for rule in falsification_rules]
        if len(ids) != len(set(ids)):
            blockers.append("falsification rule ids are not unique")

    if payload.get("real_external_actions") is not False:
        blockers.append("real external actions are not prohibited")

    fixture = _mapping(payload["fixture"], "fixture")
    policy_ref = _mapping(payload["scoring_policy"], "scoring_policy")
    try:
        fixture_path = protocol.resolve_repo_file("fixture")
        if not fixture_path.is_file():
            blockers.append("fixture file does not exist")
        elif _sha256(fixture_path) != fixture.get("sha256"):
            blockers.append("fixture SHA-256 does not match the protocol")
        else:
            scenarios = load_scenarios(fixture_path)
            if len(scenarios) != fixture.get("scenario_count"):
                blockers.append("fixture scenario count does not match the protocol")
            if any(item.benchmark_version != protocol.benchmark_version for item in scenarios):
                blockers.append("fixture benchmark version does not match the protocol")
    except (OSError, ProtocolError, ValueError, KeyError) as exc:
        blockers.append(f"fixture cannot be validated: {exc}")

    try:
        policy_path = protocol.resolve_repo_file("scoring_policy")
        if not policy_path.is_file():
            blockers.append("scoring policy file does not exist")
        elif _sha256(policy_path) != policy_ref.get("sha256"):
            blockers.append("scoring policy SHA-256 does not match the protocol")
        else:
            policy = load_scoring_policy(policy_path)
            if policy.policy_version != protocol.scoring_policy_version:
                blockers.append("scoring policy version does not match the protocol")
            if policy.benchmark_version != protocol.benchmark_version:
                blockers.append("scoring policy benchmark version does not match the protocol")
    except (OSError, ProtocolError, ValueError, KeyError) as exc:
        blockers.append(f"scoring policy cannot be validated: {exc}")

    return tuple(blockers)


def assert_ready_for_collection(protocol: RunProtocol) -> None:
    """Fail closed unless every pre-run declaration and chair gate is satisfied."""

    blockers = collection_blockers(protocol)
    if blockers:
        raise ProtocolError("collection blocked: " + "; ".join(blockers))
