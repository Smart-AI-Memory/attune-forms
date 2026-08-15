"""Tests for the v8 assumption-review construct (grammar member #8).

An ASSUMPTION_REVIEW lists the assumptions the agent INFERRED from
context and the user rules each one from the FIXED vocabulary accept /
edit / reject, supplying replacement text for an edit. The answer is
``{item key: "accept" | "reject" | {"edit": text}}`` — the triage
mapping plus an edit lane (spec D2-c); ``suggested`` may pre-mark
``accept`` only (D2-b); ``default`` and ``dispositions`` are rejected
(D2-a). Flat surfaces expand to one single-select per item paired with
an optional ``"<id>.<key>.text"`` question; the fold enforces
text-iff-edit. Spec: attune-ai docs/specs/assumption-review-construct/
(roundtable q-forms-grammar-expansion-001 → chair BACKLOG
resp-20260814-211025 → 0.6.0 by chair ruling 2026-08-15).
"""

from __future__ import annotations

import json

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_response_summary,
    form_to_markdown,
    form_to_widget_html,
    markdown_to_answers,
    needs_widget,
    problems_to_markdown,
)
from attune_forms.bridge import form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import ASSUMPTION_RULINGS, FormQuestion, QuestionType

_ITEMS = [
    {"id": "py", "label": "Python 3.10+ is the floor", "source": "pyproject.toml"},
    {"id": "host", "label": "Claude Code is the only host", "detail": "manifest names it"},
    {"label": "Tests run in CI"},
]
_KEYS = ["py", "host", "Tests run in CI"]


def _review(**override) -> dict:
    field = {
        "id": "assume",
        "text": "I inferred these — rule each",
        "type": "assumption_review",
        "assumptions": [dict(it) for it in _ITEMS],
    }
    field.update(override)
    return {"title": "Scope", "fields": [field]}


def _problems(data: dict) -> list[str]:
    with pytest.raises(FormValidationError) as excinfo:
        form_from_dict(data)
    return excinfo.value.problems


_GOOD = {"py": "accept", "host": {"edit": "Claude Code + Codex CLI"}, "Tests run in CI": "reject"}


class TestModel:
    def test_questiontype_and_fixed_vocabulary(self) -> None:
        assert QuestionType.ASSUMPTION_REVIEW.value == "assumption_review"
        assert ASSUMPTION_RULINGS == ("accept", "edit", "reject")

    def test_formquestion_assumptions_default_none(self) -> None:
        q = FormQuestion(id="a", text="t", type=QuestionType.ASSUMPTION_REVIEW)
        assert q.assumptions is None


class TestFormFromDict:
    def test_builds(self) -> None:
        q = form_from_dict(_review(suggested={"py": "accept"})).questions[0]
        assert q.type is QuestionType.ASSUMPTION_REVIEW
        assert [it["label"] for it in q.assumptions] == [it["label"] for it in _ITEMS]
        assert q.suggested == {"py": "accept"}

    def test_requires_nonempty_assumptions(self) -> None:
        data = _review()
        del data["fields"][0]["assumptions"]
        assert any("requires 'assumptions'" in p for p in _problems(data))
        assert any("non-empty" in p for p in _problems(_review(assumptions=[])))

    def test_items_need_labels_and_unique_keys(self) -> None:
        assert any("needs a 'label'" in p for p in _problems(_review(assumptions=[{"id": "x"}])))
        dupes = [{"label": "same"}, {"label": "same"}]
        assert any("duplicate key" in p for p in _problems(_review(assumptions=dupes)))
        assert any(
            "must be a string" in p
            for p in _problems(_review(assumptions=[{"label": "a", "source": 1}]))
        )

    def test_key_may_not_end_with_text_suffix(self) -> None:
        problems = _problems(_review(assumptions=[{"id": "x.text", "label": "a"}]))
        assert any("reserved for the edit-text lane" in p for p in problems)

    def test_d2a_dispositions_rejected(self) -> None:
        problems = _problems(_review(dispositions=["accept", "reject"]))
        assert len([p for p in problems if "dispositions" in p]) == 1
        assert any("vocabulary is fixed" in p for p in problems)

    def test_default_rejected(self) -> None:
        assert any("'default' is not permitted" in p for p in _problems(_review(default="accept")))

    def test_d2b_suggested_accept_only(self) -> None:
        assert any("'accept' only" in p for p in _problems(_review(suggested={"py": "edit"})))
        assert any("'accept' only" in p for p in _problems(_review(suggested={"py": "reject"})))
        assert any(
            "not in assumption keys" in p for p in _problems(_review(suggested={"zz": "accept"}))
        )
        assert any("must be a map" in p for p in _problems(_review(suggested=["py"])))

    def test_assumptions_invalid_on_other_types(self) -> None:
        data = {
            "title": "t",
            "fields": [
                {
                    "id": "s",
                    "type": "single_select",
                    "text": "?",
                    "options": ["a", "b"],
                    "assumptions": [{"label": "x"}],
                }
            ],
        }
        assert any("only valid on assumption_review" in p for p in _problems(data))

    def test_dotted_namespace_is_reserved(self) -> None:
        data = _review()
        data["fields"].append({"id": "assume.host", "type": "text_input", "text": "x"})
        assert any("dotted answer namespace" in p for p in _problems(data))


