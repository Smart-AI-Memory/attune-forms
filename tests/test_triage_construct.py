"""Tests for the v6 triage construct (communication grammar).

A TRIAGE is a per-item ruling board: every reviewed item gets its own
disposition from a small shared vocabulary; the answer is
{item key: disposition} — the one construct whose answer is a mapping.
Round-table amendments applied (thread q-forms-grammar-expansion-001):
answers key on a stable per-item ``id`` (label fallback) so label edits
and collisions can't corrupt rulings, and the flat degradation expands
to one single-select per item via dotted ids that fold back at
collection time.
"""

from __future__ import annotations

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_widget_html,
    needs_widget,
    triage_item_key,
)
from attune_forms.bridge import form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import QuestionType


def _triage(**override) -> dict:
    """Build a one-field triage form dict, overriding the field."""
    field = {
        "id": "findings",
        "text": "Rule each finding.",
        "type": "triage",
        "triage_items": [
            {
                "id": "retry",
                "label": "Unbounded retry loop",
                "tag": "high",
                "detail": "worker.py:88",
            },
            {"id": "doc", "label": "Stale docstring", "tag": "low"},
            {"label": "Naming nit"},
        ],
        "dispositions": ["fix now", "ticket", "dismiss"],
        "suggested": {"retry": "fix now"},
    }
    field.update(override)
    return {"title": "Review triage", "fields": [field]}


class TestTriageItemKey:
    def test_id_wins_over_label(self) -> None:
        assert triage_item_key({"id": "retry", "label": "Retry loop"}) == "retry"

    def test_label_is_the_fallback(self) -> None:
        assert triage_item_key({"label": "Naming nit"}) == "Naming nit"


class TestTriageFormFromDict:
    def test_builds_with_items_and_dispositions(self) -> None:
        form = form_from_dict(_triage())
        q = form.questions[0]
        assert q.type == QuestionType.TRIAGE
        assert len(q.triage_items) == 3
        assert q.dispositions == ["fix now", "ticket", "dismiss"]
        assert q.suggested == {"retry": "fix now"}

    def test_requires_items(self) -> None:
        with pytest.raises(FormValidationError, match="requires 'triage_items'"):
            form_from_dict(_triage(triage_items=None))

    def test_requires_dispositions(self) -> None:
        with pytest.raises(FormValidationError, match="requires 'dispositions'"):
            form_from_dict(_triage(dispositions=None))

    def test_items_need_labels(self) -> None:
        with pytest.raises(FormValidationError, match="needs a 'label' string"):
            form_from_dict(_triage(triage_items=[{"tag": "high"}]))

    def test_duplicate_keys_rejected(self) -> None:
        with pytest.raises(FormValidationError, match="duplicate key"):
            form_from_dict(
                _triage(
                    triage_items=[{"label": "Same"}, {"label": "Same"}],
                    suggested=None,
                )
            )

    def test_id_dedupes_identical_labels(self) -> None:
        # Stable ids exist exactly so twin labels can coexist.
        form = form_from_dict(
            _triage(
                triage_items=[
                    {"id": "a", "label": "Same"},
                    {"id": "b", "label": "Same"},
                ],
                suggested=None,
            )
        )
        assert [triage_item_key(i) for i in form.questions[0].triage_items] == ["a", "b"]

    def test_dispositions_need_two_unique(self) -> None:
        for bad in (["only"], ["x", "x"], ["x", ""], "not-a-list"):
            with pytest.raises(FormValidationError, match="unique non-empty strings"):
                form_from_dict(_triage(dispositions=bad, suggested=None))

    def test_suggested_keys_must_be_item_keys(self) -> None:
        with pytest.raises(FormValidationError, match="not in triage item keys"):
            form_from_dict(_triage(suggested={"ghost": "fix now"}))

    def test_suggested_values_must_be_dispositions(self) -> None:
        with pytest.raises(FormValidationError, match="not in dispositions"):
            form_from_dict(_triage(suggested={"retry": "shrug"}))

    def test_extras_invalid_on_other_types(self) -> None:
        with pytest.raises(FormValidationError, match="only valid on triage"):
            form_from_dict(_triage(type="decision", options=["a"]))


