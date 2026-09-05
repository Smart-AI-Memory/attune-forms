"""Versioned, provider-neutral scoring for interaction benchmark evidence."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from benchmarks.runner import (
    SCENARIO_FAMILIES,
    EventKind,
    EventTrust,
    RunArtifact,
    Scenario,
)

DEFAULT_POLICY_PATH = Path(__file__).parent / "policies" / "scoring-v0.1.json"

OutcomeValue = bool | int | float | None
ValueType = Literal["boolean", "integer", "number"]


class ScoringPolicyError(ValueError):
    """The policy or retained evidence cannot be scored deterministically."""


@dataclass(frozen=True)
class PassRule:
    operator: str
    value: bool | int | float

    def accepts(self, observed: bool | int | float) -> bool:
        if self.operator == "equals":
            return observed == self.value
        if self.operator == "at_least":
            return observed >= self.value
        if self.operator == "at_most":
            return observed <= self.value
        raise ScoringPolicyError(f"unsupported pass operator: {self.operator}")


@dataclass(frozen=True)
class SourceRule:
    mode: str
    event_kind: EventKind
    field: str | None = None
    transform: str = "identity"
    reducer: str = "single"


@dataclass(frozen=True)
class OutcomeRule:
    name: str
    description: str
    value_type: ValueType
    direction: str
    pass_rule: PassRule
    source: SourceRule
    allowed_trust: tuple[EventTrust, ...]


@dataclass(frozen=True)
class FamilyPolicy:
    family: str
    outcomes: tuple[OutcomeRule, ...]

    def by_name(self) -> dict[str, OutcomeRule]:
        return {rule.name: rule for rule in self.outcomes}


@dataclass(frozen=True)
class ScoringPolicy:
    policy_version: str
    benchmark_version: str
    missing_data: str
    safety_outcomes: frozenset[str]
    secondary_outcomes: tuple[OutcomeRule, ...]
    families: Mapping[str, FamilyPolicy]
    source_path: Path
    source_sha256: str

    def family(self, name: str) -> FamilyPolicy:
        try:
            return self.families[name]
        except KeyError as exc:
            raise ScoringPolicyError(f"policy has no scenario family: {name}") from exc


@dataclass(frozen=True)
class PolicyEvaluation:
    policy_version: str
    outcomes: Mapping[str, OutcomeValue]
    primary_outcomes: Mapping[str, OutcomeValue]
    missing_primary_outcomes: tuple[str, ...]
    primary_outcomes_pass: bool | None


def _parse_outcome(raw: dict[str, Any]) -> OutcomeRule:
    allowed_trust = tuple(EventTrust(value) for value in raw["allowed_trust"])
    if EventTrust.ACTOR_ASSERTED in allowed_trust:
        raise ScoringPolicyError("actor_asserted evidence is prohibited by scoring policy")
    source_raw = raw["source"]
    mode = source_raw["mode"]
    source = SourceRule(
        mode=mode,
        event_kind=EventKind(source_raw["event_kind"]),
        field=source_raw.get("field"),
        transform=source_raw.get("transform", "identity"),
        reducer=source_raw.get("reducer", "single"),
    )
    if source.mode == "field" and source.field is None:
        raise ScoringPolicyError(f"outcome {raw['name']} requires a source field")
    rule = OutcomeRule(
        name=raw["name"],
        description=raw["description"],
        value_type=raw["value_type"],
        direction=raw["direction"],
        pass_rule=PassRule(raw["pass"]["operator"], raw["pass"]["value"]),
        source=source,
        allowed_trust=allowed_trust,
    )
    expected_operators = {
        "lower": {"at_most", "equals"},
        "higher": {"at_least", "equals"},
    }
    if rule.pass_rule.operator not in expected_operators[rule.direction]:
        raise ScoringPolicyError(f"outcome {rule.name} pass operator contradicts its direction")
    _validate_value(rule, rule.pass_rule.value)
    return rule


def load_scoring_policy(path: Path = DEFAULT_POLICY_PATH) -> ScoringPolicy:
    source = path.read_bytes()
    raw = json.loads(source)
    if raw["missing_data"] != "null":
        raise ScoringPolicyError("missing_data must be null")
    if set(raw["families"]) != set(SCENARIO_FAMILIES):
        raise ScoringPolicyError("policy must define exactly the six scenario families")
    families: dict[str, FamilyPolicy] = {}
    seen_names: set[str] = set()
    for family, family_raw in raw["families"].items():
        outcomes = tuple(_parse_outcome(item) for item in family_raw["outcomes"])
        names = [item.name for item in outcomes]
        if len(names) != len(set(names)):
            raise ScoringPolicyError(f"duplicate outcome in family {family}")
        seen_names.update(names)
        families[family] = FamilyPolicy(family=family, outcomes=outcomes)
    secondary = tuple(_parse_outcome(item) for item in raw["secondary_outcomes"])
    secondary_names = [item.name for item in secondary]
    if len(secondary_names) != len(set(secondary_names)):
        raise ScoringPolicyError("duplicate secondary outcome")
    family_secondary_conflicts = set(secondary_names) & seen_names
    if family_secondary_conflicts:
        raise ScoringPolicyError(
            "secondary outcomes conflict with family outcomes: "
            + ", ".join(sorted(family_secondary_conflicts))
        )
    safety = frozenset(raw["safety_outcomes"])
    unknown_safety = safety - seen_names
    if unknown_safety:
        raise ScoringPolicyError(
            f"safety outcomes are not defined by a family: {', '.join(sorted(unknown_safety))}"
        )
    return ScoringPolicy(
        policy_version=raw["policy_version"],
        benchmark_version=raw["benchmark_version"],
        missing_data=raw["missing_data"],
        safety_outcomes=safety,
        secondary_outcomes=secondary,
        families=MappingProxyType(families),
        source_path=path.resolve(),
        source_sha256=hashlib.sha256(source).hexdigest(),
    )


def _validate_value(rule: OutcomeRule, value: Any) -> bool | int | float:
    if rule.value_type == "boolean":
        if not isinstance(value, bool):
            raise ScoringPolicyError(f"outcome {rule.name} requires a boolean")
        return value
    if rule.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ScoringPolicyError(f"outcome {rule.name} requires a non-negative integer")
        return value
    if rule.value_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ScoringPolicyError(f"outcome {rule.name} requires a number")
        number = float(value)
        if not 0.0 <= number <= 1.0:
            raise ScoringPolicyError(f"outcome {rule.name} must be between 0 and 1")
        return number
    raise ScoringPolicyError(f"unsupported value type: {rule.value_type}")


def _transform(rule: OutcomeRule, value: Any) -> Any:
    if rule.source.transform == "identity":
        return value
    if rule.source.transform == "invert_boolean":
        if not isinstance(value, bool):
            raise ScoringPolicyError(f"outcome {rule.name} can only invert a boolean")
        return not value
    raise ScoringPolicyError(f"unsupported transform: {rule.source.transform}")


def _evaluate_rule(artifact: RunArtifact, rule: OutcomeRule) -> OutcomeValue:
    if artifact.incomplete or artifact.error is not None:
        return None
    events = [
        event
        for event in artifact.events
        if event.kind is rule.source.event_kind and event.trust in rule.allowed_trust
    ]
    if rule.source.mode == "count_events":
        return _validate_value(rule, len(events))
    if rule.source.mode != "field":
        raise ScoringPolicyError(f"unsupported source mode: {rule.source.mode}")
    if any(rule.source.field not in event.payload for event in events):
        return None
    values = [_transform(rule, event.payload[rule.source.field]) for event in events]
    if not values:
        return None
    if rule.source.reducer == "any_true":
        if not all(isinstance(value, bool) for value in values):
            raise ScoringPolicyError(f"outcome {rule.name} any_true reducer requires booleans")
        return _validate_value(rule, any(values))
    if rule.source.reducer != "single":
        raise ScoringPolicyError(f"unsupported reducer: {rule.source.reducer}")
    if any(value != values[0] for value in values[1:]):
        raise ScoringPolicyError(f"conflicting evaluator values for outcome {rule.name}")
    return _validate_value(rule, values[0])


def evaluate_policy(
    artifact: RunArtifact,
    scenario: Scenario,
    policy: ScoringPolicy | None = None,
) -> PolicyEvaluation:
    active = policy or load_scoring_policy()
    if artifact.benchmark_version != active.benchmark_version:
        raise ScoringPolicyError("artifact benchmark version does not match scoring policy")
    if scenario.benchmark_version != active.benchmark_version:
        raise ScoringPolicyError("scenario benchmark version does not match scoring policy")
    if (
        artifact.scenario_id != scenario.actor.id
        or artifact.scenario_family != scenario.actor.family
    ):
        raise ScoringPolicyError("artifact identity does not match scenario")

    family = active.family(scenario.actor.family)
    rules = family.by_name()
    primary_names = tuple(scenario.evaluator.primary_outcomes)
    missing_rules = set(primary_names) - set(rules)
    if missing_rules:
        raise ScoringPolicyError(
            f"policy does not define primary outcomes: {', '.join(sorted(missing_rules))}"
        )

    all_rules = family.outcomes + active.secondary_outcomes
    outcomes = MappingProxyType({rule.name: _evaluate_rule(artifact, rule) for rule in all_rules})
    primary = MappingProxyType({name: outcomes[name] for name in primary_names})
    missing = tuple(name for name, value in primary.items() if value is None)
    if artifact.incomplete or artifact.error is not None or missing:
        primary_pass: bool | None = None
    else:
        primary_pass = all(rules[name].pass_rule.accepts(primary[name]) for name in primary_names)
    return PolicyEvaluation(
        policy_version=active.policy_version,
        outcomes=outcomes,
        primary_outcomes=primary,
        missing_primary_outcomes=missing,
        primary_outcomes_pass=primary_pass,
    )
