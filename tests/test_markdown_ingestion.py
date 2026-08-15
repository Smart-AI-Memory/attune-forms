"""Tests for tolerant markdown ingestion (spec markdown-ingestion).

``markdown_to_answers`` parses a typed reply to a markdown-rendered
form — filled JSON skeleton or line shorthand — deterministically,
with every unparseable line and unknown id a named problem;
``problems_to_markdown`` renders validation failures back as a
markdown re-ask of only the offending fields. Validation truth stays
``collect_form_response`` throughout (D1).
"""

from __future__ import annotations

import json

import pytest

from attune_forms import (
    WIDGET_RESPONSE_MARKER,
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_markdown,
    markdown_to_answers,
    problems_to_markdown,
)
from attune_forms.reference_form import EXAMPLE_ANSWERS, REFERENCE_FORM


def _small_form() -> dict:
    return {
        "title": "Deploy check",
        "fields": [
            {"id": "env", "type": "single_select", "text": "Env?", "options": ["staging", "prod"]},
            {"id": "days", "type": "number", "text": "Days?", "minimum": 0},
            {
                "id": "concerns",
                "type": "multi_select",
                "text": "Concerns?",
                "options": ["impl", "test", "a, b"],
                "required": False,
            },
            {
                "id": "rulings",
                "type": "triage",
                "text": "Rule findings.",
                "triage_items": [{"id": "r1", "label": "Retry loop"}, {"id": "r2", "label": "Doc"}],
                "dispositions": ["fix", "skip"],
            },
        ],
    }


class TestShorthandLines:
    def test_id_lines_parse(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "env: staging\ndays: 3")
        assert problems == []
        assert answers == {"env": "staging", "days": 3}

    def test_numbered_lines_parse_one_based(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "1: prod\n2: 2.5")
        assert problems == []
        assert answers == {"env": "prod", "days": 2.5}

    def test_bullets_and_equals_accepted(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "- env = staging")
        assert problems == []
        assert answers == {"env": "staging"}

    def test_dotted_triage_lines_kept_for_fold(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "rulings.r1: fix\nrulings.r2: skip")
        assert problems == []
        assert answers == {"rulings.r1": "fix", "rulings.r2": "skip"}
        # And they fold through the validator into the mapping answer.
        resp = collect_form_response(form, {**answers, "env": "staging", "days": 1})
        assert resp.responses["rulings"] == {"r1": "fix", "r2": "skip"}

    def test_multi_select_comma_split_but_exact_option_wins(self) -> None:
        form = form_from_dict(_small_form())
        answers, _ = markdown_to_answers(form, "concerns: impl, test")
        assert answers["concerns"] == ["impl", "test"]
        # A value that IS an option (containing a comma) is not split.
        answers, _ = markdown_to_answers(form, "concerns: a, b")
        assert answers["concerns"] == ["a, b"]

    def test_last_value_wins_deterministically(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "env: staging\nenv: prod")
        assert problems == []
        assert answers["env"] == "prod"

    def test_non_numeric_number_passes_through_for_validator(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "days: soon")
        assert problems == []
        assert answers["days"] == "soon"
        with pytest.raises(FormValidationError, match="expects a number"):
            collect_form_response(
                form, {**answers, "env": "staging", "rulings.r1": "fix", "rulings.r2": "fix"}
            )


class TestNoSilentGuesses:
    def test_unknown_field_named(self) -> None:
        form = form_from_dict(_small_form())
        _, problems = markdown_to_answers(form, "ghost: hi")
        assert problems == ["unknown field: 'ghost'"]

    def test_unknown_number_named(self) -> None:
        form = form_from_dict(_small_form())
        _, problems = markdown_to_answers(form, "9: hi")
        assert problems == ["unknown field number: 9"]

    def test_unparseable_line_named(self) -> None:
        form = form_from_dict(_small_form())
        _, problems = markdown_to_answers(form, "here are my answers!!")
        assert problems == ["unparseable line: 'here are my answers!!'"]

    def test_dotted_key_on_non_triage_named(self) -> None:
        form = form_from_dict(_small_form())
        _, problems = markdown_to_answers(form, "env.x: staging")
        assert problems == ["dotted key on non-triage field: 'env.x'"]

    def test_blank_lines_ignored(self) -> None:
        form = form_from_dict(_small_form())
        _, problems = markdown_to_answers(form, "\n\nenv: staging\n\n")
        assert problems == []


