"""Tests for the v7 confirm construct (communication grammar).

A CONFIRM is an action preview with an explicit ``consequences`` list
and a two-way approve/abort gate: exactly two author-nameable options
(default ["Approve", "Abort"]), no ``default`` and no ``recommended``
ever (spec D2 — a pre-selected approval defeats the gate), and the
answer validates as a single-select. Spec:
attune-ai docs/specs/confirm-construct/ (roundtable
q-forms-grammar-expansion-001 → chair "spec next"
resp-20260814-211025; intake resp-20260814-212130).
"""

from __future__ import annotations

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_markdown,
    form_to_widget_html,
    needs_widget,
)
from attune_forms.bridge import form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import FormQuestion, QuestionType


def _confirm(**override) -> dict:
    """Build a one-field confirm form dict, overriding the field."""
    field = {
        "id": "release_gate",
        "text": "Publish attune-forms 0.5.0 to PyPI?",
        "type": "confirm",
        "consequences": [
            {"label": "Tag v0.5.0 is pushed", "severity": "irreversible"},
            {
                "label": "Package publishes to PyPI",
                "severity": "high",
                "detail": "trusted publishing",
            },
            {"label": "CHANGELOG section promotes"},
        ],
    }
    field.update(override)
    return {"title": "Release gate", "fields": [field]}


class TestConfirmModel:
    def test_questiontype_has_confirm(self) -> None:
        assert QuestionType.CONFIRM.value == "confirm"

    def test_formquestion_consequences_default_none(self) -> None:
        q = FormQuestion(id="a", text="t", type=QuestionType.CONFIRM)
        assert q.consequences is None


class TestConfirmFormFromDict:
    def test_builds_with_defaulted_options(self) -> None:
        form = form_from_dict(_confirm())
        q = form.questions[0]
        assert q.type == QuestionType.CONFIRM
        assert q.options == ["Approve", "Abort"]
        assert len(q.consequences) == 3

    def test_author_named_pair_kept(self) -> None:
        form = form_from_dict(_confirm(options=["Ship it", "Hold"]))
        assert form.questions[0].options == ["Ship it", "Hold"]

    def test_exactly_two_options_enforced(self) -> None:
        for bad in (["Only"], ["a", "b", "c"]):
            with pytest.raises(FormValidationError, match="exactly 2 options"):
                form_from_dict(_confirm(options=bad))

    def test_requires_consequences(self) -> None:
        with pytest.raises(FormValidationError, match="requires 'consequences'"):
            form_from_dict(_confirm(consequences=None))

    def test_consequences_must_be_nonempty_dicts(self) -> None:
        for bad in ([], ["just a string"], "nope"):
            with pytest.raises(FormValidationError, match="non-empty list of dicts"):
                form_from_dict(_confirm(consequences=bad))

    def test_consequence_items_need_labels(self) -> None:
        with pytest.raises(FormValidationError, match="needs a 'label' string"):
            form_from_dict(_confirm(consequences=[{"severity": "high"}]))

    def test_consequence_extras_must_be_strings(self) -> None:
        with pytest.raises(FormValidationError, match="'severity' must be a string"):
            form_from_dict(_confirm(consequences=[{"label": "x", "severity": 3}]))

    def test_d2_default_rejected(self) -> None:
        # A pre-selected approval defeats the gate (spec D2).
        with pytest.raises(FormValidationError, match="'default' is not permitted on confirm"):
            form_from_dict(_confirm(default="Approve"))

    def test_d2_recommended_rejected(self) -> None:
        with pytest.raises(FormValidationError, match="'recommended' is not permitted on confirm"):
            form_from_dict(_confirm(recommended="Approve"))

    def test_consequences_invalid_on_other_types(self) -> None:
        with pytest.raises(FormValidationError, match="only valid on confirm"):
            form_from_dict(_confirm(type="decision", options=["a", "b"]))


class TestConfirmAnswer:
    def test_collect_accepts_either_option(self) -> None:
        form = form_from_dict(_confirm())
        assert (
            collect_form_response(form, {"release_gate": "Approve"}).responses["release_gate"]
            == "Approve"
        )
        assert (
            collect_form_response(form, {"release_gate": "Abort"}).responses["release_gate"]
            == "Abort"
        )

    def test_collect_rejects_out_of_option(self) -> None:
        form = form_from_dict(_confirm())
        with pytest.raises(FormValidationError, match="not in options"):
            collect_form_response(form, {"release_gate": "maybe"})

    def test_missing_required_answer_named(self) -> None:
        # No default exists by construction, so an empty submit must name
        # the field — approval can never happen by omission.
        form = form_from_dict(_confirm())
        with pytest.raises(FormValidationError, match="'release_gate' is required"):
            collect_form_response(form, {})

    def test_routes_to_widget(self) -> None:
        assert needs_widget(form_from_dict(_confirm())) is True