class TestAnswer:
    def test_mixed_rulings_validate(self) -> None:
        form = form_from_dict(_review())
        assert collect_form_response(form, {"assume": _GOOD}).responses["assume"] == _GOOD

    @pytest.mark.parametrize(
        ("rulings", "needle"),
        [
            ({**_GOOD, "host": {"edit": "   "}}, "edit needs replacement text"),
            ({**_GOOD, "host": "edit"}, "edit needs replacement text"),
            ({**_GOOD, "host": {"edit": "x", "note": "y"}}, "invalid ruling"),
            ({**_GOOD, "py": "maybe"}, "invalid ruling"),
            ({**_GOOD, "zz": "accept"}, "unknown assumption"),
            ({"py": "accept"}, "missing ruling"),
            ("accept", "expects a mapping"),
        ],
    )
    def test_bad_answers_named(self, rulings, needle) -> None:
        form = form_from_dict(_review())
        with pytest.raises(FormValidationError, match=needle):
            collect_form_response(form, {"assume": rulings})

    def test_partial_rulings_allowed_when_optional(self) -> None:
        form = form_from_dict(_review(required=False))
        assert collect_form_response(form, {"assume": {"py": "accept"}}).responses["assume"] == {
            "py": "accept"
        }

    def test_suggested_is_never_the_answer(self) -> None:
        form = form_from_dict(_review(suggested={"py": "accept"}))
        with pytest.raises(FormValidationError, match="required"):
            collect_form_response(form, {})

    def test_dotted_keys_fold_with_paired_text(self) -> None:
        form = form_from_dict(_review())
        got = collect_form_response(
            form,
            {
                "assume.py": "accept",
                "assume.host": "edit",
                "assume.host.text": "Claude Code + Codex CLI",
                "assume.Tests run in CI": "reject",
                "assume.py.text": "ignored — ruling is accept",
            },
        )
        assert got.responses["assume"] == _GOOD

    def test_folded_edit_without_text_is_named(self) -> None:
        form = form_from_dict(_review())
        with pytest.raises(FormValidationError, match="edit needs replacement text"):
            collect_form_response(
                form,
                {"assume.py": "accept", "assume.host": "edit", "assume.Tests run in CI": "reject"},
            )

    def test_summary_shows_edit_text(self) -> None:
        form = form_from_dict(_review())
        response = collect_form_response(form, {"assume": _GOOD})
        summary = form_response_summary(form, response)
        assert "host: edit → Claude Code + Codex CLI" in summary
        assert "py: accept" in summary

    def test_routes_to_widget(self) -> None:
        assert needs_widget(form_from_dict(_review())) is True


