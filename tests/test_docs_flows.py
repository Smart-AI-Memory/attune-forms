"""Documented FLOWS must execute — the drift catcher for call sequences.

``test_docs_drift.py`` gates the vocabulary: real construct counts, real
tool names, real function names. That is the claim-drift principle
applied to inventory, and it works — nothing in the docs has ever named
a tool that does not exist.

It is structurally blind to the defect that actually shipped. On
2026-09-08 three defects reached ``main`` in one day, each passing a
1,433-test suite at 97% coverage:

- the documented re-ask loop dead-ended on turn 2, discarding the
  user's answer;
- the documented cancellation call was rejected outright, and needed an
  undocumented dummy payload;
- the retry instruction named ``attempt`` where the caller must send
  ``next_attempt``, so the budget never advanced.

Every NAME in those instructions was real. ``cancelled`` was a genuine
schema property; ``attempt`` was a genuine result key. What was wrong
was the SEQUENCE — and no vocabulary gate can see that. Worse, the
tests exercised the working path while the docs described a different
one, so the suite stayed green: one test even passed a dummy payload
alongside a cancellation, proving a workaround rather than the
documented call.

So this module binds each documented sequence to an executable one. A
``<!-- flow: slug -->`` anchor in the skill marks a call sequence a
reader is told to follow; :func:`flow` registers the test that follows
it literally. Neither side can move alone: an anchor with no test and a
test with no anchor both fail. The tests below make the calls the way
the skill says to make them, with no arguments the skill does not
mention.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from pathlib import Path

import pytest

from attune_forms import (
    form_from_dict,
    form_to_markdown,
    markdown_to_answers,
    problems_to_markdown,
)
from attune_forms.mcp_server import (
    handle_collect_response,
    handle_render_form,
    handle_render_widget,
)

_ROOT = Path(__file__).resolve().parent.parent
_SKILL_PATH = _ROOT / "plugin" / "skills" / "forms" / "SKILL.md"
_SKILL = _SKILL_PATH.read_text(encoding="utf-8")

#: An anchor marks a call sequence the skill tells a reader to follow.
_ANCHOR = re.compile(r"<!--\s*flow:\s*([a-z0-9][a-z0-9-]*)\s*-->")

#: Flow slugs with an executable counterpart in this module.
_REGISTERED: dict[str, str] = {}


def flow(slug: str) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Register a test as the executable form of a documented flow."""

    def mark(fn: Callable[..., None]) -> Callable[..., None]:
        if slug in _REGISTERED:
            raise AssertionError(f"flow {slug!r} is registered twice")
        _REGISTERED[slug] = fn.__name__
        return fn

    return mark


def documented_flows() -> set[str]:
    """Every flow anchor in the skill."""
    return set(_ANCHOR.findall(_SKILL))


def render(args):
    return asyncio.run(handle_render_form(args))


def collect(args):
    return asyncio.run(handle_collect_response(args))


FORM = {
    "title": "Scope",
    "description": "What to do next",
    "fields": [
        {
            "id": "approach",
            "type": "single_select",
            "text": "Which approach?",
            "options": ["Verify first", "Ship now"],
        },
        {
            "id": "lanes",
            "type": "multi_select",
            "text": "Which lanes?",
            "options": ["docs", "tests", "build"],
        },
    ],
}

FREE_TEXT_FORM = {
    "title": "Notes",
    "description": "d",
    "fields": [{"id": "note", "type": "text_input", "text": "Anything to add?"}],
}


# --- the gate ------------------------------------------------------------


def test_every_documented_flow_has_an_executable_test():
    """A sequence the skill tells a reader to follow must be executed here.

    This is the half that would have caught 2026-09-08: the retry and
    cancellation sequences were documented and never executed.
    """
    missing = sorted(documented_flows() - set(_REGISTERED))

    assert not missing, (
        f"the skill documents flow(s) {missing} with no executable test. "
        "Add a @flow(slug) test that makes the calls exactly as written, "
        "or remove the anchor if the sequence is no longer documented."
    )


def test_every_flow_test_is_still_documented():
    stale = sorted(set(_REGISTERED) - documented_flows())

    assert not stale, (
        f"flow test(s) {stale} have no anchor in {_SKILL_PATH.name}; the "
        "sequence they pin is no longer documented, so the test is pinning "
        "nothing a reader is told to do."
    )


