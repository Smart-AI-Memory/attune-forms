"""Tests for the elicitation declarative-form bridge.

Covers:

- form_from_dict: construction, aliases, and every validation problem
- form_to_askuserquestion: ≤4 batching + per-type payload shape
- collect_form_response: valid answers, defaults, and every reject path
- FormValidationError carries the problem list
"""

from __future__ import annotations

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_askuserquestion,
)
from attune_forms.models import QuestionType


def _form_dict(**overrides):
    base = {
        "title": "Intake",
        "description": "test",
        "fields": [
            {"id": "outcome", "text": "Outcome?", "type": "text_input"},
            {
                "id": "approach",
                "text": "Approach?",
                "type": "single_select",
                "options": ["spec", "inline"],
            },
            {
                "id": "concerns",
                "text": "Concerns?",
                "type": "multi_select",
                "options": ["impl", "test", "docs"],
            },
            {"id": "specfirst", "text": "Spec-first?", "type": "boolean"},
        ],
    }
    base.update(overrides)
    return base


# --- form_from_dict ---------------------------------------------------


class TestFormFromDict:
    def test_builds_all_types(self):
        form = form_from_dict(_form_dict())
        assert form.title == "Intake"
        assert [q.id for q in form.questions] == [
            "outcome",
            "approach",
            "concerns",
            "specfirst",
        ]
        assert form.questions[2].type == QuestionType.MULTI_SELECT

    def test_label_and_questions_aliases(self):
        data = {
            "title": "T",
            "questions": [{"id": "a", "label": "A?", "type": "text_input"}],
        }
        form = form_from_dict(data)
        assert form.questions[0].text == "A?"

    def test_optional_attrs_passthrough(self):
        data = {
            "title": "T",
            "fields": [
                {
                    "id": "a",
                    "text": "A?",
                    "type": "text_input",
                    "default": "x",
                    "help_text": "h",
                    "required": False,
                }
            ],
        }
        q = form_from_dict(data).questions[0]
        assert q.default == "x" and q.help_text == "h" and q.required is False

    def test_path_picker_metadata_passthrough(self):
        data = {
            "title": "T",
            "fields": [
                {
                    "id": "scope",
                    "text": "Scope?",
                    "type": "text_input",
                    "path_kind": "either",
                    "path_options": ["src/a.py", "tests"],
                }
            ],
        }
        q = form_from_dict(data).questions[0]
        assert q.path_kind == "either"
        assert q.path_options == ["src/a.py", "tests"]

    @pytest.mark.parametrize("kind", ["filesystem", "", 1])
    def test_rejects_invalid_path_kind(self, kind):
        data = {
            "title": "T",
            "fields": [{"id": "scope", "text": "Scope?", "type": "text_input", "path_kind": kind}],
        }
        with pytest.raises(FormValidationError, match="path_kind"):
            form_from_dict(data)

    def test_not_a_mapping(self):
        with pytest.raises(FormValidationError, match="mapping"):
            form_from_dict(["nope"])  # type: ignore[arg-type]

    def test_missing_title(self):
        with pytest.raises(FormValidationError, match="title"):
            form_from_dict(_form_dict(title=""))

    def test_empty_fields(self):
        with pytest.raises(FormValidationError, match="non-empty 'fields'"):
            form_from_dict({"title": "T", "fields": []})

    def test_field_not_mapping(self):
        with pytest.raises(FormValidationError, match=r"field\[0\] must be a mapping"):
            form_from_dict({"title": "T", "fields": ["x"]})

    def test_missing_id_and_text(self):
        with pytest.raises(FormValidationError) as exc:
            form_from_dict({"title": "T", "fields": [{"type": "text_input"}]})
        assert any("'id'" in p for p in exc.value.problems)
        assert any("'text'" in p for p in exc.value.problems)

    def test_duplicate_id(self):
        data = {
            "title": "T",
            "fields": [
                {"id": "a", "text": "A?", "type": "text_input"},
                {"id": "a", "text": "B?", "type": "text_input"},
            ],
        }
        with pytest.raises(FormValidationError, match="duplicate id"):
            form_from_dict(data)

    def test_invalid_type(self):
        with pytest.raises(FormValidationError, match="invalid type"):
            form_from_dict({"title": "T", "fields": [{"id": "a", "text": "A?", "type": "slider"}]})

    def test_select_requires_options(self):
        with pytest.raises(FormValidationError, match="requires non-empty 'options'"):
            form_from_dict(
                {"title": "T", "fields": [{"id": "a", "text": "A?", "type": "single_select"}]}
            )

    def test_options_must_be_list_of_strings(self):
        with pytest.raises(FormValidationError, match="list of strings"):
            form_from_dict(
                {
                    "title": "T",
                    "fields": [
                        {"id": "a", "text": "A?", "type": "single_select", "options": [1, 2]}
                    ],
                }
            )


# --- form_to_askuserquestion ------------------------------------------