class TestSurfaces:
    def test_widget_rows_fixed_vocabulary_edit_box_and_suggested_mark(self) -> None:
        html = form_to_widget_html(
            form_from_dict(_review(suggested={"py": "accept"})), instance_id="a"
        )
        body = html.split("</style>")[1].split("<script>")[0]
        assert 'data-ftype="assumption_review"' in body
        assert body.count("data-assume-row") == 3
        for ruling in ASSUMPTION_RULINGS:
            assert f'data-assume="{ruling}"' in body
        assert body.count("ae-assume-edit") == 3
        assert body.count('class="ae-triage-sug">suggested') == 1
        assert "from pyproject.toml" in body
        assert 'value="Python 3.10+ is the floor"' in body  # edit box pre-filled with the label

    def test_widget_script_reads_rulings_and_reveals_edit(self) -> None:
        html = form_to_widget_html(form_from_dict(_review()), instance_id="a")
        script = html.split("<script>")[1]
        assert "ftype === 'assumption_review'" in script
        assert "ae-assume-editing" in script
        assert "edit: (t ? t.value : '')" in script

    def test_label_text_is_escaped(self) -> None:
        spicy = 'R&D "fast" <path>'
        html = form_to_widget_html(
            form_from_dict(_review(assumptions=[{"label": spicy}])), instance_id="a"
        )
        assert "<path>" not in html.split("<script>")[0]
        assert "R&amp;D &quot;fast&quot; &lt;path&gt;" in html

    def test_ask_fallback_pairs_each_item_with_a_text_question(self) -> None:
        payloads = [
            p
            for batch in form_to_askuserquestion(
                form_from_dict(_review(suggested={"py": "accept"}))
            )
            for p in batch
        ]
        ids = [p["question_id"] for p in payloads]
        assert ids == [
            "assume.py",
            "assume.py.text",
            "assume.host",
            "assume.host.text",
            "assume.Tests run in CI",
            "assume.Tests run in CI.text",
        ]
        assert payloads[0]["options"] == list(ASSUMPTION_RULINGS)
        assert payloads[0]["default"] == "accept"
        assert payloads[1]["type"] == "text_input"
        assert payloads[2]["default"] is None

    def test_single_payload_contract_raises_loudly(self) -> None:
        q = form_from_dict(_review()).questions[0]
        with pytest.raises(ValueError, match="to_ask_user_formats"):
            q.to_ask_user_format()

    def test_elicitation_schema_flattens_with_optional_text(self) -> None:
        schema = form_to_elicitation_schema(form_from_dict(_review(suggested={"py": "accept"})))
        props = schema["properties"]
        assert props["assume.py"] == {
            "title": "I inferred these — rule each — Python 3.10+ is the floor",
            "type": "string",
            "enum": list(ASSUMPTION_RULINGS),
            "description": "pyproject.toml",
            "default": "accept",
        }
        assert props["assume.host.text"]["type"] == "string"
        assert set(schema["required"]) == {"assume.py", "assume.host", "assume.Tests run in CI"}

    def test_markdown_renders_rule_rows_and_skeleton(self) -> None:
        md = form_to_markdown(form_from_dict(_review(suggested={"py": "accept"})))
        assert "Rule each assumption: `accept` / `edit: <replacement text>` / `reject`" in md
        assert "**Python 3.10+ is the floor** *(from pyproject.toml)* → suggested: `accept`" in md
        assert "**Claude Code is the only host** — manifest names it" in md
        skeleton = json.loads(md.split("```json")[1].split("```")[0])
        assert skeleton["answers"]["assume"] == {
            "py": "accept",
            "host": None,
            "Tests run in CI": None,
        }