class TestTriageAnswer:
    def test_collect_accepts_full_ruling(self) -> None:
        form = form_from_dict(_triage())
        rulings = {"retry": "fix now", "doc": "ticket", "Naming nit": "dismiss"}
        resp = collect_form_response(form, {"findings": rulings})
        assert resp.responses["findings"] == rulings

    def test_required_board_rejects_partial_ruling(self) -> None:
        form = form_from_dict(_triage())
        with pytest.raises(FormValidationError, match="missing ruling"):
            collect_form_response(form, {"findings": {"retry": "fix now"}})

    def test_optional_board_accepts_partial_ruling(self) -> None:
        form = form_from_dict(_triage(required=False))
        resp = collect_form_response(form, {"findings": {"doc": "dismiss"}})
        assert resp.responses["findings"] == {"doc": "dismiss"}

    def test_unknown_item_rejected(self) -> None:
        form = form_from_dict(_triage())
        with pytest.raises(FormValidationError, match="unknown item"):
            collect_form_response(form, {"findings": {"ghost": "fix now"}})

    def test_out_of_disposition_rejected(self) -> None:
        form = form_from_dict(_triage())
        with pytest.raises(FormValidationError, match="out-of-disposition"):
            collect_form_response(
                form,
                {"findings": {"retry": "shrug", "doc": "ticket", "Naming nit": "dismiss"}},
            )

    def test_non_mapping_rejected(self) -> None:
        form = form_from_dict(_triage())
        with pytest.raises(FormValidationError, match="expects a mapping"):
            collect_form_response(form, {"findings": "fix now"})

    def test_empty_mapping_is_missing(self) -> None:
        form = form_from_dict(_triage())
        with pytest.raises(FormValidationError, match="is required"):
            collect_form_response(form, {"findings": {}})


class TestTriageDottedFold:
    def test_flat_dotted_answers_fold_into_the_mapping(self) -> None:
        # The AskUserQuestion / elicitation transport shape.
        form = form_from_dict(_triage())
        resp = collect_form_response(
            form,
            {
                "findings.retry": "fix now",
                "findings.doc": "ticket",
                "findings.Naming nit": "dismiss",
            },
        )
        assert resp.responses["findings"] == {
            "retry": "fix now",
            "doc": "ticket",
            "Naming nit": "dismiss",
        }

    def test_mapping_plus_dotted_is_a_named_contradiction(self) -> None:
        # Chair ruling 2026-08-20: mapping-wins used to silently discard
        # the contradicting dotted value; mixed shapes are now named.
        form = form_from_dict(_triage(required=False))
        with pytest.raises(FormValidationError, match="supplied both canonically and as dotted"):
            collect_form_response(
                form,
                {"findings": {"retry": "ticket"}, "findings.retry": "dismiss"},
            )

    def test_fold_never_mutates_the_input(self) -> None:
        form = form_from_dict(_triage(required=False))
        raw = {"findings.retry": "fix now"}
        collect_form_response(form, raw)
        assert raw == {"findings.retry": "fix now"}


