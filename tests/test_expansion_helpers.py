"""Tests for the 0.5.0 cleanup batch: the shared expansion helpers and
the direct-built CONFIRM options gap.

Queued at the 0.5.0 post-merge review ("known skipped: direct-built
CONFIRM options gap; cleanup batch: helper dedup, triage-expansion
unification"): every surface now iterates item-keyed constructs through
``expansion_items`` / ``suggested_pick`` / ``item_context`` in
``models``, and a CONFIRM defaults its two-way gate on EVERY
construction path, not just ``form_from_dict``.
"""

from __future__ import annotations

from attune_forms import (
    collect_form_response,
    form_to_askuserquestion,
    form_to_markdown,
    form_to_widget_html,
)
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import (
    CONFIRM_DEFAULT_OPTIONS,
    FormQuestion,
    FormSchema,
    QuestionType,
    expansion_items,
    item_context,
    suggested_pick,
)

_TRIAGE = FormQuestion(
    id="board",
    text="Rule each",
    type=QuestionType.TRIAGE,
    triage_items=[
        {"id": "one", "label": "First", "tag": "high", "detail": "ctx"},
        {"label": "Second"},
    ],
    dispositions=["keep", "drop"],
    suggested={"one": "keep"},
)

_REVIEW = FormQuestion(
    id="assume",
    text="Rule these",
    type=QuestionType.ASSUMPTION_REVIEW,
    assumptions=[
        {"id": "py", "label": "Py floor", "source": "pyproject", "detail": "3.10"},
        {"label": "Bare row"},
    ],
    suggested={"py": "accept"},
)


class TestExpansionItems:
    def test_triage_rows_keyed_like_every_surface(self) -> None:
        assert expansion_items(_TRIAGE) == [
            ("one", _TRIAGE.triage_items[0]),
            ("Second", _TRIAGE.triage_items[1]),
        ]

    def test_assumption_rows(self) -> None:
        assert [k for k, _ in expansion_items(_REVIEW)] == ["py", "Bare row"]

    def test_non_item_types_have_no_rows(self) -> None:
        q = FormQuestion(id="t", text="t", type=QuestionType.TEXT_INPUT)
        assert expansion_items(q) == []


class TestSuggestedPick:
    def test_mapping_lookup(self) -> None:
        assert suggested_pick(_TRIAGE, "one") == "keep"
        assert suggested_pick(_TRIAGE, "Second") is None

    def test_non_mapping_suggested_degrades_to_none(self) -> None:
        """A direct-built question carrying the WRONG suggested shape
        (list on an item-keyed construct) must read as "no suggestion"
        — before the cleanup, the elicitation triage path crashed on
        exactly this (unguarded ``.get`` on a list)."""
        q = FormQuestion(
            id="board",
            text="Rule each",
            type=QuestionType.TRIAGE,
            triage_items=[{"id": "one", "label": "First"}],
            dispositions=["keep", "drop"],
            suggested=["keep"],  # type: ignore[arg-type] — the wrong shape, deliberately
        )
        assert suggested_pick(q, "one") is None
        # And every surface renders it rather than raising.
        form = FormSchema(title="T", description="", questions=[q])
        form_to_widget_html(form, instance_id="x")
        form_to_askuserquestion(form)
        form_to_elicitation_schema(form)
        form_to_markdown(form)


class TestItemContext:
    def test_triage_joins_tag_and_detail(self) -> None:
        assert item_context(_TRIAGE, _TRIAGE.triage_items[0]) == "high · ctx"

    def test_assumption_joins_source_and_detail(self) -> None:
        assert item_context(_REVIEW, _REVIEW.assumptions[0]) == "pyproject · 3.10"

    def test_bare_item_is_none(self) -> None:
        assert item_context(_TRIAGE, {"label": "Second"}) is None


class TestDirectBuiltConfirm:
    def test_direct_built_confirm_defaults_the_two_way_gate(self) -> None:
        """The gap itself: a FormQuestion built in Python (no
        form_from_dict) previously carried NO options and rendered a
        gate nothing could approve."""
        q = FormQuestion(
            id="gate",
            text="Ship?",
            type=QuestionType.CONFIRM,
            consequences=[{"label": "Tag pushed", "severity": "irreversible"}],
        )
        assert q.options == list(CONFIRM_DEFAULT_OPTIONS)
        form = FormSchema(title="Release", description="", questions=[q])
        html = form_to_widget_html(form, instance_id="g")
        assert 'value="Approve"' in html and 'value="Abort"' in html
        got = collect_form_response(form, {"gate": "Approve"})
        assert got.responses["gate"] == "Approve"

    def test_author_named_options_survive(self) -> None:
        q = FormQuestion(
            id="gate",
            text="Ship?",
            type=QuestionType.CONFIRM,
            options=["Go", "Hold"],
            consequences=[{"label": "Tag pushed"}],
        )
        assert q.options == ["Go", "Hold"]