class TestFormToAskUserQuestion:
    def test_batches_at_four(self):
        fields = [{"id": f"q{i}", "text": f"Q{i}?", "type": "text_input"} for i in range(9)]
        form = form_from_dict({"title": "T", "fields": fields})
        batches = form_to_askuserquestion(form)
        assert [len(b) for b in batches] == [4, 4, 1]

    def test_payload_shapes_per_type(self):
        form = form_from_dict(_form_dict())
        flat = [q for batch in form_to_askuserquestion(form) for q in batch]
        by_id = {q["question_id"]: q for q in flat}
        assert by_id["concerns"]["type"] == "multi_select"
        assert by_id["approach"]["options"] == ["spec", "inline"]
        # boolean renders as a Yes/No single-select
        assert by_id["specfirst"]["type"] == "single_select"
        assert by_id["specfirst"]["options"] == ["Yes", "No"]

    def test_custom_batch_size(self):
        form = form_from_dict(_form_dict())
        batches = form_to_askuserquestion(form, batch_size=2)
        assert [len(b) for b in batches] == [2, 2]


# --- collect_form_response --------------------------------------------


class TestCollectFormResponse:
    def test_valid_answers(self):
        form = form_from_dict(_form_dict())
        resp = collect_form_response(
            form,
            {
                "outcome": "ship it",
                "approach": "spec",
                "concerns": ["impl", "test"],
                "specfirst": "Yes",
            },
            template_id="t1",
        )
        assert resp.template_id == "t1"
        assert resp.responses["concerns"] == ["impl", "test"]
        assert resp.get("approach") == "spec"

    def test_missing_required_raises(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="'outcome' is required"):
            collect_form_response(form, {"approach": "spec", "concerns": [], "specfirst": "No"})

    def test_optional_missing_uses_default(self):
        data = {
            "title": "T",
            "fields": [
                {
                    "id": "a",
                    "text": "A?",
                    "type": "text_input",
                    "required": False,
                    "default": "fallback",
                }
            ],
        }
        form = form_from_dict(data)
        resp = collect_form_response(form, {})
        assert resp.responses["a"] == "fallback"

    def test_explicit_empty_answer_accepts_the_default(self):
        # Pinned by chair ruling 2026-08-20 (confirmation-pass-1
        # needs-a-look): an explicit "" is the accept-the-default
        # gesture, indistinguishable from an untouched prefill — a
        # surface that needs a clearable field must not prefill it via
        # `default`. Documented in collect_form_response's docstring.
        data = {
            "title": "T",
            "fields": [
                {
                    "id": "a",
                    "text": "A?",
                    "type": "text_input",
                    "required": False,
                    "default": "fallback",
                }
            ],
        }
        resp = collect_form_response(form_from_dict(data), {"a": ""})
        assert resp.responses["a"] == "fallback"

    def test_optional_missing_no_default_omitted(self):
        data = {
            "title": "T",
            "fields": [{"id": "a", "text": "A?", "type": "text_input", "required": False}],
        }
        resp = collect_form_response(form_from_dict(data), {})
        assert "a" not in resp.responses

    def test_multiselect_non_list_rejected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="expects a list"):
            collect_form_response(
                form,
                {"outcome": "x", "approach": "spec", "concerns": "impl", "specfirst": "No"},
            )

    def test_multiselect_out_of_option_rejected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="out-of-option"):
            collect_form_response(
                form,
                {"outcome": "x", "approach": "spec", "concerns": ["nope"], "specfirst": "No"},
            )

    def test_single_select_out_of_option_rejected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="not in options"):
            collect_form_response(
                form,
                {"outcome": "x", "approach": "wat", "concerns": [], "specfirst": "No"},
            )

    def test_boolean_invalid_rejected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="must be 'Yes' or 'No'"):
            collect_form_response(
                form,
                {"outcome": "x", "approach": "spec", "concerns": [], "specfirst": "maybe"},
            )

    def test_text_non_string_rejected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError, match="expects a string"):
            collect_form_response(
                form,
                {"outcome": 123, "approach": "spec", "concerns": [], "specfirst": "No"},
            )

    def test_multiple_problems_collected(self):
        form = form_from_dict(_form_dict())
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(form, {})
        # outcome required + approach required + specfirst required (3 of 4;
        # concerns is multi-select, empty list → required miss too)
        assert len(exc.value.problems) >= 3


def test_validation_error_carries_problems():
    err = FormValidationError(["a", "b"])
    assert err.problems == ["a", "b"]
    assert "a" in str(err) and "b" in str(err)


