"""The MCP surface reaches the route-active host-question target.

Until now `form.host_question` was registered and ratified but not
reachable: `handle_render_form` rendered through the compatibility-only
projection, so the bindings AF-2 retains had no consumer on the wire.

These tests cover the wiring in both directions — the projection out,
and a raw host reply decoded back through bindings the server re-derives
rather than trusts the host to return. They also pin the parts that must
NOT change: `batches` is still returned (the tool description and the
skill both promise it, and it retires with `form_to_askuserquestion` no
earlier than 0.18.0), and the typed `answers` path is untouched.
"""

from __future__ import annotations

import asyncio

import pytest

from attune_forms import (
    CLAUDE_ASKUSERQUESTION,
    canonical_host_question_response,
    form_from_dict,
    form_to_host_question,
)
from attune_forms.mcp_server import (
    _host_question_profile,
    handle_collect_response,
    handle_render_form,
    tool_definitions,
)

FORM = {
    "title": "Scope",
    "description": "d",
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

#: A form the profile cannot carry: free text has no host control.
INADMISSIBLE = {
    "title": "T",
    "description": "d",
    "fields": [{"id": "note", "type": "text_input", "text": "Notes?"}],
}


def _raw(form_def=FORM, answers=None):
    """The reply the host would send for this form, built from bindings."""
    form = form_from_dict(form_def)
    batch = form_to_host_question(form, CLAUDE_ASKUSERQUESTION)
    return canonical_host_question_response(
        batch, CLAUDE_ASKUSERQUESTION, answers or {"approach": "Verify first", "lanes": ["docs"]}
    )


def render(args):
    """The repo calls these async handlers through asyncio.run."""
    return asyncio.run(handle_render_form(args))


def collect(args):
    return asyncio.run(handle_collect_response(args))


# --- the profile comes from the registry --------------------------------


def test_the_profile_is_read_from_the_route_active_target():
    profile = _host_question_profile()

    assert profile is not None
    assert profile.id == "claude-askuserquestion"


# --- rendering out -------------------------------------------------------


def test_render_returns_the_route_active_projection():
    result = render({"form": FORM})

    assert result["success"]
    assert result["host_question_admissible"] is True
    assert result["profile_id"] == "claude-askuserquestion"
    assert result["response_correlation"] == "emitted_text"
    assert [q["question"] for q in result["host_question"]["questions"]] == [
        "Which approach?",
        "Which lanes?",
    ]


def test_render_still_returns_the_deprecated_batches_key():
    # The tool description and plugin/skills/forms/SKILL.md both promise
    # `batches`. It retires with form_to_askuserquestion, not before.
    result = render({"form": FORM})

    assert "batches" in result
    assert result["batches"][0][0]["question"] == "Which approach?"


def test_an_inadmissible_form_is_named_not_truncated():
    result = render({"form": INADMISSIBLE})

    assert result["success"]
    assert result["host_question_admissible"] is False
    assert result["host_question_problems"]
    assert "host_question" not in result


def test_a_bad_definition_still_fails_before_any_projection():
    result = render({"form": {"title": "t", "fields": [{"id": "a"}]}})

    assert result["success"] is False
    assert result["problems"]


# --- decoding back -------------------------------------------------------


def test_a_raw_host_reply_decodes_to_typed_answers():
    result = collect({"form": FORM, "host_response": _raw()})

    assert result["success"]
    assert result["outcome"] == "accepted"
    assert result["responses"] == {"approach": "Verify first", "lanes": ["docs"]}
    assert result["receipt"]["profile_id"] == "claude-askuserquestion"


def test_an_unmappable_reply_is_named_never_guessed():
    raw = {**_raw(), "Which lanes?": "docs,not-an-option"}

    result = collect({"form": FORM, "host_response": raw})

    assert result["success"] is False
    assert result["outcome"] == "undecodable"
    assert any("matches no emitted option" in p for p in result["problems"])
    assert "responses" not in result


def test_the_unanswered_marker_is_reported_and_re_asked():
    raw = {**_raw(), "Which approach?": "[No preference]"}

    result = collect({"form": FORM, "host_response": raw})

    assert result["outcome"] == "invalid"
    assert result["unanswered"] == ["approach"]
    # A bounded re-ask of just the offending question, plus the attempt
    # the caller sends back with it.
    assert [q["question"] for q in result["next_host_question"]["questions"]] == ["Which approach?"]
    assert result["next_attempt"] == 2


def test_the_re_ask_completes_and_preserves_earlier_answers():
    """The turn-2 test whose absence let a dead-end ship.

    Turn 1 pinned the re-ask payload; nothing followed the documented
    flow to its end. It did not work: the narrowed reply was decoded
    against the FULL form, every question not re-asked read as a missing
    key, and the exchange died `undecodable` with the user's answer
    discarded. `answered_so_far` closes it.
    """
    first = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "[No preference]", "Which lanes?": "docs"},
        }
    )
    assert first["outcome"] == "invalid"

    second = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "Verify first"},
            "attempt": first["next_attempt"],
            "answered_so_far": first["answered_so_far"],
        }
    )

    assert second["outcome"] == "accepted"
    # Both the re-asked answer AND the one accepted on turn 1.
    assert second["responses"] == {"approach": "Verify first", "lanes": ["docs"]}


