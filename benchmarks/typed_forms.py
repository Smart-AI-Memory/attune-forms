"""Typed attune-forms benchmark condition; no comparative collector is enabled."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from attune_forms import collect_form_response, form_from_dict
from benchmarks.provider import BaselineActor, TextProvider
from benchmarks.runner import (
    ActorScenario,
    AdapterOutput,
    BenchmarkEvent,
    EventKind,
    EventTrust,
)


@dataclass(frozen=True)
class FormRequest:
    """Immutable form snapshot presented to an injected host or simulator."""

    request_id: str
    form_json: str


@dataclass(frozen=True)
class FormSubmission:
    """Host disposition bound to the exact request; never model-supplied answers."""

    request_id: str
    action: str
    answers: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class TypedFormActor:
    """Ask the same text-provider seam for a form using only actor-visible facts."""

    provider: TextProvider

    @staticmethod
    def messages_for(scenario: ActorScenario) -> tuple[Mapping[str, str], ...]:
        """Add only the typed condition's output contract to the baseline prompt."""
        messages = BaselineActor.messages_for(scenario, "free_form")
        instruction = (
            ' Return only JSON with exactly one key, "form". Its value is an '
            'attune-forms definition: {"title":"Clarification","fields":'
            '[{"id":"scope","type":"text_input","text":"What scope?",'
            '"required":true}]}. Use stable unique field ids and ask for the '
            "missing decisions relevant to the task. text_input, single_select "
            "and multi_select are supported; select fields need an options array "
            "of strings. Do not provide answers, defaults, approval, or execution "
            "results on behalf of the user. No Markdown fences."
        )
        return ({"role": "system", "content": messages[0]["content"] + instruction}, messages[1])

    def __call__(self, scenario: ActorScenario, condition: str) -> AdapterOutput:
        """Retain the actor's exact response and provider telemetry."""
        if condition != "typed_interaction":
            raise ValueError("typed actor requires the typed_interaction condition")
        messages = self.messages_for(scenario)
        reply = self.provider.complete(messages)
        return AdapterOutput(
            events=(
                BenchmarkEvent(
                    EventKind.MESSAGE, {"text": reply.text}, source=self.provider.provider_id
                ),
            ),
            transcript=(*messages, {"role": "assistant", "content": reply.text}),
            tokens_input=reply.tokens_input,
            tokens_output=reply.tokens_output,
            elapsed_ms=reply.elapsed_ms,
            provider_metadata=reply.metadata or {},
        )


@dataclass(frozen=True)
class AttuneFormsAdapter:
    """Validate one typed request/response via an explicitly injected host.

    Events attest to adapter calls and validation only, not pixels, human
    identity, consequential authorization, or task execution. A simulator must
    identify itself in response_source. No host is selected implicitly.
    """

    respond: Callable[[FormRequest], FormSubmission]
    response_source: str
    condition: str = field(default="typed_interaction", init=False)
    adapter_id: str = field(default="attune-forms/typed", init=False)
    adapter_version: str = field(default="0.1.0", init=False)

    def run(
        self,
        scenario: ActorScenario,
        actor: Callable[[ActorScenario, str], AdapterOutput],
    ) -> AdapterOutput:
        """Keep invalid/cancelled responses out of accepted benchmark evidence."""
        output = actor(scenario, self.condition)
        events = list(output.events)
        started = time.monotonic()
        try:
            if not self.response_source.strip():
                raise ValueError("response_source must identify the host or simulator")
            if any(e.trust is not EventTrust.ACTOR_ASSERTED for e in events):
                raise ValueError("actor output cannot supply trusted events")
            if output.incomplete:
                return output
            messages = [e for e in events if e.kind is EventKind.MESSAGE]
            if len(messages) != 1:
                raise ValueError("typed actor must return exactly one message")
            envelope = json.loads(messages[0].payload["text"])
            if not isinstance(envelope, dict) or set(envelope) != {"form"}:
                raise ValueError("typed output must contain only a form, never answers")
            form = form_from_dict(envelope["form"])
            if any(q.default is not None or q.inferred_from for q in form.questions):
                raise ValueError("typed pilot forms cannot supply default or inferred answers")
            request = FormRequest(uuid.uuid4().hex, json.dumps(envelope["form"], sort_keys=True))
            events.append(
                BenchmarkEvent(
                    EventKind.CLARIFICATION_REQUEST,
                    {
                        "request_id": request.request_id,
                        "form": envelope["form"],
                        "decision_ids": [q.id for q in form.questions],
                        "display_verified": False,
                    },
                    trust=EventTrust.RUNNER_OBSERVED,
                    source=self.adapter_id,
                )
            )
            submission = self.respond(request)
            if not isinstance(submission, FormSubmission):
                raise ValueError("host must return FormSubmission")
            if submission.request_id != request.request_id:
                raise ValueError("submission belongs to a different or stale request")
            if submission.action not in {"accept", "cancel", "decline"}:
                raise ValueError("invalid submission action")
            if submission.action != "accept":
                if submission.answers is not None:
                    raise ValueError("cancelled or declined submissions cannot contain answers")
                events.append(
                    BenchmarkEvent(
                        EventKind.CANCELLATION,
                        {"request_id": request.request_id, "action": submission.action},
                        trust=EventTrust.RUNNER_OBSERVED,
                        source=self.response_source,
                    )
                )
                return replace(output, events=tuple(events))
            if not isinstance(submission.answers, Mapping):
                raise ValueError("accepted submissions require an answer mapping")
            response = collect_form_response(form, dict(submission.answers), self.adapter_id)
            events.append(
                BenchmarkEvent(
                    EventKind.CLARIFICATION_RESPONSE,
                    {
                        "request_id": request.request_id,
                        "answers": response.responses,
                        "response_id": response.response_id,
                        "validated": True,
                    },
                    trust=EventTrust.RUNNER_OBSERVED,
                    source=self.response_source,
                )
            )
            return replace(
                output,
                events=tuple(events),
                transcript=(
                    *output.transcript,
                    {
                        "role": "user",
                        "content": json.dumps(response.responses, sort_keys=True),
                        "source": self.response_source,
                    },
                ),
                provider_metadata={
                    **output.provider_metadata,
                    "typed_response_elapsed_ms": round((time.monotonic() - started) * 1000),
                },
            )
        except Exception as exc:  # Retain actor text/telemetry on host or validation failures.
            message = f"{type(exc).__name__}: {exc}"
            # Only adapter-originated events may carry trusted provenance.
            safe_events = events[len(output.events) :]
            safe_events.insert(
                0,
                BenchmarkEvent(
                    EventKind.MESSAGE,
                    {
                        "untrusted_actor_events": [
                            {
                                "kind": e.kind.value,
                                "payload": dict(e.payload),
                                "claimed_trust": e.trust.value,
                                "source": e.source,
                            }
                            for e in output.events
                        ]
                    },
                    source="actor",
                ),
            )
            safe_events.append(
                BenchmarkEvent(
                    EventKind.ADAPTER_ERROR,
                    {"message": message},
                    trust=EventTrust.RUNNER_OBSERVED,
                    source=self.adapter_id,
                )
            )
            return replace(output, events=tuple(safe_events), incomplete=True, error=message)