class TestConfirmSurfaces:
    def test_widget_renders_preview_and_unchecked_gate(self) -> None:
        html = form_to_widget_html(form_from_dict(_confirm()))
        assert 'class="ae-gate"' in html
        assert "If approved:" in html
        assert 'class="ae-gate-tag"' in html  # severity badge
        assert 'data-ftype="confirm"' in html
        assert 'data-collect="checked-one"' in html
        # Nothing pre-selected: no control carries the checked ATTRIBUTE
        # (always space-prefixed; data-collect="checked-one" is not a hit).
        assert " checked" not in html.split("<script>")[0]

    def test_consequence_text_is_escaped(self) -> None:
        html = form_to_widget_html(
            form_from_dict(_confirm(consequences=[{"label": "<img src=x>", "severity": "<b>"}]))
        )
        assert "<img" not in html
        assert "<b>" not in html

    def test_ask_fallback_is_two_option_select_with_receipt(self) -> None:
        form = form_from_dict(_confirm())
        payload = form_to_askuserquestion(form)[0][0]
        assert payload["type"] == "single_select"
        assert payload["options"] == ["Approve", "Abort"]
        assert payload["default"] is None
        assert payload["help_text"].startswith("Will: ")
        assert "Tag v0.5.0 is pushed (irreversible)" in payload["help_text"]
        assert "trusted publishing" in payload["help_text"]

    def test_elicitation_schema_is_two_value_enum_no_default(self) -> None:
        schema = form_to_elicitation_schema(form_from_dict(_confirm()))
        prop = schema["properties"]["release_gate"]
        assert prop["type"] == "string"
        assert prop["enum"] == ["Approve", "Abort"]
        assert "default" not in prop
        assert "Will: " in prop["description"]

    def test_markdown_renders_preview_and_null_skeleton(self) -> None:
        import json

        form = form_from_dict(_confirm())
        md = form_to_markdown(form)
        assert "If approved:" in md
        assert "- Tag v0.5.0 is pushed `irreversible`" in md
        assert "Answer one of: **Approve** / **Abort**" in md
        skeleton = json.loads(md.split("```json")[1].split("```")[0])
        assert skeleton["answers"]["release_gate"] is None


class TestConfirmationPass2:
    """Collect-path bypass (checkpoint-2 promoted item, 2026-08-20):
    the no-`default` rule for the D2 constructs was enforced ONLY
    definition-side in `form_from_dict`. A FormQuestion built DIRECTLY
    (dataclass constructor) with a `default` slipped past it, and
    `collect_form_response({})` then auto-injected the default — so an
    UNANSWERED confirm gate collected as *approved* with no user act,
    the exact thing the two-way gate exists to prevent. The guard now
    lives on the collect/inject path too, where it can't be bypassed."""

    def test_directly_built_confirm_with_default_rejected_at_collect(self) -> None:
        from attune_forms.models import FormSchema

        form = FormSchema(
            title="Release gate",
            description="",
            questions=[
                FormQuestion(
                    id="gate",
                    type=QuestionType.CONFIRM,
                    text="Approve?",
                    options=["Approve", "Abort"],
                    consequences=[{"label": "irreversible"}],
                    default="Approve",
                )
            ],
        )
        # An unanswered gate must NOT silently collect the default.
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(form, {})
        (problem,) = exc.value.problems
        assert "'default' is not permitted on confirm" in problem
        assert "D2: no pre-selected approval" in problem
        assert "'gate'" in problem

    def test_directly_built_ranking_with_default_rejected_at_collect(self) -> None:
        from attune_forms.models import FormSchema

        form = FormSchema(
            title="Order",
            description="",
            questions=[
                FormQuestion(
                    id="rk",
                    type=QuestionType.RANKING,
                    text="Order",
                    options=["A", "B", "C"],
                    default=["A", "B", "C"],
                )
            ],
        )
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(form, {})
        (problem,) = exc.value.problems
        assert "'default' is not permitted on ranking" in problem
        assert "a proposed order is 'suggested'" in problem

    def test_directly_built_assumption_review_with_default_rejected_at_collect(self) -> None:
        from attune_forms.models import FormSchema

        form = FormSchema(
            title="Review",
            description="",
            questions=[
                FormQuestion(
                    id="ar",
                    type=QuestionType.ASSUMPTION_REVIEW,
                    text="Review the assumptions",
                    assumptions=[{"label": "x"}],
                    # A validly-SHAPED default mapping — would otherwise
                    # inject a pre-marked ruling with no user act.
                    default={"x": "accept"},
                )
            ],
        )
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(form, {})
        assert any(
            "'default' is not permitted on assumption_review" in p
            and "a pre-marked ruling is 'suggested'" in p
            for p in exc.value.problems
        )