def test_the_re_ask_without_the_carry_still_names_the_problem():
    # Dropping answered_so_far must not silently succeed on a partial
    # form; it stays a named missing-key problem.
    first = collect(
        {
            "form": FORM,
            "host_response": {"Which approach?": "[No preference]", "Which lanes?": "docs"},
        }
    )

    second = collect(
        {"form": FORM, "host_response": {"Which approach?": "Verify first"}, "attempt": 2}
    )

    assert first["outcome"] == "invalid"
    assert second["outcome"] == "undecodable"
    assert any("no response under key" in p for p in second["problems"])


def test_the_attempt_budget_is_carried_by_the_caller():
    raw = {**_raw(), "Which approach?": "[No preference]"}

    last = collect({"form": FORM, "host_response": raw, "attempt": 3})

    assert last["outcome"] == "exhausted"
    assert "next_host_question" not in last


def test_an_empty_reply_is_named_not_treated_as_cancellation():
    result = collect({"form": FORM, "host_response": {}})

    # An empty mapping is a reply that correlates to nothing, not a
    # cancel. Only an explicit `cancelled` says the user dismissed it.
    assert result["success"] is False
    assert result["outcome"] != "cancelled"
    assert result["problems"]


@pytest.mark.parametrize("bad", ["Verify first", ["Verify first"], 7, True, 1.5])
def test_a_malformed_host_response_is_not_reported_as_a_cancellation(bad):
    """A wrong shape must not be laundered into `outcome: cancelled`.

    It was: a non-dict became None, which the adapter reads as the user
    dismissing the prompt — empty problems, and a receipt asserting a
    cancellation that never happened. stdio is covered by the SDK's
    schema gate, but this handler is a direct import surface (the
    attune-ai mirror), so it holds the contract itself.
    """
    result = collect({"form": FORM, "host_response": bad})

    assert result["success"] is False
    assert result.get("outcome") != "cancelled"
    assert any("must be an object" in p for p in result["problems"])


def test_an_explicit_cancellation_is_recorded_as_one():
    result = collect({"form": FORM, "host_response": {}, "cancelled": True})

    assert result["outcome"] == "cancelled"
    assert result["receipt"]["outcome"] == "cancelled"
    assert "next_host_question" not in result


@pytest.mark.parametrize("bad", ["nope", 3, ["a"]])
def test_a_malformed_carry_is_refused(bad):
    result = collect({"form": FORM, "host_response": _raw(), "answered_so_far": bad})

    assert result["success"] is False
    assert any("answered_so_far" in p for p in result["problems"])


def test_an_inadmissible_form_cannot_decode():
    result = collect({"form": INADMISSIBLE, "host_response": {"Notes?": "x"}})

    assert result["success"] is False
    assert result["action"] == "inadmissible"


# --- the guards ----------------------------------------------------------


def test_both_answer_sources_is_a_named_problem():
    result = collect({"form": FORM, "answers": {}, "host_response": _raw()})

    assert result["success"] is False
    assert any("not both" in p for p in result["problems"])


def test_neither_answer_source_is_a_named_problem():
    result = collect({"form": FORM})

    assert result["success"] is False
    assert any("provide 'answers'" in p for p in result["problems"])


@pytest.mark.parametrize("attempt", [0, -1, "two", 1.5])
def test_a_bad_attempt_is_refused(attempt):
    result = collect({"form": FORM, "host_response": _raw(), "attempt": attempt})

    assert result["success"] is False
    assert any("attempt" in p for p in result["problems"])


# --- what must not have changed -----------------------------------------


def test_the_typed_answers_path_is_untouched():
    result = collect({"form": FORM, "answers": {"approach": "Ship now", "lanes": ["tests"]}})

    assert result["success"]
    assert result["responses"] == {"approach": "Ship now", "lanes": ["tests"]}
    assert "outcome" not in result


def test_typed_answers_still_name_the_offending_field():
    result = collect({"form": FORM, "answers": {"lanes": ["docs"]}})

    assert result["success"] is False
    assert any("approach" in p for p in result["problems"])


def test_the_tool_schema_accepts_both_answer_sources():
    schema = next(
        t.inputSchema for t in tool_definitions() if t.name == "elicitation_collect_response"
    )

    assert "answers" in schema["properties"]
    assert "host_response" in schema["properties"]
    assert "attempt" in schema["properties"]
    # Neither is schema-required: the handler names the one-of rule,
    # because "required" cannot express it here.
    assert "required" not in schema


def test_the_render_tool_still_documents_batches_as_deprecated():
    description = next(
        t.description for t in tool_definitions() if t.name == "elicitation_render_form"
    )

    assert "host_question" in description
    assert "DEPRECATED" in description
