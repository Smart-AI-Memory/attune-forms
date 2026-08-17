"""Tests for the v6 deliberation construct (communication grammar).

A DELIBERATION is a decision whose options carry multi-voice
endorsements ({option: [voice, ...]}): the chips make a 2-1 split and
its minority visible, the synthesis pick is badged, and the chair picks
one — the answer validates exactly as a single-select. Ratified with
amendments by the round table (thread q-forms-grammar-expansion-001):
the synthesis recommendation stays a badge, never the answer, and the
flat fallback folds endorsements into a compact summary instead of
dumping rationale per voice.
"""

from __future__ import annotations

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_widget_html,
    needs_widget,
)
from attune_forms.bridge import form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import FormQuestion, QuestionType


def _deliberation(**override) -> dict:
    """Build a one-field deliberation form dict, overriding the field."""
    field = {
        "id": "cache",
        "text": "Where should the cache live?",
        "type": "deliberation",
        "options": ["LRU", "Redis", "None yet"],
        "endorsements": {"LRU": ["claude", "codex"], "Redis": ["antigravity"]},
        "recommended": "LRU",
        "rationale": "Two of three seats favor in-process.",
    }
    field.update(override)
    return {"title": "Deliberate", "fields": [field]}


class TestDeliberationModel:
    def test_questiontype_has_deliberation(self) -> None:
        assert QuestionType.DELIBERATION.value == "deliberation"

    def test_formquestion_endorsements_default_none(self) -> None:
        q = FormQuestion(id="a", text="t", type=QuestionType.DELIBERATION)
        assert q.endorsements is None


class TestDeliberationFormFromDict:
    def test_builds_with_endorsements(self) -> None:
        form = form_from_dict(_deliberation())
        q = form.questions[0]
        assert q.type == QuestionType.DELIBERATION
        assert q.endorsements == {"LRU": ["claude", "codex"], "Redis": ["antigravity"]}

    def test_requires_options(self) -> None:
        with pytest.raises(FormValidationError, match="requires non-empty 'options'"):
            form_from_dict(_deliberation(options=[], endorsements={}))

    def test_requires_endorsements(self) -> None:
        with pytest.raises(FormValidationError, match="requires 'endorsements'"):
            form_from_dict(_deliberation(endorsements=None))

    def test_endorsement_keys_must_be_options(self) -> None:
        with pytest.raises(FormValidationError, match="'endorsements' keys not in options"):
            form_from_dict(_deliberation(endorsements={"Ghost": ["claude"]}))

    def test_endorsement_values_must_be_nonempty_name_lists(self) -> None:
        for bad in ({"LRU": []}, {"LRU": "claude"}, {"LRU": [""]}, {"LRU": [1]}):
            with pytest.raises(FormValidationError, match="non-empty list of names"):
                form_from_dict(_deliberation(endorsements=bad))

    def test_endorsements_invalid_on_other_types(self) -> None:
        with pytest.raises(FormValidationError, match="only valid on deliberation"):
            form_from_dict(_deliberation(type="decision", endorsements={"LRU": ["claude"]}))

    def test_unendorsed_option_is_allowed(self) -> None:
        # The chair may table a position no voice proposed ("None yet").
        form = form_from_dict(_deliberation())
        assert "None yet" in form.questions[0].options


class TestDeliberationAnswer:
    def test_collect_accepts_selected_option(self) -> None:
        form = form_from_dict(_deliberation())
        resp = collect_form_response(form, {"cache": "Redis"})
        assert resp.responses == {"cache": "Redis"}

    def test_collect_rejects_out_of_option(self) -> None:
        form = form_from_dict(_deliberation())
        with pytest.raises(FormValidationError, match="not in options"):
            collect_form_response(form, {"cache": "nope"})

    def test_chair_pick_beats_synthesis(self) -> None:
        # The synthesis pick is a badge, never the answer: picking a
        # non-recommended option is a first-class outcome.
        form = form_from_dict(_deliberation())
        resp = collect_form_response(form, {"cache": "None yet"})
        assert resp.responses["cache"] == "None yet"


class TestDeliberationFallback:
    def test_maps_to_single_select_recommended_first(self) -> None:
        form = form_from_dict(_deliberation())
        payload = form_to_askuserquestion(form)[0][0]
        assert payload["type"] == "single_select"
        assert payload["options"][0] == "LRU"

    def test_endorsements_fold_into_help_text(self) -> None:
        # The flat surface has no chip row — the 2-1 split must survive
        # as a compact summary (round-table degradation ruling).
        form = form_from_dict(_deliberation())
        payload = form_to_askuserquestion(form)[0][0]
        assert "Endorsements" in payload["help_text"]
        assert "claude, codex" in payload["help_text"]

    def test_routes_to_widget(self) -> None:
        assert needs_widget(form_from_dict(_deliberation())) is True

    def test_elicitation_schema_is_string_enum(self) -> None:
        schema = form_to_elicitation_schema(form_from_dict(_deliberation()))
        prop = schema["properties"]["cache"]
        assert prop["type"] == "string"
        assert prop["enum"] == ["LRU", "Redis", "None yet"]


class TestDeliberationWidget:
    def test_renders_cards_with_seat_chips(self) -> None:
        html = form_to_widget_html(form_from_dict(_deliberation()))
        assert 'class="ae-cards"' in html
        assert html.count('class="ae-seat"') == 3  # claude, codex, antigravity
        assert "Synthesis pick" in html
        assert 'data-ftype="deliberation"' in html

    def test_rationale_headed_synthesis(self) -> None:
        html = form_to_widget_html(form_from_dict(_deliberation()))
        assert "Synthesis</span>" in html

    def test_deliberation_collects_as_checked_one(self) -> None:
        html = form_to_widget_html(form_from_dict(_deliberation()))
        assert 'data-collect="checked-one"' in html

    def test_recommended_ordered_first(self) -> None:
        html = form_to_widget_html(form_from_dict(_deliberation()))
        assert html.index('value="LRU"') < html.index('value="Redis"')

    def test_voice_names_are_escaped(self) -> None:
        html = form_to_widget_html(
            form_from_dict(_deliberation(endorsements={"LRU": ['<img src=x onerror="p()">']}))
        )
        assert "<img" not in html