class TestIngestion:
    def test_shorthand_rulings_including_edit_text(self) -> None:
        form = form_from_dict(_review())
        answers, problems = markdown_to_answers(
            form,
            "assume.py: accept\nassume.host: edit: Claude Code + Codex CLI\nassume.Tests run in CI: reject",
        )
        assert problems == []
        assert collect_form_response(form, answers).responses["assume"] == _GOOD

    def test_bare_edit_shapes_to_empty_edit_and_is_named(self) -> None:
        form = form_from_dict(_review())
        answers, problems = markdown_to_answers(form, "assume.host: edit")
        assert (answers, problems) == ({"assume.host": {"edit": ""}}, [])
        with pytest.raises(FormValidationError, match="edit needs replacement text"):
            collect_form_response(
                form, {**answers, "assume.py": "accept", "assume.Tests run in CI": "reject"}
            )

    def test_typed_text_lane_pairs_with_bare_edit(self) -> None:
        form = form_from_dict(_review())
        answers, _ = markdown_to_answers(
            form,
            "assume.py: accept\nassume.host: edit\nassume.host.text: CC + Codex\nassume.Tests run in CI: reject",
        )
        assert collect_form_response(form, answers).responses["assume"]["host"] == {
            "edit": "CC + Codex"
        }

    def test_unknown_assumption_is_a_named_problem(self) -> None:
        form = form_from_dict(_review())
        _, problems = markdown_to_answers(form, "assume.zz: accept")
        assert problems == ["unknown assumption: 'assume.zz'"]

    def test_typed_rows_override_pasted_skeleton(self) -> None:
        form = form_from_dict(_review(suggested={"py": "accept"}))
        md = form_to_markdown(form)
        skeleton = md[md.index("```json") :]
        answers, problems = markdown_to_answers(
            form,
            skeleton
            + "\nassume.py: reject\nassume.host: edit: CC + Codex\nassume.Tests run in CI: accept",
        )
        assert problems == []
        assert answers == {
            "assume": {"py": "reject", "host": {"edit": "CC + Codex"}, "Tests run in CI": "accept"}
        }

    def test_text_for_non_edit_ruling_is_dropped_on_merge(self) -> None:
        form = form_from_dict(_review(suggested={"py": "accept"}))
        md = form_to_markdown(form)
        skeleton = md[md.index("```json") :]
        answers, _ = markdown_to_answers(
            form,
            skeleton
            + "\nassume.py.text: stray\nassume.host: reject\nassume.Tests run in CI: reject",
        )
        assert answers["assume"]["py"] == "accept"
        assert "py.text" not in answers["assume"]

    def test_bad_review_re_asks_only_that_field(self) -> None:
        data = _review()
        data["fields"].insert(0, {"id": "name", "type": "text_input", "text": "Name?"})
        form = form_from_dict(data)
        answers, _ = markdown_to_answers(
            form, "name: x\nassume.py: accept\nassume.host: edit\nassume.Tests run in CI: reject"
        )
        with pytest.raises(FormValidationError) as excinfo:
            collect_form_response(form, answers)
        re_ask = problems_to_markdown(form, excinfo.value.problems)
        assert "edit needs replacement text" in re_ask
        assert "**I inferred these — rule each**" in re_ask
        assert "**Name?**" not in re_ask