class TestDefaultValidation:
    """Pinned from the 2026-08-19 pilot review of bridge.py (act-now
    finding): a `default` is a pre-supplied answer, so it passes the
    same per-type validator an answer would — before, form_from_dict
    passed it through unchecked and collect injected it unvalidated,
    so an out-of-vocabulary or wrongly-typed default landed in a
    "validated" FormResponse."""

    def _select(self, **overrides):
        field = {
            "id": "a",
            "text": "Pick",
            "type": "single_select",
            "options": ["x", "y"],
            "required": False,
        }
        field.update(overrides)
        return {"title": "T", "fields": [field]}

    def test_out_of_option_default_rejected_at_definition(self):
        with pytest.raises(FormValidationError, match="invalid 'default'"):
            form_from_dict(self._select(default="zzz"))

    def test_wrongly_typed_text_default_rejected_at_definition(self):
        field = {"id": "t", "text": "T", "type": "text_input", "default": 12345}
        with pytest.raises(FormValidationError, match="invalid 'default'"):
            form_from_dict({"title": "T", "fields": [field]})

    def test_valid_default_still_collects_when_unanswered(self):
        form = form_from_dict(self._select(default="y"))
        response = collect_form_response(form, {})
        assert response.responses == {"a": "y"}

    def test_directly_built_invalid_default_rejected_at_collect(self):
        # A form built in Python bypasses form_from_dict's definition
        # check; the collect-time guard still refuses to launder the
        # default into a validated response.
        from attune_forms.models import FormQuestion, FormSchema

        question = FormQuestion(
            id="a",
            text="Pick",
            type=QuestionType.SINGLE_SELECT,
            options=["x", "y"],
            required=False,
            default="zzz",
        )
        form = FormSchema(title="T", description="", questions=[question])
        with pytest.raises(FormValidationError, match="invalid 'default'"):
            collect_form_response(form, {})


class TestUnknownAnswerKeys:
    """Pinned from the 2026-08-19 pilot review of bridge.py: an answer
    key matching no question id was silently ignored — a typo'd key
    against an optional-with-default field invisibly collected the
    default. Unknown keys are now named; keys inside an expanding
    question's dotted namespace stay exempt from the UNKNOWN check (the
    fold owns them) — but coexisting with a canonical answer they are a
    named contradiction (chair ruling, 2026-08-20)."""

    def test_typoed_key_is_named(self):
        field = {
            "id": "approach",
            "text": "Approach",
            "type": "single_select",
            "options": ["spec", "yolo"],
            "required": False,
            "default": "spec",
        }
        form = form_from_dict({"title": "T", "fields": [field]})
        with pytest.raises(FormValidationError, match="unknown answer key 'aproach'"):
            collect_form_response(form, {"aproach": "yolo"})

    def test_dotted_keys_under_present_mapping_are_a_named_contradiction(self):
        # Chair ruling 2026-08-20 (confirmation-pass-1): the old
        # canonical-wins rule silently discarded a contradicting dotted
        # sibling — same silent-drop class as #39/#40. Mixed shapes are
        # now a named problem, not an arbitrary winner.
        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {
                        "id": "board",
                        "text": "Rule items",
                        "type": "triage",
                        "triage_items": [{"label": "One"}, {"label": "Two"}],
                        "dispositions": ["keep", "drop"],
                    }
                ],
            }
        )
        with pytest.raises(
            FormValidationError,
            match=r"'board' is supplied both canonically and as dotted keys \('board.One'\)",
        ):
            collect_form_response(
                form,
                {"board": {"One": "keep", "Two": "drop"}, "board.One": "drop"},
            )


class TestUnknownDefinitionKeys:
    """Pinned from the confirmation-pass-1 chair ruling (2026-08-20):
    the definition-side twin of TestUnknownAnswerKeys. A key the parser
    never reads was silently ignored — a typo'd 'maximun' built a
    bound-less number field that validated any answer clean. Unknown
    top-level and field-level keys are now named definition problems."""

    def test_ledger_repro_typoed_maximum_is_named(self):
        # The exact confirmation-pass repro: the typo'd bound must not
        # silently vanish into an unconstrained field.
        with pytest.raises(
            FormValidationError, match="field\\[0\\] unknown definition key 'maximun'"
        ):
            form_from_dict(
                {
                    "title": "T",
                    "fields": [{"id": "n", "text": "N", "type": "number", "maximun": 10}],
                }
            )

    def test_every_unknown_field_key_is_named(self):
        with pytest.raises(FormValidationError) as exc:
            form_from_dict(
                {
                    "title": "T",
                    "fields": [
                        {
                            "id": "q",
                            "text": "Q",
                            "type": "text_input",
                            "regired": True,
                            "recomended": "x",
                        }
                    ],
                }
            )
        problems = exc.value.problems
        assert "field[0] unknown definition key 'regired'" in problems
        assert "field[0] unknown definition key 'recomended'" in problems

    def test_top_level_unknown_key_is_named(self):
        with pytest.raises(
            FormValidationError, match="form has unknown definition key 'descripton'"
        ):
            form_from_dict(
                {
                    "title": "T",
                    "descripton": "typo",
                    "fields": [{"id": "q", "text": "Q", "type": "text_input"}],
                }
            )

    def test_documented_aliases_stay_accepted(self):
        # 'label' (for 'text') and 'questions' (for 'fields') are
        # documented aliases, not strays.
        form = form_from_dict(
            {
                "title": "T",
                "questions": [{"id": "q", "label": "Q", "type": "text_input"}],
            }
        )
        assert form.questions[0].text == "Q"
