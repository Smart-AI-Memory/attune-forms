"""Host-question consuming adapter (AF-2 Task 2).

The outbound half is covered in ``test_host_question.py``. This file
covers the return path: a raw host response correlates back to typed
answers through the retained bindings alone, every unmappable response
is a named problem rather than a partial answer, and the profile's
re-ask budget is honoured exactly.

The load-bearing case is the round trip against the shipped canonical
fixtures — ``canonical_host_question_response`` builds a raw response
from nothing but the bindings and the declared codec, so decoding it
back to ``canonical_host_question_answers`` proves the bindings are
sufficient in both directions.
"""

from __future__ import annotations

import dataclasses

import pytest

from attune_forms import (
    ASKUSERQUESTION_HOST_QUESTION,
    CLAUDE_ASKUSERQUESTION,
    MultiSelectEncoding,
    canonical_host_question_answers,
    canonical_host_question_form,
    canonical_host_question_response,
    decode_host_question_response,
    form_from_dict,
    form_to_host_question,
    host_question_turn,
)
from attune_forms.bridge import FormValidationError, collect_form_response
from attune_forms.canonical_fixtures import digest

PROFILE = CLAUDE_ASKUSERQUESTION
FACET = ASKUSERQUESTION_HOST_QUESTION


@pytest.fixture
def form():
    return canonical_host_question_form()


@pytest.fixture
def batch(form):
    return form_to_host_question(form, PROFILE)


@pytest.fixture
def raw(batch):
    return canonical_host_question_response(batch, PROFILE)


def _profile(**overrides):
    """The installed profile with its facet overridden."""
    return dataclasses.replace(PROFILE, host_question=dataclasses.replace(FACET, **overrides))


# --- round trip ---------------------------------------------------------


def test_canonical_response_decodes_to_canonical_answers(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, raw)

    assert decoding.ok
    assert dict(decoding.answers) == canonical_host_question_answers()


def test_recommended_suffix_is_stripped_back_to_the_option_id(form, batch, raw):
    # The host returns the emitted label including " (Recommended)"; the
    # binding carries it, so the decoded value is the plain option id.
    assert any(" (Recommended)" in value for value in raw.values())

    decoding = decode_host_question_response(form, batch, PROFILE, raw)

    assert decoding.answers["approach"] == "Verify first"


def test_decoded_answers_validate_against_the_form(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, raw)

    response = collect_form_response(form, dict(decoding.answers))

    assert response.responses == canonical_host_question_answers()


@pytest.mark.parametrize("correlation", ["question_id", "ordinal", "emitted_text"])
def test_every_correlation_mode_round_trips(form, correlation):
    profile = _profile(response_correlation=correlation)
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(form, batch, profile, raw)

    assert decoding.ok, decoding.problems
    assert dict(decoding.answers) == canonical_host_question_answers()


# --- cancellation and the unanswered marker -----------------------------


def test_no_response_is_cancellation_when_the_profile_declares_it(form, batch):
    decoding = decode_host_question_response(form, batch, PROFILE, None)

    assert decoding.cancelled
    assert not decoding.problems
    assert not decoding.ok


def test_no_response_is_a_problem_when_the_profile_cannot_cancel(form):
    profile = _profile(cancellation=False)
    batch = form_to_host_question(form, profile)

    decoding = decode_host_question_response(form, batch, profile, None)

    assert not decoding.cancelled
    assert decoding.problems


def test_unanswered_marker_omits_the_question_rather_than_guessing(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "How deep?": "[No preference]"}
    )

    assert decoding.ok
    assert decoding.unanswered == ("depth",)
    assert "depth" not in decoding.answers


# --- the reserved Other option ------------------------------------------


def test_other_is_recorded_but_never_laundered_into_an_answer(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "How deep?": "Other"}, freeform={"depth": "exhaustive"}
    )

    assert decoding.ok
    assert decoding.other_selected == ("depth",)
    assert decoding.freeform["depth"] == "exhaustive"
    assert "depth" not in decoding.answers