class TestReviewFindings:
    """Regressions pinned from the 2026-08-15 five-lens review of this
    construct (one confirmed by two skeptics, four verified by the lead
    after the skeptic pool hit its usage limit)."""

    def test_bad_ruling_does_not_re_ask_a_sibling_field_named_edit(self) -> None:
        """Confirmed: the validator's vocabulary hint must not be
        single-quoted, and the re-ask must attribute by the leading id
        only — otherwise a sibling field named edit / accept / reject is
        re-asked for this board's problem (markdown-ingestion R2)."""
        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {"id": "edit", "type": "text_input", "text": "Anything to edit?"},
                    {"id": "accept", "type": "boolean", "text": "Accept the terms?"},
                    {
                        "id": "assume",
                        "type": "assumption_review",
                        "text": "Rule these",
                        "assumptions": [
                            {"id": "py", "label": "Py"},
                            {"id": "host", "label": "Host"},
                        ],
                    },
                ],
            }
        )
        answers, _ = markdown_to_answers(
            form, "edit: nothing\naccept: Yes\nassume.py: accept\nassume.host: edited"
        )
        with pytest.raises(FormValidationError) as excinfo:
            collect_form_response(form, answers)
        re_ask = problems_to_markdown(form, excinfo.value.problems)
        assert "**Rule these**" in re_ask
        assert "**Anything to edit?**" not in re_ask
        assert "**Accept the terms?**" not in re_ask
        # A bare edit (the other message carrying the hint) — same guarantee.
        answers, _ = markdown_to_answers(
            form, "edit: nothing\naccept: Yes\nassume.py: accept\nassume.host: edit"
        )
        with pytest.raises(FormValidationError) as excinfo:
            collect_form_response(form, answers)
        assert "**Anything to edit?**" not in problems_to_markdown(form, excinfo.value.problems)

    def test_widget_gate_treats_blank_edit_as_unanswered(self) -> None:
        """Verified: an edit with no replacement text must be stopped by
        the widget's required gate — never posted for the validator to
        reject after the widget has disabled itself."""
        html = form_to_widget_html(form_from_dict(_review()), instance_id="a")
        gate = html.split("Required-field gate")[1]
        assert "blankEdit" in gate
        assert "String(r.edit || '').trim()" in gate

    def test_duplicate_labels_rejected_even_with_distinct_ids(self) -> None:
        """Verified (R1: labels unique): two identical rows are
        indistinguishable to the user whatever their ids."""
        problems = _problems(
            _review(assumptions=[{"id": "x", "label": "Same"}, {"id": "y", "label": "Same"}])
        )
        assert any("duplicate label 'Same'" in p for p in problems)

    def test_json_reply_accepts_the_edit_colon_text_form(self) -> None:
        """Verified: the rendered rule line teaches `edit: <text>`, so a
        JSON-skeleton reply using that string form must shape exactly as
        the shorthand path does — same regex, never a guess."""
        form = form_from_dict(_review())
        answers, problems = markdown_to_answers(
            form,
            '```json\n{"answers": {"assume": {"py": "accept", "host": "edit: CC + Codex", '
            '"Tests run in CI": "reject"}}}\n```',
        )
        assert problems == []
        assert collect_form_response(form, answers).responses["assume"]["host"] == {
            "edit": "CC + Codex"
        }
        # dotted per-item JSON keys shape the same way; the text lane never does
        answers, _ = markdown_to_answers(
            form,
            '```json\n{"answers": {"assume.host": "edit: via dotted", "assume.py.text": "edit: raw"}}\n```',
        )
        assert answers == {"assume.host": {"edit": "via dotted"}, "assume.py.text": "edit: raw"}

    def test_json_edit_null_is_named_not_dropped(self) -> None:
        """Verified as NOT a defect (kept for the record): {"edit": null}
        survives the skeleton null-strip and the validator names it."""
        form = form_from_dict(_review())
        answers, problems = markdown_to_answers(
            form,
            '```json\n{"answers": {"assume": {"py": "accept", "host": {"edit": null}, '
            '"Tests run in CI": "reject"}}}\n```',
        )
        assert problems == []
        with pytest.raises(FormValidationError, match="edit needs replacement text"):
            collect_form_response(form, answers)

    def test_inline_edit_text_beats_text_lane_with_and_without_skeleton(self) -> None:
        """Verified: the merge and the fold agree — a text lane fills an
        EMPTY edit; inline `edit: <text>` wins otherwise, whether or not a
        suggested-carrying skeleton was pasted."""
        form = form_from_dict(_review(suggested={"py": "accept"}))
        typed = "assume.py: accept\nassume.host: edit: inline\nassume.host.text: lane\nassume.Tests run in CI: reject"
        answers, _ = markdown_to_answers(form, typed)
        assert collect_form_response(form, answers).responses["assume"]["host"] == {
            "edit": "inline"
        }
        md = form_to_markdown(form)
        answers, _ = markdown_to_answers(form, md[md.index("```json") :] + "\n" + typed)
        assert collect_form_response(form, answers).responses["assume"]["host"] == {
            "edit": "inline"
        }
        # and the lane still fills a bare edit on both paths
        typed_bare = typed.replace("edit: inline", "edit")
        answers, _ = markdown_to_answers(form, md[md.index("```json") :] + "\n" + typed_bare)
        assert collect_form_response(form, answers).responses["assume"]["host"] == {"edit": "lane"}
