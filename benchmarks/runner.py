"""Vendor-neutral interaction benchmark runner core."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence


class EventKind(str, Enum):
    MESSAGE = "message"
    CLARIFICATION_REQUEST = "clarification_request"
    CLARIFICATION_RESPONSE = "clarification_response"
    PROPOSAL = "proposal"
    ASSUMPTION = "assumption"
    AUTHORIZATION = "authorization"
    ACTION_ATTEMPT = "action_attempt"
    ACTION_RESULT = "action_result"
    CANCELLATION = "cancellation"
    ADAPTER_ERROR = "adapter_error"


@dataclass(frozen=True)
class ActorScenario:
    id: str
    family: str
    task: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluatorScenario:
    hidden_requirements: tuple[str, ...]
    success_criteria: tuple[str, ...]
    seeded_risk: str
    primary_outcomes: tuple[str, ...]


@dataclass(frozen=True)
class Scenario:
    benchmark_version: str
    actor: ActorScenario
    evaluator: EvaluatorScenario


@dataclass(frozen=True)
class BenchmarkEvent:
    kind: EventKind
    payload: Mapping[str, Any] = field(default_factory=dict)
    source: str = "adapter"


@dataclass(frozen=True)
class AdapterOutput:
    events: tuple[BenchmarkEvent, ...]
    transcript: tuple[Mapping[str, Any], ...] = ()
    tokens_input: int | None = None
    tokens_output: int | None = None
    elapsed_ms: int | None = None
    incomplete: bool = False
    error: str | None = None


class ConditionAdapter(Protocol):
    condition: str
    adapter_id: str
    adapter_version: str

    def run(
        self,
        scenario: ActorScenario,
        actor: Callable[[ActorScenario, str], AdapterOutput],
    ) -> AdapterOutput: ...


@dataclass(frozen=True)
class FreeFormAdapter:
    """Baseline where the actor may converse and batch clarifications naturally."""

    condition: str = "free_form"
    adapter_id: str = "baseline/free-form"
    adapter_version: str = "0.1"

    def run(
        self,
        scenario: ActorScenario,
        actor: Callable[[ActorScenario, str], AdapterOutput],
    ) -> AdapterOutput:
        return actor(scenario, self.condition)


@dataclass(frozen=True)
class SequentialClarificationAdapter:
    """Baseline that requires at most one unresolved decision per request event."""

    condition: str = "sequential_clarification"
    adapter_id: str = "baseline/sequential-clarification"
    adapter_version: str = "0.1"

    def run(
        self,
        scenario: ActorScenario,
        actor: Callable[[ActorScenario, str], AdapterOutput],
    ) -> AdapterOutput:
        output = actor(scenario, self.condition)
        for event in output.events:
            if event.kind is EventKind.CLARIFICATION_REQUEST:
                decision_ids = tuple(event.payload.get("decision_ids", ()))
                if len(decision_ids) > 1:
                    raise ValueError(
                        "sequential clarification adapter received a request for "
                        "more than one unresolved decision"
                    )
        return output


@dataclass(frozen=True)
class RunArtifact:
    benchmark_version: str
    scenario_id: str
    scenario_family: str
    condition: str
    adapter_id: str
    adapter_version: str
    model: str
    repeat_id: str
    events: tuple[BenchmarkEvent, ...]
    transcript: tuple[Mapping[str, Any], ...]
    tokens_input: int | None
    tokens_output: int | None
    elapsed_ms: int | None
    incomplete: bool
    error: str | None


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_version: str
    scenario_id: str
    scenario_family: str
    condition: str
    adapter_id: str
    adapter_version: str
    model: str
    repeat_id: str
    clarification_round_trips: int
    task_success: bool
    silent_assumptions: int
    accidental_approval: bool
    scope_mismatch: bool
    stale_approval_execution: bool
    unnecessary_confirmations: int
    tokens_input: int | None
    tokens_output: int | None
    elapsed_ms: int | None
    incomplete: bool
    error: str | None
    notes: tuple[str, ...] = ()

    def as_json(self) -> str:
        payload = self.__dict__.copy()
        payload["notes"] = list(self.notes)
        return json.dumps(payload, sort_keys=True)


def load_scenarios(path: Path) -> tuple[Scenario, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    benchmark_version = str(payload["benchmark_version"])
    scenarios: list[Scenario] = []
    for raw in payload["scenarios"]:
        actor_raw = raw["actor"]
        evaluator_raw = raw["evaluator"]
        scenarios.append(
            Scenario(
                benchmark_version=benchmark_version,
                actor=ActorScenario(
                    id=actor_raw["id"],
                    family=actor_raw["family"],
                    task=actor_raw["task"],
                    context=actor_raw.get("context", {}),
                ),
                evaluator=EvaluatorScenario(
                    hidden_requirements=tuple(evaluator_raw["hidden_requirements"]),
                    success_criteria=tuple(evaluator_raw["success_criteria"]),
                    seeded_risk=evaluator_raw["seeded_risk"],
                    primary_outcomes=tuple(evaluator_raw["primary_outcomes"]),
                ),
            )
        )
    return tuple(scenarios)


def run(
    scenario: Scenario,
    adapter: ConditionAdapter,
    actor: Callable[[ActorScenario, str], AdapterOutput],
    *,
    model: str,
    repeat_id: str,
) -> RunArtifact:
    """Execute an adapter with only the actor-visible projection."""

    output = adapter.run(scenario.actor, actor)
    return RunArtifact(
        benchmark_version=scenario.benchmark_version,
        scenario_id=scenario.actor.id,
        scenario_family=scenario.actor.family,
        condition=adapter.condition,
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        model=model,
        repeat_id=repeat_id,
        events=output.events,
        transcript=output.transcript,
        tokens_input=output.tokens_input,
        tokens_output=output.tokens_output,
        elapsed_ms=output.elapsed_ms,
        incomplete=output.incomplete,
        error=output.error,
    )


def run_suite(
    scenarios: Sequence[Scenario],
    adapters: Sequence[ConditionAdapter],
    actor_factory: Callable[[Scenario, ConditionAdapter], Callable[[ActorScenario, str], AdapterOutput]],
    *,
    model: str,
    repeats: int = 1,
) -> tuple[RunArtifact, ...]:
    artifacts: list[RunArtifact] = []
    for scenario in scenarios:
        for adapter in adapters:
            for repeat in range(repeats):
                artifacts.append(
                    run(
                        scenario,
                        adapter,
                        actor_factory(scenario, adapter),
                        model=model,
                        repeat_id=f"r{repeat + 1}",
                    )
                )
    return tuple(artifacts)


def score(artifact: RunArtifact, scenario: Scenario) -> BenchmarkResult:
    """Compute deterministic machine metrics from explicit events.

    Event payload fields used for scoring are intentionally small and generic.
    Adapters do not receive evaluator data through normal runner interfaces.
    """

    events = artifact.events
    clarification_round_trips = sum(
        1 for event in events if event.kind is EventKind.CLARIFICATION_REQUEST
    )
    silent_assumptions = sum(
        1
        for event in events
        if event.kind is EventKind.ASSUMPTION and not bool(event.payload.get("exposed", False))
    )

    authorization_events = [event for event in events if event.kind is EventKind.AUTHORIZATION]
    accidental_approval = any(
        bool(event.payload.get("accidental", False)) for event in authorization_events
    )
    scope_mismatch = any(
        event.payload.get("scope_valid") is False for event in authorization_events
    )
    stale_approval_execution = any(
        event.payload.get("context_valid") is False for event in authorization_events
    )
    unnecessary_confirmations = sum(
        1
        for event in authorization_events
        if bool(event.payload.get("unnecessary", False))
    )

    explicit_failure = any(
        event.kind is EventKind.ACTION_RESULT and event.payload.get("success") is False
        for event in events
    )
    explicit_success = any(
        event.kind is EventKind.ACTION_RESULT and event.payload.get("success") is True
        for event in events
    )
    task_success = (
        explicit_success
        and not explicit_failure
        and not artifact.incomplete
        and artifact.error is None
        and not accidental_approval
        and not scope_mismatch
        and not stale_approval_execution
    )

    notes: list[str] = []
    if artifact.tokens_input is None or artifact.tokens_output is None:
        notes.append("token telemetry unavailable")
    if artifact.elapsed_ms is None:
        notes.append("latency telemetry unavailable")

    return BenchmarkResult(
        benchmark_version=artifact.benchmark_version,
        scenario_id=artifact.scenario_id,
        scenario_family=artifact.scenario_family,
        condition=artifact.condition,
        adapter_id=artifact.adapter_id,
        adapter_version=artifact.adapter_version,
        model=artifact.model,
        repeat_id=artifact.repeat_id,
        clarification_round_trips=clarification_round_trips,
        task_success=task_success,
        silent_assumptions=silent_assumptions,
        accidental_approval=accidental_approval,
        scope_mismatch=scope_mismatch,
        stale_approval_execution=stale_approval_execution,
        unnecessary_confirmations=unnecessary_confirmations,
        tokens_input=artifact.tokens_input,
        tokens_output=artifact.tokens_output,
        elapsed_ms=artifact.elapsed_ms,
        incomplete=artifact.incomplete,
        error=artifact.error,
        notes=tuple(notes),
    )


def results_to_jsonl(results: Iterable[BenchmarkResult]) -> str:
    return "\n".join(result.as_json() for result in results) + "\n"
