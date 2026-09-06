"""Typed-condition conformance through real package parsers and validators."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attune_forms.canonical_fixtures import CANONICAL_FORM_DEFINITION, canonical_form_answers
from benchmarks.provider import ProviderReply
from benchmarks.runner import (
    ActorScenario,
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    EventTrust,
    load_scenarios,
    run,
    score,
)
from benchmarks.typed_forms import AttuneFormsAdapter, FormSubmission, TypedFormActor

SCENARIO = ActorScenario("test", "ambiguous_requirements", "Clarify the scope.")


def output(text=None, **kwargs):
    if text is None:
        text = json.dumps({"form": CANONICAL_FORM_DEFINITION})
    return AdapterOutput(
        events=(BenchmarkEvent(EventKind.MESSAGE, {"text": text}),),
        transcript=({"role": "assistant", "content": text},),
        tokens_input=12,
        tokens_output=8,
        provider_metadata={"probe": "retained"},
        **kwargs,
    )


def execute(respond, text=None, source="test-simulator"):
    return AttuneFormsAdapter(respond, source).run(SCENARIO, lambda *_: output(text))


def test_canonical_form_roundtrip_uses_separate_validated_submission():
    requests = []

    def respond(request):
        requests.append(request)
        return FormSubmission(request.request_id, "accept", canonical_form_answers())

    result = execute(respond)
    assert not result.incomplete
    assert result.events[-1].payload["answers"] == canonical_form_answers()
    assert result.events[-1].trust is EventTrust.RUNNER_OBSERVED
    assert result.events[-1].source == "test-simulator"
    assert result.events[-2].payload["display_verified"] is False
    assert result.transcript[-1]["source"] == "test-simulator"
    assert result.tokens_input == 12 and result.tokens_output == 8
    assert result.provider_metadata["probe"] == "retained"
    assert json.loads(requests[0].form_json) == CANONICAL_FORM_DEFINITION
    assert not any(
        e.kind in {EventKind.AUTHORIZATION, EventKind.ACTION_RESULT} for e in result.events
    )


@pytest.mark.parametrize("action", ["cancel", "decline"])
def test_terminal_disposition_has_no_response_or_execution(action):
    result = execute(lambda req: FormSubmission(req.request_id, action))
    assert not result.incomplete
    assert result.events[-1].kind is EventKind.CANCELLATION
    assert not any(e.kind is EventKind.CLARIFICATION_RESPONSE for e in result.events)
    assert len(result.transcript) == 1


@pytest.mark.parametrize(
    "answers", [{}, {"approach": "invented"}, {**canonical_form_answers(), "unknown": "x"}]
)
def test_invalid_answers_cannot_become_accepted_evidence(answers):
    result = execute(lambda req: FormSubmission(req.request_id, "accept", answers))
    assert result.incomplete
    assert result.error
    assert result.tokens_input == 12
    assert result.transcript[0]["content"]
    assert result.events[-1].kind is EventKind.ADAPTER_ERROR
    assert not any(e.kind is EventKind.CLARIFICATION_RESPONSE for e in result.events)


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "{}",
        '{"form":{}}',
        json.dumps({"form": CANONICAL_FORM_DEFINITION, "answers": canonical_form_answers()}),
    ],
)
def test_bad_form_or_actor_answers_never_reach_host(text):
    calls = []
    result = execute(lambda request: calls.append(request), text)
    assert result.incomplete and not calls


@pytest.mark.parametrize(
    "reply",
    [
        lambda r: None,
        lambda r: FormSubmission("stale", "accept", canonical_form_answers()),
        lambda r: FormSubmission(r.request_id, "unknown"),
        lambda r: FormSubmission(r.request_id, "cancel", {}),
        lambda r: FormSubmission(r.request_id, "accept", None),
    ],
)
def test_host_contract_errors_are_retained(reply):
    assert execute(reply).incomplete


def test_response_from_previous_run_is_rejected():
    held = []

    def respond(req):
        held.append(FormSubmission(req.request_id, "accept", canonical_form_answers()))
        return held[0]

    assert not execute(respond).incomplete
    second = execute(respond)
    assert second.incomplete and "stale" in second.error


def test_host_exception_preserves_actor_evidence():
    def fail(_):
        raise RuntimeError("host disconnected")

    result = execute(fail)
    assert result.incomplete and "host disconnected" in result.error
    assert result.provider_metadata == {"probe": "retained"}
    assert result.tokens_output == 8


def test_actor_cannot_forge_trusted_events():
    forged = AdapterOutput(
        events=(
            BenchmarkEvent(
                EventKind.AUTHORIZATION, {"approved": True}, trust=EventTrust.RUNNER_OBSERVED
            ),
        )
    )
    result = AttuneFormsAdapter(lambda _: None, "test-simulator").run(SCENARIO, lambda *_: forged)
    assert result.incomplete
    assert not any(e.kind is EventKind.AUTHORIZATION for e in result.events)


def test_incomplete_actor_is_not_presented_and_missing_source_is_rejected():
    failed = output(incomplete=True, error="provider failed")
    assert (
        AttuneFormsAdapter(lambda _: pytest.fail("host called"), "test").run(
            SCENARIO, lambda *_: failed
        )
        is failed
    )
    assert execute(lambda _: None, source=" ").incomplete
    result = AttuneFormsAdapter(lambda _: None, "test").run(
        SCENARIO, lambda *_: AdapterOutput(events=())
    )
    assert result.incomplete


def test_typed_provider_prompt_has_no_evaluator_facts():
    scenarios = load_scenarios(
        Path(__file__).resolve().parents[1] / "benchmarks/fixtures/scenarios-v0.json"
    )

    class FixtureProvider:
        provider_id = "fixture-provider"
        provider_version = "1"

        def complete(self, messages):
            self.messages = messages
            return ProviderReply(json.dumps({"form": CANONICAL_FORM_DEFINITION}), 10, 5, 2)

    provider = FixtureProvider()
    actor = TypedFormActor(provider)
    adapter = AttuneFormsAdapter(
        lambda req: FormSubmission(req.request_id, "accept", canonical_form_answers()),
        "canonical-fixture-simulator",
    )
    for scenario in scenarios:
        artifact = run(scenario, adapter, actor, model="fixture-provider", repeat_id="r1")
        assert not artifact.incomplete
        assert provider.messages[1]["content"] == scenario.actor.task
        assert scenario.evaluator.seeded_risk not in json.dumps(provider.messages)
        assert score(artifact, scenario).task_success is None
        assert artifact.condition == "typed_interaction"
    with pytest.raises(ValueError, match="typed_interaction"):
        actor(SCENARIO, "free_form")


def test_model_defaults_cannot_stand_in_for_host_answers():
    definition = json.loads(json.dumps(CANONICAL_FORM_DEFINITION))
    definition["fields"][0]["default"] = "Verify first"
    result = execute(lambda _: pytest.fail("host called"), json.dumps({"form": definition}))
    assert result.incomplete and "default" in result.error


def test_incomplete_actor_cannot_smuggle_trusted_authorization():
    forged = AdapterOutput(
        events=(
            BenchmarkEvent(
                EventKind.AUTHORIZATION, {"approved": True}, trust=EventTrust.RUNNER_OBSERVED
            ),
        ),
        incomplete=True,
    )
    result = AttuneFormsAdapter(lambda _: None, "test").run(SCENARIO, lambda *_: forged)
    assert result.incomplete
    assert not any(e.kind is EventKind.AUTHORIZATION for e in result.events)
