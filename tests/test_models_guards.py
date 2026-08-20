"""Tests for the confirmation-pass-1 models fixes (ledger 2026-08-20).

Two needs-a-look rows, both direct-Python-API reach only (the parse
path validates these shapes before they reach the helpers):

1. ``get_question_batches`` rejects a non-positive ``batch_size`` with a
   named ``ValueError`` — before, ``-1`` silently returned ``[]`` (every
   question dropped) and ``0`` raised a raw ``range()`` error.
2. The formatting helpers now degrade direct-built malformed shapes the
   way ``suggested_pick`` always did, instead of crashing: non-dict
   ``consequences`` entries are skipped, a list-typed ``endorsements``
   reads as no endorsements (``endorsement_map``), and non-dict
   ``triage_items`` / ``assumptions`` rows are skipped by
   ``expansion_items`` on every surface.
"""

from __future__ import annotations

import pytest

from attune_forms import (
    form_to_askuserquestion,
    form_to_markdown,
    form_to_widget_html,
)
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import (
    FormQuestion,
    FormSchema,
    QuestionType,
    _consequences_summary,
    endorsement_map,
    expansion_items,
)


def _form(q: FormQuestion) -> FormSchema:
    return FormSchema(title="T", description="", questions=[q])


def _render_every_surface(q: FormQuestion) -> None:
    """Every flat + rich surface renders the question rather than raising."""
    form = _form(q)
    form_to_widget_html(form, instance_id="x")
    form_to_askuserquestion(form)
    form_to_elicitation_schema(form)
    form_to_markdown(form)


class TestGetQuestionBatchesGuard:
    _QS = [FormQuestion(id=f"q{i}", text=f"Q{i}", type=QuestionType.TEXT_INPUT) for i in range(5)]

    def test_negative_batch_size_is_named_not_silent_empty(self) -> None:
        """The silent-drop shape itself: -1 used to return [] — five
        questions gone with no signal."""
        form = FormSchema(title="T", description="", questions=list(self._QS))
        with pytest.raises(ValueError, match="batch_size must be at least 1, got -1"):
            form.get_question_batches(batch_size=-1)

    def test_zero_batch_size_is_named_not_raw_range_error(self) -> None:
        form = FormSchema(title="T", description="", questions=list(self._QS))
        with pytest.raises(ValueError, match="batch_size must be at least 1, got 0"):
            form.get_question_batches(batch_size=0)

    def test_positive_sizes_still_batch(self) -> None:
        form = FormSchema(title="T", description="", questions=list(self._QS))
        assert [len(b) for b in form.get_question_batches()] == [4, 1]
        assert [len(b) for b in form.get_question_batches(batch_size=1)] == [1] * 5
        assert [len(b) for b in form.get_question_batches(batch_size=2)] == [2, 2, 1]


class TestConsequencesDegrade:
    def test_non_dict_entries_are_skipped_not_crashed(self) -> None:
        """Before the guard: raw AttributeError from ``item.get`` on the
        string entry — inconsistent with suggested_pick's degrade norm."""
        assert (
            _consequences_summary(
                [{"label": "Tag pushed", "severity": "irreversible"}, "oops"]  # type: ignore[list-item]
            )
            == "Will: Tag pushed (irreversible)"
        )

    def test_all_bad_entries_degrade_to_none(self) -> None:
        assert _consequences_summary(["oops", 3]) is None  # type: ignore[list-item]

    def test_confirm_renders_on_every_surface(self) -> None:
        q = FormQuestion(
            id="gate",
            text="Ship?",
            type=QuestionType.CONFIRM,
            consequences=[{"label": "Tag pushed"}, "oops"],  # type: ignore[list-item]
        )
        _render_every_surface(q)
        payload = q.to_ask_user_format()
        assert payload["help_text"] == "Will: Tag pushed"


class TestEndorsementsDegrade:
    _BAD = FormQuestion(
        id="pick",
        text="Which?",
        type=QuestionType.DELIBERATION,
        options=["A", "B"],
        endorsements=["claude", "codex"],  # type: ignore[arg-type] — the wrong shape, deliberately
    )

    def test_list_typed_endorsements_read_as_none(self) -> None:
        assert endorsement_map(self._BAD) == {}

    def test_mapping_passes_through(self) -> None:
        q = FormQuestion(
            id="pick",
            text="Which?",
            type=QuestionType.DELIBERATION,
            options=["A", "B"],
            endorsements={"A": ["claude"]},
        )
        assert endorsement_map(q) == {"A": ["claude"]}

    def test_every_surface_renders_without_the_fold(self) -> None:
        """Before the guard: ``.items()`` (help-text fold), ``.get``
        (widget chips, markdown suffix) each raised AttributeError."""
        _render_every_surface(self._BAD)
        payload = self._BAD.to_ask_user_format()
        assert payload["help_text"] is None  # no endorsement fold, no crash


class TestExpansionItemsDegrade:
    def test_non_dict_triage_rows_are_skipped(self) -> None:
        q = FormQuestion(
            id="board",
            text="Rule each",
            type=QuestionType.TRIAGE,
            triage_items=[{"id": "one", "label": "First"}, "oops"],  # type: ignore[list-item]
            dispositions=["keep", "drop"],
        )
        assert [k for k, _ in expansion_items(q)] == ["one"]
        _render_every_surface(q)
        assert [p["question_id"] for p in q.to_ask_user_formats()] == ["board.one"]

    def test_non_dict_assumption_rows_are_skipped(self) -> None:
        q = FormQuestion(
            id="assume",
            text="Rule these",
            type=QuestionType.ASSUMPTION_REVIEW,
            assumptions=[{"id": "py", "label": "Py floor"}, 42],  # type: ignore[list-item]
        )
        assert [k for k, _ in expansion_items(q)] == ["py"]
        _render_every_surface(q)
        ids = [p["question_id"] for p in q.to_ask_user_formats()]
        assert ids == ["assume.py", "assume.py.text"]