def test_other_without_free_text_is_a_named_problem(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, {**raw, "How deep?": "Other"})

    assert not decoding.ok
    assert any("no free text" in problem for problem in decoding.problems)


def test_other_is_a_problem_when_the_profile_carries_no_free_text(form, raw):
    profile = _profile(freeform="none")
    batch = form_to_host_question(form, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "How deep?": "Other"}, freeform={"depth": "x"}
    )

    assert not decoding.ok
    assert any("no free text" in problem for problem in decoding.problems)


def test_free_text_for_a_question_that_did_not_choose_other_is_a_problem(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, raw, freeform={"depth": "x"})

    assert not decoding.ok
    assert any("did not choose Other" in problem for problem in decoding.problems)


# --- responses that cannot be correlated --------------------------------


def test_unknown_atom_is_named_never_matched_approximately(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, {**raw, "How deep?": "shallow"})

    assert not decoding.ok
    assert any("matches no emitted option" in problem for problem in decoding.problems)
    assert "depth" not in decoding.answers


def test_a_key_matching_no_binding_is_named(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, {**raw, "Bogus?": "x"})

    assert not decoding.ok
    assert any("matches no binding" in problem for problem in decoding.problems)


def test_a_missing_key_is_named_rather_than_treated_as_unanswered(form, batch, raw):
    without = {key: value for key, value in raw.items() if key != "How deep?"}

    decoding = decode_host_question_response(form, batch, PROFILE, without)

    assert not decoding.ok
    assert decoding.unanswered == ()
    assert any("no response under key" in problem for problem in decoding.problems)


def test_keys_colliding_under_the_correlation_normalization_are_named(form, batch, raw):
    # The installed profile casefolds, so two keys differing only in case
    # collide; taking either silently would pick an answer by dict order.
    decoding = decode_host_question_response(form, batch, PROFILE, {**raw, "HOW DEEP?": "quick"})

    assert not decoding.ok
    assert any("repeats the key" in problem for problem in decoding.problems)


def test_a_batch_from_another_profile_is_refused(form, batch):
    other = dataclasses.replace(PROFILE, id="some-other-host")

    decoding = decode_host_question_response(form, batch, other, {})

    assert not decoding.ok
    assert any("rendered for profile" in problem for problem in decoding.problems)


def test_a_profile_without_the_facet_is_a_programming_error(form, batch):
    with pytest.raises(ValueError, match="no host_question facet"):
        decode_host_question_response(form, batch, object(), {})


def test_a_non_mapping_response_is_named(form, batch):
    decoding = decode_host_question_response(form, batch, PROFILE, ["nope"])

    assert not decoding.ok
    assert any("must be a mapping" in problem for problem in decoding.problems)


# --- the multi-select codec ---------------------------------------------


def test_delimited_multi_select_decodes_to_a_list(form, batch, raw):
    assert raw["Which lanes?"] == "docs,tests"

    decoding = decode_host_question_response(form, batch, PROFILE, raw)

    assert decoding.answers["lanes"] == ["docs", "tests"]


def test_list_encoding_decodes_to_a_list(form):
    profile = _profile(multi_select_encoding=MultiSelectEncoding(kind="list"))
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)
    assert raw["Which lanes?"] == ["docs", "tests"]

    decoding = decode_host_question_response(form, batch, profile, raw)

    assert decoding.answers["lanes"] == ["docs", "tests"]


def test_the_wrong_shape_for_the_declared_encoding_is_named(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": ["docs"]}
    )

    assert not decoding.ok
    assert any("declares a delimited string" in problem for problem in decoding.problems)


def test_a_repeated_selection_is_named(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": "docs,docs"}
    )

    assert not decoding.ok
    assert any("same option more than once" in problem for problem in decoding.problems)