class TestTriageFallback:
    def test_expands_to_one_single_select_per_item(self) -> None:
        form = form_from_dict(_triage())
        payloads = [p for batch in form_to_askuserquestion(form) for p in batch]
        assert [p["question_id"] for p in payloads] == [
            "findings.retry",
            "findings.doc",
            "findings.Naming nit",
        ]
        assert all(p["type"] == "single_select" for p in payloads)
        assert all(p["options"] == ["fix now", "ticket", "dismiss"] for p in payloads)

    def test_suggested_becomes_the_default(self) -> None:
        form = form_from_dict(_triage())
        payloads = [p for batch in form_to_askuserquestion(form) for p in batch]
        assert payloads[0]["default"] == "fix now"
        assert payloads[1]["default"] is None

    def test_item_context_folds_into_help_text(self) -> None:
        form = form_from_dict(_triage())
        payloads = [p for batch in form_to_askuserquestion(form) for p in batch]
        assert payloads[0]["help_text"] == "high · worker.py:88"

    def test_expansion_batches_with_other_questions(self) -> None:
        data = _triage()
        data["fields"].append({"id": "note", "type": "text_input", "text": "n", "required": False})
        batches = form_to_askuserquestion(form_from_dict(data))
        assert [len(b) for b in batches] == [4]

    def test_routes_to_widget(self) -> None:
        assert needs_widget(form_from_dict(_triage())) is True

    def test_elicitation_schema_flattens_per_item(self) -> None:
        schema = form_to_elicitation_schema(form_from_dict(_triage()))
        assert set(schema["properties"]) == {
            "findings.retry",
            "findings.doc",
            "findings.Naming nit",
        }
        prop = schema["properties"]["findings.retry"]
        assert prop["enum"] == ["fix now", "ticket", "dismiss"]
        assert prop["default"] == "fix now"
        assert schema["required"] == ["findings.retry", "findings.doc", "findings.Naming nit"]


class TestTriageWidget:
    def test_renders_rows_and_per_row_pickers(self) -> None:
        html = form_to_widget_html(form_from_dict(_triage()))
        assert html.count('class="ae-triage-row"') == 3
        assert 'data-item="retry"' in html  # keyed by id, not label
        assert 'data-item="Naming nit"' in html  # label fallback
        assert html.count('role="radiogroup"') == 3
        assert 'data-ftype="triage"' in html

    def test_suggested_prechecked_and_marked(self) -> None:
        html = form_to_widget_html(form_from_dict(_triage()))
        assert "checked" in html
        assert 'class="ae-triage-sug"' in html

    def test_submit_script_rebuilds_the_mapping(self) -> None:
        html = form_to_widget_html(form_from_dict(_triage()))
        assert 'data-collect="rulings"' in html
        script = html.split("<script>")[1]
        assert "mode === 'rulings'" in script
        assert "data-item" in script  # rows scoped generically, not by class

    def test_labels_and_dispositions_are_escaped(self) -> None:
        html = form_to_widget_html(
            form_from_dict(
                _triage(
                    triage_items=[{"label": '<b>"bold"</b>'}],
                    dispositions=["<keep>", "drop"],
                    suggested=None,
                )
            )
        )
        assert "<b>" not in html
        assert "<keep>" not in html


class TestReviewFindingRegressions:
    """Regressions for the 2026-08-14 review findings owned by triage."""

    def test_sibling_id_in_dotted_namespace_rejected(self) -> None:
        # The fold claims every "<board>." key, so a sibling field inside
        # the namespace would have its answer stolen — reject at definition.
        data = _triage()
        data["fields"].append(
            {"id": "findings.notes", "type": "text_input", "text": "n", "required": False}
        )
        with pytest.raises(FormValidationError, match="dotted answer namespace"):
            form_from_dict(data)

    def test_summary_renders_rulings_not_dict_repr(self) -> None:
        from attune_forms import form_response_summary

        form = form_from_dict(_triage())
        resp = collect_form_response(
            form,
            {"findings": {"retry": "fix now", "doc": "ticket", "Naming nit": "dismiss"}},
        )
        summary = form_response_summary(form, resp)
        assert "retry: fix now; doc: ticket; Naming nit: dismiss" in summary
        assert "{'" not in summary  # never the raw dict repr

    def test_old_single_payload_contract_raises_loudly(self) -> None:
        # to_ask_user_format used to fall through to an unrenderable
        # {"type": "triage", "options": []} payload; now it refuses.
        form = form_from_dict(_triage())
        with pytest.raises(ValueError, match="to_ask_user_formats"):
            form.questions[0].to_ask_user_format()
