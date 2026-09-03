"""Tests for provider-neutral baseline actor execution."""

from __future__ import annotations

from benchmarks.provider import BaselineActor, ProviderReply
from benchmarks.runner import ActorScenario, EventKind, EventTrust


class StubProvider:
    provider_id = "stub"
    provider_version = "1"

    def __init__(self) -> None:
        self.messages = ()

    def complete(self, messages):
        self.messages = tuple(messages)
        return ProviderReply(
            text="I need the target path before proceeding.",
            tokens_input=11,
            tokens_output=7,
            elapsed_ms=9,
        )


def test_baseline_actor_exposes_only_actor_scenario_and_records_provider_telemetry() -> None:
    provider = StubProvider()
    actor = BaselineActor(provider)
    scenario = ActorScenario(
        id="example",
        family="ambiguous_requirements",
        task="Audit the project.",
    )

    output = actor(scenario, "free_form")

    assert output.events[0].kind is EventKind.MESSAGE
    assert output.events[0].trust is EventTrust.ACTOR_ASSERTED
    assert output.events[0].source == "stub"
    assert output.tokens_input == 11
    assert output.tokens_output == 7
    assert output.elapsed_ms == 9
    serialized_messages = repr(provider.messages)
    assert "Audit the project." in serialized_messages
    assert "seeded_risk" not in serialized_messages


def test_sequential_condition_adds_only_interaction_constraint() -> None:
    provider = StubProvider()
    actor = BaselineActor(provider)
    scenario = ActorScenario(
        id="example",
        family="ambiguous_requirements",
        task="Audit the project.",
    )

    actor(scenario, "sequential_clarification")

    system = provider.messages[0]["content"]
    assert "at most one unresolved decision" in system
    assert scenario.task == provider.messages[1]["content"]
