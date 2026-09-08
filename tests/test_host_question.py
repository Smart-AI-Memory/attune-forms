"""Host-profile structured-question renderer (AF-2).

Every acceptance receipt in the attune-ai host-surface-parity AF-2
handoff has a test here that fails when the property it names is broken:
admissibility agrees with the renderer and never truncates; recommended
options partition first with the suffix as part of the bound atom;
repeated labels across questions are legal while within-question and
reserved-Other collisions are not; duplicate question text falls back
only on emitted-text correlation; the profile serializes every declared
facet; the canonical codec quotes atoms that carry the delimiter.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from attune_forms import (
    ASKUSERQUESTION_HOST_QUESTION,
    CLAUDE_ASKUSERQUESTION,
    PORTABLE_MARKDOWN,
    RECOMMENDED_SUFFIX,
    FormSchema,
    HostQuestionProfile,
    MultiSelectEncoding,
    QuestionType,
    canonical_form,
    canonical_host_question_form,
    canonical_host_question_response,
    form_from_dict,
    form_to_host_question,
    host_question_admissibility,
    installed_profile,
)
from attune_forms.canonical_fixtures import digest

PROFILE = CLAUDE_ASKUSERQUESTION
FACET = ASKUSERQUESTION_HOST_QUESTION


def _form(*fields: dict) -> object:
    return form_from_dict({"title": "T", "description": "d", "fields": list(fields)})


def _select(qid: str = "a", **overrides: object) -> dict:
    base = {"id": qid, "type": "single_select", "text": f"Which {qid}?", "options": ["x", "y"]}
    base.update(overrides)
    return base


def _with_facet(**changes: object):
    """The installed profile with a modified facet (and matching capabilities)."""
    facet = dataclasses.replace(FACET, **changes)
    caps = dataclasses.replace(PROFILE.capabilities, multi_select=facet.multi_select)
    return dataclasses.replace(PROFILE, id="test-profile", capabilities=caps, host_question=facet)


# --- the installed profile ---------------------------------------------------


def test_askuserquestion_profile_is_installed_with_its_observed_facet() -> None:
    installed = installed_profile("claude-askuserquestion")
    assert installed is PROFILE
    assert installed.host_question is FACET
    assert (FACET.max_questions, FACET.min_options, FACET.max_options) == (4, 2, 4)
    assert FACET.max_header_chars == 12
    assert FACET.multi_select and FACET.cancellation
    assert FACET.freeform == "separate_response" and FACET.other_label == "Other"
    assert FACET.response_correlation == "emitted_text"
    assert FACET.unanswered_marker == "[No preference]"
    # MEASURED 2026-09-08: this host escapes nothing — a delimiter-bearing
    # label came back joined with a bare comma. "none" is verified as the
    # declaration, not merely unproven.
    assert FACET.multi_select_encoding == MultiSelectEncoding(
        kind="comma_delimited",
        delimiter=",",
        atom="emitted_label",
        escaping="none",
        canonical_reencode=True,
        escaping_verified=True,
    )
    assert FACET.inadmissible_types == ("ranking",)
    assert FACET.max_validation_attempts > 0 and FACET.response_deadline_seconds > 0
    assert installed_profile("nobody") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"max_questions": 0},
        {"max_options": 1, "min_options": 2},
        {"max_header_chars": -1},
        {"max_validation_attempts": 0},
        {"response_deadline_seconds": 0},
        {"freeform": "guess"},
        {"validation_feedback": "shout"},
        {"question_text_normalization": "lowercase"},
        {"response_correlation": "vibes"},
        {"other_label": " "},
        {"recommended_suffix": ""},
        {"inadmissible_types": ("hologram",)},
    ],
)
def test_facet_rejects_unknown_vocabularies_and_bad_bounds(changes: dict) -> None:
    with pytest.raises(ValueError):
        dataclasses.replace(FACET, **changes)


def test_facet_rejects_a_non_encoding_and_encoding_rejects_inconsistency() -> None:
    with pytest.raises(TypeError):
        dataclasses.replace(FACET, multi_select_encoding="csv")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        MultiSelectEncoding(kind="comma_delimited", delimiter=None)
    with pytest.raises(ValueError):
        MultiSelectEncoding(kind="list", delimiter=",")
    with pytest.raises(ValueError):
        MultiSelectEncoding(kind="list", escaping="json_quote_when_delimiter_or_quote")
    with pytest.raises(ValueError):
        MultiSelectEncoding(atom="tokens")


def test_encoding_quotes_atoms_that_carry_the_delimiter_or_a_quote() -> None:
    quoting = MultiSelectEncoding(
        kind="comma_delimited",
        delimiter=",",
        escaping="json_quote_when_delimiter_or_quote",
        canonical_reencode=True,
    )
    encoded = quoting.encode(["a,b", 'say "hi"', "plain"])
    assert encoded == '"a,b","say \\"hi\\"",plain'
    first_atom, end = json.JSONDecoder().raw_decode(encoded)
    assert first_atom == "a,b" and encoded[end] == ","
    assert MultiSelectEncoding().encode(["a", "b"]) == ["a", "b"]
    bare = MultiSelectEncoding(kind="comma_delimited", delimiter="; ")
    assert bare.encode(["a", "b"]) == "a; b"
    # The INSTALLED host does none of this: it joins bare, which is why
    # delimiter-bearing labels can never be carried on it.
    assert FACET.multi_select_encoding.encode(["a", "b"]) == "a,b"


def test_profile_serialization_binds_every_facet_field() -> None:
    base = digest(FACET.serialize())
    keys = set(FACET.serialize())
    assert {
        "cancellation",
        "freeform",
        "validation_feedback",
        "max_validation_attempts",
        "response_deadline_seconds",
        "multi_select_encoding",
        "response_correlation",
        "unanswered_marker",
    } <= keys
    variants: dict[str, object] = {
        "max_questions": 3,
        "max_options": 3,
        "min_options": 1,
        "max_header_chars": 8,
        "max_option_label_chars": None,
        "multi_select": False,
        "other_label": "Else",
        "freeform": "none",
        "cancellation": False,
        "validation_feedback": "none",
        "max_validation_attempts": 4,
        "response_deadline_seconds": 60,
        "question_text_normalization": "exact",
        "option_label_normalization": "exact",
        "response_correlation": "ordinal",
        "multi_select_encoding": MultiSelectEncoding(),
        "recommended_suffix": " (Rec)",
        "unanswered_marker": None,
        "inadmissible_types": ("triage",),
    }
    assert set(variants) == {f.name for f in dataclasses.fields(HostQuestionProfile)}
    for name, value in variants.items():
        changed = dataclasses.replace(FACET, **{name: value})
        assert digest(changed.serialize()) != base, name


# --- admissibility and the renderer agree -------------------------------------


def test_admissibility_agrees_with_the_renderer_and_never_truncates() -> None:
    form = canonical_host_question_form()
    verdict = host_question_admissibility(form, PROFILE)
    assert verdict.admissible and verdict.problems == () and verdict.question_count == 4
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    assert len(batch.payload["questions"]) == 4 == len(batch.answer_bindings)
    assert batch.profile_id == "claude-askuserquestion"
    assert batch.response_correlation == "emitted_text"

    five = _form(_select(options=["a", "b", "c", "d", "e"]))
    verdict = host_question_admissibility(five, PROFILE)
    assert not verdict.admissible
    assert any("5 options exceed the profile maximum 4" in p for p in verdict.problems)
    assert form_to_host_question(five, PROFILE) is None


def test_the_same_form_is_inadmissible_for_a_single_question_profile() -> None:
    form = canonical_host_question_form()
    single = _with_facet(max_questions=1)
    assert host_question_admissibility(form, PROFILE).admissible
    verdict = host_question_admissibility(form, single)
    assert not verdict.admissible
    assert any("4 emitted questions exceed the profile maximum 1" in p for p in verdict.problems)
    assert form_to_host_question(form, single) is None


def test_recommended_option_partitions_first_with_the_suffix_bound_as_the_atom() -> None:
    form = _form(
        {
            "id": "approach",
            "type": "decision",
            "text": "Which approach?",
            "options": ["Build first", "Verify first", "Skip"],
            "recommended": "Verify first",
            "rationale": "receipts",
            "option_notes": {"Verify first": "cheap", "Skip": "fast"},
        }
    )
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    (question,) = batch.payload["questions"]
    assert [o["label"] for o in question["options"]] == [
        f"Verify first{RECOMMENDED_SUFFIX}",
        "Build first",
        "Skip",
    ]
    assert [o["description"] for o in question["options"]] == ["cheap", "", "fast"]
    (binding,) = batch.answer_bindings
    assert binding.option_bindings[0] == (
        f"Verify first{RECOMMENDED_SUFFIX}",
        f"Verify first{RECOMMENDED_SUFFIX}",
        "Verify first",
    )
    assert binding.option_bindings[1:] == (
        ("Build first", "Build first", "Build first"),
        ("Skip", "Skip", "Skip"),
    )
    assert binding.question_id == "approach" and binding.ordinal == 1
    assert binding.emitted_text == "Which approach?" == question["question"]


def test_a_plain_select_default_is_not_a_recommendation() -> None:
    batch = form_to_host_question(_form(_select(default="y")), PROFILE)
    assert batch is not None
    assert [o["label"] for o in batch.payload["questions"][0]["options"]] == ["x", "y"]


def test_multi_select_keeps_option_order_and_sets_the_flag() -> None:
    form = _form({"id": "m", "type": "multi_select", "text": "Which?", "options": ["c", "a", "b"]})
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    (question,) = batch.payload["questions"]
    assert question["multiSelect"] is True
    assert [o["label"] for o in question["options"]] == ["c", "a", "b"]
    single_only = _with_facet(multi_select=False)
    verdict = host_question_admissibility(form, single_only)
    assert not verdict.admissible
    assert any("no multi-select control" in p for p in verdict.problems)


def test_repeated_yes_no_labels_across_questions_are_legal() -> None:
    form = _form(
        {"id": "p", "type": "boolean", "text": "Proceed?"},
        {"id": "q", "type": "boolean", "text": "Publish?"},
    )
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    assert [b.option_bindings for b in batch.answer_bindings] == [
        (("Yes", "Yes", "Yes"), ("No", "No", "No")),
        (("Yes", "Yes", "Yes"), ("No", "No", "No")),
    ]
    assert [q["multiSelect"] for q in batch.payload["questions"]] == [False, False]


def test_within_question_collision_after_normalization_is_inadmissible() -> None:
    verdict = host_question_admissibility(_form(_select(options=["Fast", "fast  "])), PROFILE)
    assert not verdict.admissible
    assert any("collide" in p for p in verdict.problems)
    exact = _with_facet(option_label_normalization="exact")
    assert host_question_admissibility(_form(_select(options=["Fast", "fast  "])), exact).admissible


def test_reserved_other_collision_is_inadmissible() -> None:
    verdict = host_question_admissibility(_form(_select(options=["other", "x"])), PROFILE)
    assert not verdict.admissible
    assert any("reserved Other label" in p for p in verdict.problems)


def test_suffixed_label_counts_against_the_label_bound() -> None:
    tight = _with_facet(max_option_label_chars=len("Verify first") + 2)
    form = _form(
        {
            "id": "d",
            "type": "decision",
            "text": "Which?",
            "options": ["Verify first", "Build"],
            "recommended": "Verify first",
        }
    )
    verdict = host_question_admissibility(form, tight)
    assert not verdict.admissible
    assert any("exceeds" in p for p in verdict.problems)
    assert host_question_admissibility(form, PROFILE).admissible


def test_duplicate_question_text_falls_back_only_on_emitted_text_correlation() -> None:
    form = _form(_select("a", text="Which one?"), _select("b", text="which  ONE?"))
    verdict = host_question_admissibility(form, PROFILE)
    assert not verdict.admissible
    assert any("cannot be correlated by emitted text" in p for p in verdict.problems)
    assert form_to_host_question(form, PROFILE) is None

    by_id = _with_facet(response_correlation="question_id")
    batch = form_to_host_question(form, by_id)
    assert batch is not None
    assert [q["question_id"] for q in batch.payload["questions"]] == ["a", "b"]
    assert batch.response_correlation == "question_id"

    by_ordinal = _with_facet(response_correlation="ordinal")
    batch = form_to_host_question(form, by_ordinal)
    assert batch is not None
    assert all("question_id" not in q for q in batch.payload["questions"])
    assert [b.ordinal for b in batch.answer_bindings] == [1, 2]


def test_header_derives_from_the_id_and_falls_back_to_the_ordinal_never_truncating() -> None:
    form = _form(_select("approach"), _select("pending_triage_items"))
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    assert [q["header"] for q in batch.payload["questions"]] == ["Approach", "Q2"]
    unbounded = _with_facet(max_header_chars=None)
    batch = form_to_host_question(form, unbounded)
    assert batch is not None
    assert batch.payload["questions"][1]["header"] == "Pending triage items"


@pytest.mark.parametrize("control", ["text_input", "textarea", "number", "date"])
def test_free_text_and_typed_controls_have_no_host_question_control(control: str) -> None:
    verdict = host_question_admissibility(_form({"id": "f", "type": control, "text": "?"}), PROFILE)
    assert not verdict.admissible
    assert any(f"{control} has no host question control" in p for p in verdict.problems)


def test_ranking_is_inadmissible_by_profile_declaration_not_by_shape() -> None:
    form = _form(
        {"id": "r", "type": "ranking", "text": "Order these", "options": ["a", "b", "c", "d"]}
    )
    verdict = host_question_admissibility(form, PROFILE)
    assert not verdict.admissible
    assert any("ranking is inadmissible on this profile" in p for p in verdict.problems)
    permissive = _with_facet(inadmissible_types=())
    verdict = host_question_admissibility(form, permissive)
    assert verdict.admissible and verdict.question_count == 4


def test_triage_expands_per_item_and_the_question_cap_applies() -> None:
    def triage(n: int) -> dict:
        return {
            "id": "t",
            "type": "triage",
            "text": "Rule each",
            "triage_items": [{"id": f"i{k}", "label": f"Item {k}"} for k in range(n)],
            "dispositions": ["apply", "defer"],
            "suggested": {"i0": "defer"},
        }

    batch = form_to_host_question(_form(triage(3)), PROFILE)
    assert batch is not None
    assert [b.question_id for b in batch.answer_bindings] == ["t.i0", "t.i1", "t.i2"]
    first = batch.payload["questions"][0]
    assert [o["label"] for o in first["options"]] == [f"defer{RECOMMENDED_SUFFIX}", "apply"]
    assert not host_question_admissibility(_form(triage(5)), PROFILE).admissible


def test_assumption_review_is_inadmissible_because_its_edit_lane_is_free_text() -> None:
    form = _form(
        {
            "id": "ar",
            "type": "assumption_review",
            "text": "Check these",
            "assumptions": [{"id": "x", "label": "It compiles"}],
        }
    )
    verdict = host_question_admissibility(form, PROFILE)
    assert not verdict.admissible
    assert any("text_input has no host question control" in p for p in verdict.problems)


def test_help_text_and_inference_provenance_fold_into_the_question_text() -> None:
    form = _form(
        _select(help_text="pick one"),
        _select("g", default="x", inferred_from="the last run"),
    )
    batch = form_to_host_question(form, PROFILE)
    assert batch is not None
    texts = [q["question"] for q in batch.payload["questions"]]
    assert texts[0] == "Which a? — pick one"
    assert texts[1].startswith("Which g? — Guessed: x — the last run")
    assert [b.emitted_text for b in batch.answer_bindings] == texts


def test_profile_change_between_renders_changes_admissibility_not_the_form() -> None:
    form = _form(_select(options=["a", "b", "c"]))
    assert form_to_host_question(form, PROFILE) is not None
    narrow = _with_facet(max_options=2)
    assert form_to_host_question(form, narrow) is None
    assert host_question_admissibility(form, PROFILE).admissible
    assert not host_question_admissibility(form, narrow).admissible


def test_profiles_without_a_facet_and_direct_calls_are_defensive() -> None:
    form = canonical_host_question_form()
    verdict = host_question_admissibility(form, PORTABLE_MARKDOWN)
    assert verdict == dataclasses.replace(verdict, admissible=False, question_count=0)
    assert verdict.problems == ("profile has no host-question facet",)
    assert form_to_host_question(form, PORTABLE_MARKDOWN) is None
    assert form_to_host_question(canonical_form(), PROFILE) is None  # has a text_input


def test_a_bare_facet_is_accepted_and_carries_no_profile_id() -> None:
    batch = form_to_host_question(canonical_host_question_form(), FACET)
    assert batch is not None and batch.profile_id == ""


def test_empty_form_is_inadmissible() -> None:
    verdict = host_question_admissibility(FormSchema("T", "d", []), PROFILE)
    assert verdict.problems == ("form has no questions",)
    assert form_to_host_question(FormSchema("T", "d", []), PROFILE) is None


def test_a_token_returning_profile_is_refused_by_this_label_binding_renderer() -> None:
    tokens = _with_facet(multi_select_encoding=MultiSelectEncoding(atom="response_token"))
    verdict = host_question_admissibility(_form(_select()), tokens)
    assert not verdict.admissible
    assert any("binds emitted labels only" in p for p in verdict.problems)


def test_canonical_response_keys_follow_the_declared_correlation() -> None:
    form = canonical_host_question_form()
    by_text = canonical_host_question_response(form_to_host_question(form, PROFILE), PROFILE)
    assert "Which approach?" in by_text
    by_id_profile = _with_facet(response_correlation="question_id")
    by_id = canonical_host_question_response(
        form_to_host_question(form, by_id_profile), by_id_profile
    )
    assert set(by_id) == {"approach", "depth", "proceed", "lanes"}
    ordinal_profile = _with_facet(response_correlation="ordinal")
    by_ordinal = canonical_host_question_response(
        form_to_host_question(form, ordinal_profile), ordinal_profile
    )
    assert set(by_ordinal) == {"1", "2", "3", "4"}
    assert by_ordinal["4"] == by_id["lanes"] == "docs,tests"


def test_batch_is_deterministic_frozen_and_json_safe() -> None:
    form = canonical_host_question_form()
    first, second = form_to_host_question(form, PROFILE), form_to_host_question(form, PROFILE)
    assert first == second
    json.dumps(first.payload)
    json.dumps(dataclasses.asdict(first))
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.profile_id = "x"  # type: ignore[misc]
    assert all(
        isinstance(b.option_bindings, tuple) and len(t) == 3
        for b in first.answer_bindings
        for t in b.option_bindings
    )
    assert QuestionType.RANKING.value in FACET.inadmissible_types


@pytest.mark.parametrize("label", ["[No preference]", "[no   PREFERENCE]"])
def test_unanswered_marker_cannot_be_selected_as_an_option(label: str) -> None:
    form = _form(_select(options=[label, "Yes"]))
    verdict = host_question_admissibility(form, PROFILE)
    assert not verdict.admissible
    assert any("unanswered marker" in problem for problem in verdict.problems)
    assert form_to_host_question(form, PROFILE) is None
    no_marker = _with_facet(unanswered_marker=None)
    assert host_question_admissibility(form, no_marker).admissible


@pytest.mark.parametrize("label", ["a,b", "a, b", 'say "hi"'])
def test_unverified_multiselect_escaping_falls_back_before_rendering(label: str) -> None:
    form = _form(_select(type="multi_select", options=[label, "plain"]))
    declared = MultiSelectEncoding(
        kind="comma_delimited",
        delimiter=",",
        escaping="json_quote_when_delimiter_or_quote",
        canonical_reencode=True,
    )
    unverified = _with_facet(multi_select_encoding=declared)
    assert not host_question_admissibility(form, unverified).admissible
    assert form_to_host_question(form, unverified) is None
    verified = _with_facet(
        multi_select_encoding=dataclasses.replace(declared, escaping_verified=True)
    )
    assert host_question_admissibility(form, verified).admissible
    batch = form_to_host_question(form, verified)
    assert batch.answer_bindings[0].option_bindings[0] == (label, label, label)
    # The INSTALLED profile refuses these forever, and for a different
    # reason: it declares no escaping at all, so verification cannot
    # rescue the label.
    verdict = host_question_admissibility(form, PROFILE)
    assert not verdict.admissible
    assert "escapes nothing" in verdict.problems[0]
    # Scalar single-select and list codecs need no delimiter decoding.
    assert host_question_admissibility(_form(_select(options=[label, "plain"])), PROFILE).admissible
    listed = _with_facet(multi_select_encoding=MultiSelectEncoding())
    assert host_question_admissibility(form, listed).admissible


def test_multiselect_without_escaping_cannot_claim_ambiguous_labels_are_safe() -> None:
    profile = _with_facet(
        multi_select_encoding=MultiSelectEncoding(
            kind="comma_delimited", delimiter=",", escaping_verified=True
        )
    )
    assert not host_question_admissibility(
        _form(_select(type="multi_select", options=["a,b", "c"])), profile
    ).admissible
    changed = dataclasses.replace(
        FACET.multi_select_encoding, escaping="json_quote_when_delimiter_or_quote"
    )
    assert digest(dataclasses.asdict(changed)) != digest(
        dataclasses.asdict(FACET.multi_select_encoding)
    )


def test_header_fallback_must_fit_even_a_one_character_bound() -> None:
    profile = _with_facet(max_header_chars=1)
    form = _form(_select("long_name"))
    verdict = host_question_admissibility(form, profile)
    assert not verdict.admissible
    assert any("header 'Q1' exceeds 1" in p for p in verdict.problems)
    assert form_to_host_question(form, profile) is None
    assert (
        form_to_host_question(_form(_select("a")), profile).payload["questions"][0]["header"] == "A"
    )


def test_batch_payload_is_a_defensive_transport_copy() -> None:
    batch = form_to_host_question(canonical_host_question_form(), PROFILE)
    original = batch.payload
    copy = batch.payload
    copy["questions"][0]["question"] = "changed"
    copy["questions"][0]["options"][0]["label"] = "changed"
    copy["questions"].pop()
    assert batch.payload == original
    assert batch.answer_bindings[0].emitted_text == original["questions"][0]["question"]
    rebuilt = type(batch)(
        original, batch.answer_bindings, batch.profile_id, batch.response_correlation
    )
    original["questions"].clear()
    assert rebuilt == batch


def test_escaping_verification_requires_a_boolean() -> None:
    with pytest.raises(ValueError, match="escaping_verified must be a boolean"):
        MultiSelectEncoding(escaping_verified="false")