def test_declared_normalization_absorbs_whitespace_the_host_adds(form, batch, raw):
    # The profile collapses whitespace, so a host that pads around its
    # delimiter still correlates; the tolerance is the profile's, not a
    # fuzzy match invented by the decoder.
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": "docs, tests"}
    )

    assert decoding.ok, decoding.problems
    assert decoding.answers["lanes"] == ["docs", "tests"]


def test_a_response_that_does_not_re_encode_to_itself_is_refused(form):
    # canonical_reencode is declared: an atom quoted where the codec
    # would not quote it is not a string this host could have produced,
    # so it fails closed rather than decoding to a plausible answer.
    profile = _profile(
        multi_select_encoding=MultiSelectEncoding(
            kind="comma_delimited",
            delimiter=",",
            escaping="json_quote_when_delimiter_or_quote",
            canonical_reencode=True,
            escaping_verified=True,
        )
    )
    batch = form_to_host_question(form, profile)

    decoding = decode_host_question_response(
        form,
        batch,
        profile,
        {**canonical_host_question_response(batch, profile), "Which lanes?": '"docs",tests'},
    )

    assert not decoding.ok
    assert any("re-encode" in problem for problem in decoding.problems)


def test_quoting_the_host_has_not_demonstrated_is_refused(form):
    """A DECLARED but unproven escaping refuses quoted input.

    The installed profile no longer exercises this: the 2026-09-08 trial
    measured that it escapes nothing, so its declaration is "none" and
    verified. The guard still matters for any profile that declares a
    rule before a host has demonstrated it.
    """
    profile = _profile(
        multi_select_encoding=MultiSelectEncoding(
            kind="comma_delimited",
            delimiter=",",
            escaping="json_quote_when_delimiter_or_quote",
            canonical_reencode=True,
        )
    )
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "Which lanes?": '"docs",tests'}
    )

    assert not decoding.ok
    assert any("escaping_verified is false" in problem for problem in decoding.problems)


def test_the_installed_host_joins_bare_so_quotes_are_literal(form, batch, raw):
    # MEASURED: this host escapes nothing, so a quote in the reply is part
    # of a label, not a delimiter — and matches no emitted option here.
    assert FACET.multi_select_encoding.escaping == "none"

    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": '"docs",tests'}
    )

    assert not decoding.ok
    assert any("matches no emitted option" in problem for problem in decoding.problems)


def test_verified_quoting_decodes_a_delimiter_bearing_atom():
    codec = MultiSelectEncoding(
        kind="comma_delimited",
        delimiter=",",
        escaping="json_quote_when_delimiter_or_quote",
        canonical_reencode=True,
        escaping_verified=True,
    )
    profile = _profile(multi_select_encoding=codec)
    form = form_from_dict(
        {
            "title": "T",
            "description": "d",
            "fields": [
                {
                    "id": "lanes",
                    "type": "multi_select",
                    "text": "Which lanes?",
                    "options": ["docs, tests", "build"],
                }
            ],
        }
    )
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile, {"lanes": ["docs, tests", "build"]})
    assert raw["Which lanes?"] == '"docs, tests",build'

    decoding = decode_host_question_response(form, batch, profile, raw)

    assert decoding.ok, decoding.problems
    assert decoding.answers["lanes"] == ["docs, tests", "build"]


# --- validation attribution ---------------------------------------------


def test_validation_problems_name_the_question_at_fault():
    form = form_from_dict(
        {
            "title": "T",
            "description": "d",
            "fields": [
                {"id": "depth", "type": "single_select", "text": "d?", "options": ["a", "b"]}
            ],
        }
    )

    with pytest.raises(FormValidationError) as caught:
        collect_form_response(form, {})

    assert caught.value.fields == ("depth",)
    assert caught.value.fully_attributed


def test_an_unattributable_problem_fails_closed():
    form = form_from_dict(
        {
            "title": "T",
            "description": "d",
            "fields": [
                {"id": "depth", "type": "single_select", "text": "d?", "options": ["a", "b"]}
            ],
        }
    )

    with pytest.raises(FormValidationError) as caught:
        collect_form_response(form, {"depth": "a", "stray": 1})

    assert caught.value.fields == ()
    assert not caught.value.fully_attributed