def test_the_skill_documents_at_least_the_host_question_line():
    # A guard on the guard: an empty anchor set would make both gates
    # above pass vacuously.
    assert len(documented_flows()) >= 5


# --- the flows, executed as written --------------------------------------


@flow("host-question-render")
def test_render_returns_an_admissible_payload_to_send_as_is():
    result = render({"form": FORM})

    assert result["host_question_admissible"] is True
    # "already ordered and headed — send it as-is"
    questions = result["host_question"]["questions"]
    assert [q["question"] for q in questions] == ["Which approach?", "Which lanes?"]
    assert all(q["header"] for q in questions)


@flow("host-question-inadmissible")
def test_an_inadmissible_form_says_what_the_host_cannot_carry():
    result = render({"form": FREE_TEXT_FORM})

    assert result["host_question_admissible"] is False
    assert result["host_question_problems"]
    assert "host_question" not in result


@flow("host-question-collect")
def test_the_raw_reply_goes_straight_back_as_host_response():
    # "Send the host's raw reply straight back ... as host_response" —
    # display labels, not option ids; the caller maps nothing.
    result = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "Ship now", "Which lanes?": "docs,tests"},
        }
    )

    assert result["outcome"] == "accepted"
    assert result["responses"] == {"approach": "Ship now", "lanes": ["docs", "tests"]}


@flow("host-question-retry")
def test_the_documented_retry_sends_next_attempt_and_the_carry():
    """Turn 2, exactly as the skill instructs.

    The instruction is specific about which fields go back, because the
    first version of it named the wrong one and the exchange dead-ended.
    """
    first = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "[No preference]", "Which lanes?": "docs"},
        }
    )
    assert "next_host_question" in first

    second = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "Verify first"},
            "attempt": first["next_attempt"],
            "answered_so_far": first["answered_so_far"],
        }
    )

    assert second["outcome"] == "accepted"
    # The turn-1 answer survives; only the offending question was re-asked.
    assert second["responses"] == {"approach": "Verify first", "lanes": ["docs"]}
    # The field the skill names must be the one that ADVANCES the budget.
    # Naming `attempt` instead would leave it at 1 forever, and the
    # bounded re-ask would not be bounded.
    assert first["next_attempt"] == first["attempt"] + 1


@flow("host-question-cancel")
def test_a_dismissed_prompt_is_reported_with_cancelled_alone():
    # "send `cancelled: true` rather than an empty or oddly-shaped reply"
    # — and nothing else, which is what the docs describe.
    result = collect({"form": FORM, "cancelled": True})

    assert result["outcome"] == "cancelled"


@flow("widget-postback")
def test_the_widget_postback_validates_through_collect_response():
    rendered = asyncio.run(handle_render_widget({"form": FORM}))
    assert rendered["success"]

    validated = collect({"form": FORM, "answers": {"approach": "Ship now", "lanes": ["build"]}})

    assert validated["success"]
    assert validated["responses"]["lanes"] == ["build"]


@flow("markdown-roundtrip")
def test_the_text_only_path_parses_its_own_skeleton():
    # "run markdown_to_answers(form, reply) ... returns (answers, problems)"
    form = form_from_dict(FORM)
    markdown = form_to_markdown(form)

    answers, problems = markdown_to_answers(form, markdown)

    assert isinstance(answers, dict)
    assert isinstance(problems, list)


@flow("reask-only-offending-fields")
def test_problems_re_ask_exactly_the_offending_fields():
    # "On problems, relay problems_to_markdown(form, problems) — it
    # re-renders exactly the offending fields, never the whole form."
    form = form_from_dict(FORM)
    result = collect({"form": FORM, "answers": {"lanes": ["docs"]}})
    assert result["success"] is False

    re_ask = problems_to_markdown(form, result["problems"])

    assert "Which approach?" in re_ask
    assert "Which lanes?" not in re_ask


# --- the mirror carries the same anchors ---------------------------------


def test_the_agents_mirror_documents_the_same_flows():
    mirror = (_ROOT / ".agents" / "skills" / "forms" / "SKILL.md").read_text(encoding="utf-8")

    assert set(_ANCHOR.findall(mirror)) == documented_flows()


@pytest.mark.parametrize("slug", sorted(_REGISTERED))
def test_each_flow_anchor_appears_exactly_once(slug):
    # Two anchors with one slug would let a second, unexercised sequence
    # ride along on the first one's test.
    assert _SKILL.count(f"flow: {slug} ") + _SKILL.count(f"flow: {slug}-->") <= 1
