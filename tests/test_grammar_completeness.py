"""Grammar-completeness drift catcher (architecture review F1 pin, 2026-08-20).

Adding a construct touches ~19 places across four surfaces (see
``docs/adding-a-construct.md``). The review ruled that cost the honest
price of four genuinely different translations — no registry or base
class collapses it — so the protection is this completeness table
instead: every :class:`QuestionType` member must carry a row here, and
the rows pin the construct-specific output each surface must emit plus
a wrong-shaped answer the validator must reject. A construct wired
into only three of the four surfaces — or a new type added without
updating these tables — fails red instead of silently falling through
a default branch.

The reference form is the fixture: it is drift-guarded elsewhere
(``test_reference_form``) to hold exactly one field per type.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_elicitation_schema,
    form_to_markdown,
    form_to_widget_html,
)
from attune_forms.models import QuestionType, expansion_items, ranking_slot_count
from attune_forms.reference_form import EXAMPLE_ANSWERS, REFERENCE_FORM

#: How the widget's submit script reads each type's answer out of the
#: DOM. A deliberate second copy of ``widget._COLLECT_MODES``'s
#: *meaning* (not an import): a new type must state its mode here too,
#: which is the point of the table.
_WIDGET_COLLECT_MODES: dict[QuestionType, str] = {
    QuestionType.TEXT_INPUT: "value",
    QuestionType.SINGLE_SELECT: "value",
    QuestionType.MULTI_SELECT: "checked-many",
    QuestionType.BOOLEAN: "value",
    QuestionType.NUMBER: "value",
    QuestionType.DATE: "value",
    QuestionType.TEXTAREA: "value",
    QuestionType.DECISION: "checked-one",
    QuestionType.PUSHBACK: "checked-one",
    QuestionType.PROGRESS: "checked-one",
    QuestionType.DELIBERATION: "checked-one",
    QuestionType.TRIAGE: "rulings",
    QuestionType.CONFIRM: "checked-one",
    QuestionType.RANKING: "ranked",
    QuestionType.ASSUMPTION_REVIEW: "rulings-with-text",
}

#: A canonically WRONG-shaped answer per type — the validator must name
#: the field rather than accept it.
_WRONG_ANSWERS: dict[QuestionType, Any] = {
    QuestionType.TEXT_INPUT: 42,
    QuestionType.SINGLE_SELECT: "not-an-option",
    QuestionType.MULTI_SELECT: "impl",  # scalar where a list is required
    QuestionType.BOOLEAN: "maybe",
    QuestionType.NUMBER: "three",
    QuestionType.DATE: "01/02/2026",
    QuestionType.TEXTAREA: 42,
    QuestionType.DECISION: "not-an-option",
    QuestionType.PUSHBACK: "not-an-option",
    QuestionType.PROGRESS: "not-an-option",
    QuestionType.DELIBERATION: "not-an-option",
    QuestionType.TRIAGE: ["fix now"],  # list where a mapping is required
    QuestionType.CONFIRM: "Maybe",
    QuestionType.RANKING: ["staging", "staging", "canary"],  # repeat
    QuestionType.ASSUMPTION_REVIEW: {"py-floor": "maybe"},
}


def _questions_by_type():
    form = form_from_dict(REFERENCE_FORM)
    return form, {q.type: q for q in form.questions}


class TestTableCompleteness:
    """The gate that makes the other tests a drift catcher: a new
    QuestionType member without a row in BOTH tables fails here."""

    def test_collect_mode_table_covers_every_type(self) -> None:
        assert set(_WIDGET_COLLECT_MODES) == set(QuestionType)

    def test_wrong_answer_table_covers_every_type(self) -> None:
        assert set(_WRONG_ANSWERS) == set(QuestionType)


class TestWidgetSurface:
    def test_every_type_emits_its_pinned_collect_mode(self) -> None:
        form, by_type = _questions_by_type()
        html = form_to_widget_html(form, instance_id="grammar")
        emitted = dict(
            re.findall(r'data-fid="([^"]+)" data-ftype="[^"]+" data-collect="([^"]+)"', html)
        )
        for qtype, question in by_type.items():
            assert emitted.get(question.id) == _WIDGET_COLLECT_MODES[qtype], qtype


class TestAskSurface:
    def test_every_type_expands_to_the_expected_payload_count(self) -> None:
        """TRIAGE expands per item, RANKING per slot, ASSUMPTION_REVIEW
        per item plus its paired text lane; everything else is one
        payload. Sizes derive from the shared helpers every surface is
        required to iterate through."""
        _, by_type = _questions_by_type()
        for qtype, question in by_type.items():
            payloads = question.to_ask_user_formats()
            if qtype is QuestionType.TRIAGE:
                expected = len(expansion_items(question))
            elif qtype is QuestionType.RANKING:
                expected = ranking_slot_count(question)
            elif qtype is QuestionType.ASSUMPTION_REVIEW:
                expected = 2 * len(expansion_items(question))
            else:
                expected = 1
            assert len(payloads) == expected, qtype


class TestElicitationSchemaSurface:
    def test_every_type_projects_a_construct_shaped_property(self) -> None:
        form, by_type = _questions_by_type()
        props = form_to_elicitation_schema(form)["properties"]
        for qtype, question in by_type.items():
            if qtype in (QuestionType.TRIAGE, QuestionType.ASSUMPTION_REVIEW):
                for key, _item in expansion_items(question):
                    assert f"{question.id}.{key}" in props, qtype
                if qtype is QuestionType.ASSUMPTION_REVIEW:
                    for key, _item in expansion_items(question):
                        assert f"{question.id}.{key}.text" in props
            elif qtype is QuestionType.RANKING:
                prop = props[question.id]
                assert prop["type"] == "array"
                assert prop["maxItems"] == ranking_slot_count(question)
            else:
                assert question.id in props, qtype


class TestMarkdownSurface:
    def test_the_skeleton_carries_every_types_answer_shape(self) -> None:
        """The reply skeleton is the markdown surface's contract: item-
        keyed constructs must expose their per-item keys, a ranking its
        ordered list, a multi-select a list — a type falling through to
        a scalar placeholder is the silent-degradation this pins."""
        form, by_type = _questions_by_type()
        md = form_to_markdown(form)
        block = re.findall(r"```json\n(.*?)```", md, re.S)[-1]
        skeleton = json.loads(block)["answers"]
        for qtype, question in by_type.items():
            assert question.id in skeleton, qtype
            value = skeleton[question.id]
            if qtype in (QuestionType.TRIAGE, QuestionType.ASSUMPTION_REVIEW):
                assert isinstance(value, dict), qtype
                assert set(value) == {k for k, _ in expansion_items(question)}
            elif qtype in (QuestionType.RANKING, QuestionType.MULTI_SELECT):
                assert isinstance(value, list), qtype


class TestValidatorSurface:
    @pytest.mark.parametrize("qtype", list(QuestionType), ids=lambda t: t.value)
    def test_a_wrong_shaped_answer_is_rejected_by_name(self, qtype: QuestionType) -> None:
        form, by_type = _questions_by_type()
        question = by_type[qtype]
        answers = dict(EXAMPLE_ANSWERS)
        answers[question.id] = _WRONG_ANSWERS[qtype]
        with pytest.raises(FormValidationError) as excinfo:
            collect_form_response(form, answers)
        assert question.id in str(excinfo.value)