class TestJsonBlock:
    def test_sentinel_payload_block_wins(self) -> None:
        form = form_from_dict(_small_form())
        payload = {WIDGET_RESPONSE_MARKER: True, "answers": {"env": "prod", "days": 1}}
        reply = f"junk line\n```json\n{json.dumps(payload)}\n```"
        answers, problems = markdown_to_answers(form, reply)
        # The JSON block IS the wire format — line noise is irrelevant.
        assert problems == []
        assert answers == {"env": "prod", "days": 1}

    def test_bare_answers_object_accepted(self) -> None:
        form = form_from_dict(_small_form())
        reply = '```json\n{"answers": {"env": "staging"}}\n```'
        answers, problems = markdown_to_answers(form, reply)
        assert (answers, problems) == ({"env": "staging"}, [])

    def test_skeleton_nulls_dropped(self) -> None:
        form = form_from_dict(_small_form())
        md = form_to_markdown(form)
        skeleton = md.split("```json")[1].split("```")[0]
        answers, problems = markdown_to_answers(form, f"```json\n{skeleton}\n```")
        assert problems == []
        assert answers == {}  # untouched skeleton = nothing answered

    def test_invalid_json_block_is_named_then_lines_parse(self) -> None:
        form = form_from_dict(_small_form())
        answers, problems = markdown_to_answers(form, "```json\n{nope\n```\nenv: staging")
        assert "fenced code block is not valid JSON" in problems
        assert answers == {"env": "staging"}


class TestProblemsToMarkdown:
    def test_reasks_only_offending_fields(self) -> None:
        form = form_from_dict(_small_form())
        answers, _ = markdown_to_answers(
            form, "env: nowhere\ndays: 1\nrulings.r1: fix\nrulings.r2: fix"
        )
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(form, answers)
        md = problems_to_markdown(form, exc.value.problems)
        assert "'env' value 'nowhere' not in options" in md
        assert "1. **Env?**" in md  # original position number kept
        assert "Days?" not in md  # validated fields never re-asked
        assert "shorthand works" in md

    def test_unattributable_problems_render_in_header_only(self) -> None:
        form = form_from_dict(_small_form())
        md = problems_to_markdown(form, ["something went sideways"])
        assert "- something went sideways" in md
        assert "**Env?**" not in md

    def test_ac3_bad_option_plus_unknown_id(self) -> None:
        # AC-3 verbatim: one bad option and one unknown id -> both named,
        # exactly the offending field re-rendered.
        form = form_from_dict(_small_form())
        answers, parse_problems = markdown_to_answers(form, "env: nowhere\nghost: hi")
        assert parse_problems == ["unknown field: 'ghost'"]
        with pytest.raises(FormValidationError) as exc:
            collect_form_response(
                form, {**answers, "days": 1, "rulings.r1": "fix", "rulings.r2": "fix"}
            )
        md = problems_to_markdown(form, parse_problems + exc.value.problems)
        assert "unknown field: 'ghost'" in md
        assert "not in options" in md
        assert "1. **Env?**" in md
        assert md.count("**Rule findings.**") == 0  # only env re-asked


class TestReferenceConformance:
    def test_shorthand_reply_round_trips_every_type(self) -> None:
        """R5/AC-1: a typed shorthand reply covering EVERY QuestionType
        parses and validates against the reference form."""
        form = form_from_dict(REFERENCE_FORM)
        reply = "\n".join(
            [
                "feature_name: Dark mode toggle",
                "2: high",  # numbered line for priority
                "concerns: impl, test, docs",
                "needs_migration: No",
                "estimated_days: 3",
                "target_date: 2026-08-01",
                "notes: Ship behind a flag, measure, then widen.",
                "rollout: Ship behind a feature flag",
                "branch_strategy: Short stacked PRs off main",
                "cache_strategy: In-process LRU",
                "finding_rulings.retry-loop: fix now",
                "finding_rulings.stale-doc: ticket",
                "flag_flip_gate: Approve",
                "blockers: Design sign-off",
            ]
        )
        answers, problems = markdown_to_answers(form, reply)
        assert problems == []
        response = collect_form_response(form, answers)
        assert set(response.responses) == set(EXAMPLE_ANSWERS)
        assert response.responses["finding_rulings"] == EXAMPLE_ANSWERS["finding_rulings"]
        assert response.responses["estimated_days"] == 3

    def test_filled_skeleton_round_trips_identically(self) -> None:
        """AC-2: the S4 skeleton, filled and pasted back, validates."""
        form = form_from_dict(REFERENCE_FORM)
        md = form_to_markdown(form)
        skeleton = json.loads(md.split("```json")[1].split("```")[0])
        skeleton["answers"].update(EXAMPLE_ANSWERS)
        reply = f"here you go\n```json\n{json.dumps(skeleton)}\n```"
        answers, problems = markdown_to_answers(form, reply)
        assert problems == []
        response = collect_form_response(form, answers)
        assert set(response.responses) == set(EXAMPLE_ANSWERS)