def test_a_raiser_that_attributes_nothing_keeps_the_old_behaviour():
    error = FormValidationError(["something is wrong"])

    assert error.problems == ["something is wrong"]
    assert error.fields == ()
    assert not error.fully_attributed


# --- the bounded re-ask --------------------------------------------------


def test_a_clean_response_is_accepted_in_one_turn(form, batch, raw):
    turn = host_question_turn(form, batch, PROFILE, raw)

    assert turn.outcome == "accepted"
    assert turn.done
    assert turn.response is not None
    assert turn.response.responses == canonical_host_question_answers()


def test_a_validation_failure_re_asks_only_the_offending_question(form, batch, raw):
    turn = host_question_turn(form, batch, PROFILE, {**raw, "How deep?": "[No preference]"})

    assert turn.outcome == "invalid"
    assert not turn.done
    assert [question.id for question in turn.next_form.questions] == ["depth"]
    assert len(turn.next_batch.answer_bindings) == 1


def test_the_re_ask_completes_the_exchange(form, batch, raw):
    first = host_question_turn(form, batch, PROFILE, {**raw, "How deep?": "[No preference]"})
    second_raw = canonical_host_question_response(first.next_batch, PROFILE, {"depth": "standard"})

    second = host_question_turn(first.next_form, first.next_batch, PROFILE, second_raw, attempt=2)

    assert second.outcome == "accepted"
    assert second.done
    assert second.response.responses == {"depth": "standard"}


def test_the_last_attempt_is_exhausted_rather_than_re_asked(form, batch, raw):
    turn = host_question_turn(
        form, batch, PROFILE, {**raw, "How deep?": "[No preference]"}, attempt=3
    )

    assert turn.outcome == "exhausted"
    assert turn.done
    assert turn.next_batch is None


def test_a_profile_without_feedback_never_re_asks(form, raw):
    profile = _profile(validation_feedback="none")
    batch = form_to_host_question(form, profile)

    turn = host_question_turn(form, batch, profile, {**raw, "How deep?": "[No preference]"})

    assert turn.outcome == "exhausted"
    assert turn.done


def test_a_cancelled_batch_is_terminal(form, batch):
    turn = host_question_turn(form, batch, PROFILE, None)

    assert turn.outcome == "cancelled"
    assert turn.done
    assert turn.response is None


def test_an_undecodable_response_is_terminal_not_retried(form, batch, raw):
    # Re-asking the same batch cannot make an uncorrelatable response
    # correlate, so this must not consume the validation budget.
    turn = host_question_turn(form, batch, PROFILE, {**raw, "Bogus?": "x"})

    assert turn.outcome == "undecodable"
    assert turn.done


def test_attempt_is_one_based(form, batch, raw):
    with pytest.raises(ValueError, match="1-based"):
        host_question_turn(form, batch, PROFILE, raw, attempt=0)


# --- receipts ------------------------------------------------------------


def test_the_receipt_binds_the_facet_it_decoded_against(form, batch, raw):
    turn = host_question_turn(form, batch, PROFILE, raw)

    assert turn.receipt.facet_digest == digest(FACET.serialize())
    assert turn.receipt.profile_id == PROFILE.id
    assert turn.receipt.response_correlation == FACET.response_correlation


def test_a_changed_facet_changes_the_receipt_digest(form, raw):
    profile = _profile(max_validation_attempts=2)
    batch = form_to_host_question(form, profile)

    turn = host_question_turn(form, batch, profile, raw)

    assert turn.receipt.facet_digest != digest(FACET.serialize())


def test_the_receipt_records_the_attempt_budget_and_outcome(form, batch, raw):
    turn = host_question_turn(form, batch, PROFILE, {**raw, "How deep?": "[No preference]"})

    receipt = turn.receipt.serialize()

    assert receipt["outcome"] == "invalid"
    assert receipt["attempt"] == 1
    assert receipt["max_attempts"] == 3
    assert receipt["unanswered"] == ["depth"]
    assert receipt["answered"] == ["approach", "proceed", "lanes"]


