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


class TestReviewFindingRegressions:
    def test_falsy_zero_default_survives_in_skeleton(self) -> None:
        # `default or recommended` swallowed falsy defaults: a NUMBER
        # default of 0 must render as 0, never null.
        form = form_from_dict(
            {
                "title": "t",
                "fields": [{"id": "retries", "type": "number", "text": "Retries?", "default": 0}],
            }
        )
        assert _skeleton(form_to_markdown(form))["answers"]["retries"] == 0


# --- multi-line item detail (regression, 2026-08-28) -----------------
#
# A multi-line ``detail`` — a diff hunk, a log excerpt — used to be
# interpolated straight into the bullet: the opening fence landed
# mid-line so it never opened a code block, every removed line of a
# diff parsed as a NEW bullet, and a "suggested" suffix was glued onto
# the detail's closing fence. Found by probing the zero-change triage
# encoding for hunk review (round table q-forms-hunk-review-001).

_DIFF = "```diff\n@@ -88,7 +88,9 @@\n-    while True:\n+    for _ in range(3):\n```"


def _hunk_board(**extra) -> dict:
    item = {"id": "src/bridge.py@a1b2c3d:88-96", "label": "bound the retry loop", "detail": _DIFF}
    return {
        "title": "t",
        "fields": [
            {
                "id": "hunks",
                "type": "triage",
                "text": "Rule each hunk.",
                "triage_items": [item],
                "dispositions": ["apply", "revise", "drop"],
                **extra,
            }
        ],
    }


def test_multiline_detail_moves_below_the_bullet() -> None:
    """The detail is an indented block, not part of the bullet line."""
    md = form_to_markdown(form_from_dict(_hunk_board()))
    bullet = next(ln for ln in md.splitlines() if ln.startswith("- **bound the retry loop**"))
    assert "```" not in bullet, "fence must not open mid-bullet"
    # Indented, not fenced: _defuse_fences would break any fence we
    # emitted, so the block relies on indentation alone.
    assert "      @@ -88,7 +88,9 @@" in md


def test_multiline_detail_removed_lines_stay_inside_the_fence() -> None:
    """A diff's ``-`` lines must not parse as new bullets."""
    md = form_to_markdown(form_from_dict(_hunk_board()))
    assert "      -    while True:" in md
    assert not any(
        ln.startswith("-    while True:") for ln in md.splitlines()
    ), "removed line escaped the fence and became a bullet"


def test_multiline_detail_keeps_suggested_on_the_bullet() -> None:
    """``suggested`` rides the bullet, never the detail's closing fence."""
    board = _hunk_board(suggested={"src/bridge.py@a1b2c3d:88-96": "apply"})
    md = form_to_markdown(form_from_dict(board))
    bullet = next(ln for ln in md.splitlines() if ln.startswith("- **bound the retry loop**"))
    assert bullet.endswith("→ suggested: `apply`")


def test_single_line_detail_still_renders_inline() -> None:
    """The common case is unchanged — no gratuitous block."""
    board = _hunk_board()
    board["fields"][0]["triage_items"][0]["detail"] = "worker.py:88"
    md = form_to_markdown(form_from_dict(board))
    assert "- **bound the retry loop** — worker.py:88" in md


def test_unfenced_multiline_detail_is_still_indented() -> None:
    """An author who did not fence the block still gets literal lines."""
    board = _hunk_board()
    board["fields"][0]["triage_items"][0]["detail"] = "line one\n- line two\nline three"
    md = form_to_markdown(form_from_dict(board))
    assert "      line one" in md
    assert "      - line two" in md


def test_author_fence_is_stripped_not_defused() -> None:
    """A ```lang wrapper cannot survive this surface — drop it.

    ``_defuse_fences`` breaks every three-backtick run so the reply
    skeleton keeps its boundaries; a kept wrapper would therefore render
    as visible backtick-plus-zero-width noise around the block.
    """
    md = form_to_markdown(form_from_dict(_hunk_board()))
    detail = [ln for ln in md.splitlines() if ln.startswith("      ")]
    assert detail, "detail block missing"
    assert not any("`" in ln for ln in detail), "author fence survived into the block"


def test_multiline_detail_keeps_the_skeleton_round_tripping() -> None:
    """The block must not desync the trailing answers skeleton."""
    form = form_from_dict(_hunk_board())
    skeleton = _skeleton(form_to_markdown(form))
    assert skeleton["answers"] == {"hunks": {"src/bridge.py@a1b2c3d:88-96": None}}


def test_progress_multiline_detail_stays_inside_its_row() -> None:
    """PROGRESS rows route detail through _item_row like the other
    item-bearing constructs (retro probe 2026-08-29: the #61 batch
    missed this fourth site)."""
    md = form_to_markdown(
        form_from_dict(
            {
                "title": "T",
                "fields": [
                    {
                        "id": "p",
                        "type": "progress",
                        "text": "Status?",
                        "progress_items": [
                            {
                                "label": "migrate",
                                "status": "done",
                                "detail": "a\n-    old\n+    new",
                            },
                            {"label": "ship", "status": "blocked", "detail": "one-liner"},
                        ],
                        "options": ["ship"],
                    }
                ],
            }
        )
    )
    assert "      -    old" in md
    assert not any(ln.startswith("-    old") for ln in md.splitlines())
    assert "- ✕ ship — one-liner" in md
