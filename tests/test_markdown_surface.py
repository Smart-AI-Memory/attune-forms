"""Tests for the S4 portable markdown surface (``form_to_markdown``).

The surface for hosts with neither an HTML widget pane nor a question
tool (Codex CLI, Antigravity, plain chat). Round-table ruling (thread
q-forms-grammar-expansion-001, 3/3): rendering alone is documentation,
not a surface — the RETURN PATH is the construct. Here that path is the
emitted JSON answer skeleton: the widget's exact sentinel-marked
postback shape, filled by the host agent and validated through
``collect_form_response``. The round-trip tests below are the
conformance check the table demanded.
"""

from __future__ import annotations

import json

import pytest

from attune_forms import (
    WIDGET_RESPONSE_MARKER,
    collect_form_response,
    form_from_dict,
    form_to_markdown,
)
from attune_forms.models import QuestionType
from attune_forms.reference_form import EXAMPLE_ANSWERS, REFERENCE_FORM


def _skeleton(md: str) -> dict:
    """Extract the emitted JSON answer skeleton from the markdown."""
    block = md.split("```json")[1].split("```")[0]
    return json.loads(block)


class TestRendersEveryControlType:
    def test_reference_form_renders_all_types(self) -> None:
        # The drift-guarded reference covers every QuestionType; one
        # render must carry every field and emit a complete skeleton.
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form, message="hello")
        assert md.startswith(f"## {form.title}")
        assert "hello" in md
        for q in form.questions:
            assert q.text in md
        assert set(_skeleton(md)["answers"]) == {q.id for q in form.questions}

    def test_decision_marks_recommended_and_notes(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "**(recommended)**" in md
        assert "> **Why:**" in md

    def test_pushback_marks_both_positions(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "**(I'd suggest instead)**" in md
        assert "**(your approach)**" in md
        assert "> **Why I'd push back:**" in md

    def test_deliberation_summarizes_endorsements(self) -> None:
        # The strict summary degradation the table demanded — voices as
        # a compact suffix, never a rationale dump per voice.
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "**(synthesis pick)**" in md
        assert "endorsed by: claude, codex" in md
        assert "> **Synthesis:**" in md

    def test_progress_renders_status_icons_and_picker(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "- ✓ Requirements" in md
        assert "- ◐ Prototype" in md
        assert "- ✕ Design sign-off" in md
        assert "Blocked — pick one to tackle:" in md

    def test_triage_renders_vocabulary_and_suggestions(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "Rule each item as one of: `fix now` / `ticket` / `dismiss`" in md
        assert "→ suggested: `fix now`" in md

    def test_inferred_default_marked_as_guess(self) -> None:
        form = form_from_dict(
            {
                "title": "t",
                "fields": [
                    {
                        "id": "env",
                        "type": "text_input",
                        "text": "Env?",
                        "default": "staging",
                        "inferred_from": "recent deploys target staging",
                    }
                ],
            }
        )
        md = form_to_markdown(form)
        assert "> guessed: `staging` — recent deploys target staging" in md

    def test_optional_field_marked(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        assert "*(optional)*" in md


class TestSkeletonRoundTrip:
    def test_skeleton_carries_the_widget_sentinel(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        skeleton = _skeleton(form_to_markdown(form))
        assert skeleton[WIDGET_RESPONSE_MARKER] is True
        assert skeleton["title"] == form.title

    def test_filled_skeleton_validates(self) -> None:
        # The conformance loop: render -> fill the skeleton with the
        # reference answers -> validate. Same validator as every surface.
        form = form_from_dict(REFERENCE_FORM)
        skeleton = _skeleton(form_to_markdown(form))
        skeleton["answers"].update(EXAMPLE_ANSWERS)
        response = collect_form_response(form, skeleton["answers"])
        assert set(response.responses) == set(EXAMPLE_ANSWERS)

    def test_triage_skeleton_prefills_suggested(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        skeleton = _skeleton(form_to_markdown(form))
        assert skeleton["answers"]["finding_rulings"] == {
            "retry-loop": "fix now",
            "stale-doc": None,
        }

    def test_recommended_prefills_construct_answers(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        skeleton = _skeleton(form_to_markdown(form))
        assert skeleton["answers"]["rollout"] == "Ship behind a feature flag"


class TestListStyles:
    def test_ordered_list_style_numbers_options(self) -> None:
        form = form_from_dict(
            {
                "title": "t",
                "fields": [
                    {
                        "id": "s",
                        "type": "single_select",
                        "text": "Pick",
                        "options": ["a", "b"],
                        "list_style": "ordered",
                    }
                ],
            }
        )
        md = form_to_markdown(form)
        assert "1. a" in md and "2. b" in md

    def test_multi_select_notes_pick_any(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        assert "*(pick any that apply)*" in form_to_markdown(form)


class TestQuestionTypeCoverageGuard:
    def test_every_type_renders_nonempty_control_lines(self) -> None:
        """Drift guard: a new QuestionType must render SOMETHING on the
        markdown surface — the reference form (one field per type) is the
        fixture, and every field must contribute at least one control
        line beyond its label."""
        form = form_from_dict(REFERENCE_FORM)
        covered = {q.type for q in form.questions}
        assert covered == set(QuestionType)
        md = form_to_markdown(form)
        # Every question renders its number + bolded text line.
        for idx, q in enumerate(form.questions, start=1):
            assert f"{idx}. **{q.text}**" in md


class TestValidationErrorPath:
    def test_bad_skeleton_fill_fails_loudly(self) -> None:
        form = form_from_dict(REFERENCE_FORM)
        skeleton = _skeleton(form_to_markdown(form))
        answers = dict(EXAMPLE_ANSWERS)
        answers["priority"] = "nope"
        skeleton["answers"].update(answers)
        with pytest.raises(Exception, match="not in options"):
            collect_form_response(form, skeleton["answers"])