def test_the_receipt_serializes_to_json_safe_data(form, batch, raw):
    import json

    turn = host_question_turn(form, batch, PROFILE, raw)

    assert json.loads(json.dumps(turn.receipt.serialize()))["outcome"] == "accepted"


# --- hostile and unusual raw shapes -------------------------------------


def _verified_profile():
    """A profile whose host has demonstrated the declared escaping."""
    return _profile(
        multi_select_encoding=MultiSelectEncoding(
            kind="comma_delimited",
            delimiter=",",
            escaping="json_quote_when_delimiter_or_quote",
            canonical_reencode=False,
            escaping_verified=True,
        )
    )


def test_a_bare_facet_decodes_the_same_as_its_containing_profile(form, raw):
    batch = form_to_host_question(form, FACET)

    decoding = decode_host_question_response(form, batch, FACET, raw)

    assert decoding.ok, decoding.problems
    assert dict(decoding.answers) == canonical_host_question_answers()


def test_unescaped_codec_splits_on_the_bare_delimiter(form):
    profile = _profile(
        multi_select_encoding=MultiSelectEncoding(kind="comma_delimited", delimiter=",")
    )
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(form, batch, profile, raw)

    assert decoding.ok, decoding.problems
    assert decoding.answers["lanes"] == ["docs", "tests"]


def test_an_unterminated_quoted_atom_is_named(form):
    profile = _verified_profile()
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "Which lanes?": '"docs,tests'}
    )

    assert not decoding.ok
    assert any("unparseable quoted atom" in problem for problem in decoding.problems)


def test_a_quoted_atom_not_followed_by_the_delimiter_is_named(form):
    profile = _verified_profile()
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "Which lanes?": '"docs"tests'}
    )

    assert not decoding.ok
    assert any("after a quoted atom" in problem for problem in decoding.problems)


def test_a_non_string_single_answer_is_named(form, batch, raw):
    decoding = decode_host_question_response(form, batch, PROFILE, {**raw, "How deep?": 5})

    assert not decoding.ok
    assert any("expected a single label" in problem for problem in decoding.problems)


def test_a_non_list_under_a_list_encoding_is_named(form):
    profile = _profile(multi_select_encoding=MultiSelectEncoding(kind="list"))
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "Which lanes?": "docs,tests"}
    )

    assert not decoding.ok
    assert any("declares a list encoding" in problem for problem in decoding.problems)


def test_the_unanswered_marker_cannot_be_one_of_several_selections(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": "docs,[No preference]"}
    )

    assert not decoding.ok
    assert any("one of several selections" in problem for problem in decoding.problems)


def test_other_inside_a_multi_select_is_recorded_as_other(form, batch, raw):
    decoding = decode_host_question_response(
        form, batch, PROFILE, {**raw, "Which lanes?": "docs,Other"}, freeform={"lanes": "infra"}
    )

    assert decoding.ok, decoding.problems
    assert decoding.other_selected == ("lanes",)
    assert "lanes" not in decoding.answers


def test_a_batch_correlated_differently_from_the_profile_is_refused(form, batch):
    profile = _profile(response_correlation="ordinal")

    decoding = decode_host_question_response(form, batch, profile, {})

    assert not decoding.ok
    assert any("batch correlates on" in problem for problem in decoding.problems)


def test_a_response_ending_in_a_quoted_atom_decodes(form):
    profile = _verified_profile()
    batch = form_to_host_question(form, profile)
    raw = canonical_host_question_response(batch, profile)

    decoding = decode_host_question_response(
        form, batch, profile, {**raw, "Which lanes?": 'docs,"tests"'}
    )

    assert decoding.ok, decoding.problems
    assert decoding.answers["lanes"] == ["docs", "tests"]
