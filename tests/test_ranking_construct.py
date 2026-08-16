"""Tests for the v8 ranking construct (communication grammar member #7).

A RANKING orders the options — optionally only the top ``top_n``. The
answer is an ordered list of option labels: distinct, every entry an
option, exactly ``top_n`` (or all) of them. A ``suggested`` order renders
visibly as a proposal, never as the answer; ``default`` is rejected
(spec D2-c). On flat surfaces it expands to one single-select per rank
slot (``"<id>.<k>"``, D2-b) and folds back in ``collect_form_response``.
Spec: attune-ai docs/specs/ranking-construct/ (roundtable
q-forms-grammar-expansion-001 → chair BACKLOG resp-20260814-211025 →
0.6.0 by chair ruling 2026-08-15; D2 forks ratified the same day).
"""

from __future__ import annotations

import json

import pytest

from attune_forms import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_to_markdown,
    form_to_widget_html,
    markdown_to_answers,
    needs_widget,
    problems_to_markdown,
)
from attune_forms.bridge import form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import FormQuestion, QuestionType, ranking_slot_count

_OPTIONS = ["auth", "billing", "search", "docs"]


def _ranking(**override) -> dict:
    """Build a one-field ranking form dict, overriding the field."""
    field = {
        "id": "prio",
        "text": "Order the work",
        "type": "ranking",
        "options": list(_OPTIONS),
    }
    field.update(override)
    return {"title": "Plan", "fields": [field]}


def _problems(data: dict) -> list[str]:
    with pytest.raises(FormValidationError) as excinfo:
        form_from_dict(data)
    return excinfo.value.problems


class TestRankingModel:
    def test_questiontype_has_ranking(self) -> None:
        assert QuestionType.RANKING.value == "ranking"

    def test_formquestion_top_n_default_none(self) -> None:
        q = FormQuestion(id="a", text="t", type=QuestionType.RANKING, options=["a", "b"])
        assert q.top_n is None
        assert ranking_slot_count(q) == 2

    def test_slot_count_follows_top_n(self) -> None:
        q = FormQuestion(id="a", text="t", type=QuestionType.RANKING, options=_OPTIONS, top_n=2)
        assert ranking_slot_count(q) == 2


class TestRankingFormFromDict:
    def test_builds_full_permutation_form(self) -> None:
        q = form_from_dict(_ranking()).questions[0]
        assert q.type is QuestionType.RANKING
        assert q.top_n is None and q.suggested is None

    def test_builds_top_n_with_suggested_order(self) -> None:
        q = form_from_dict(_ranking(top_n=2, suggested=["search", "auth"])).questions[0]
        assert q.top_n == 2
        assert q.suggested == ["search", "auth"]

    def test_requires_two_unique_options(self) -> None:
        assert any("unique" in p for p in _problems(_ranking(options=["only"])))
        assert any("unique" in p for p in _problems(_ranking(options=["a", "a", "b"])))

    @pytest.mark.parametrize("top_n", [0, 5, -1, True, "2"])
    def test_top_n_bounds_and_type(self, top_n) -> None:
        assert any("'top_n'" in p for p in _problems(_ranking(top_n=top_n)))

    def test_d2c_default_rejected(self) -> None:
        problems = _problems(_ranking(default="auth"))
        assert any("'default' is not permitted on ranking" in p for p in problems)

    def test_suggested_must_be_an_order_of_options(self) -> None:
        assert any("must be a list" in p for p in _problems(_ranking(suggested={"auth": "1"})))
        assert any("not in options" in p for p in _problems(_ranking(suggested=["auth", "x"] * 2)))
        assert any("repeats" in p for p in _problems(_ranking(suggested=["auth"] * 4)))
        assert any("exactly 4" in p for p in _problems(_ranking(suggested=["auth", "docs"])))
        assert any("exactly 2" in p for p in _problems(_ranking(top_n=2, suggested=["auth"])))

    def test_top_n_invalid_on_other_types(self) -> None:
        data = {
            "title": "t",
            "fields": [
                {"id": "s", "type": "single_select", "text": "?", "options": ["a", "b"], "top_n": 1}
            ],
        }
        assert any("only valid on ranking" in p for p in _problems(data))

    def test_dotted_namespace_is_reserved(self) -> None:
        data = _ranking()
        data["fields"].append({"id": "prio.1", "type": "text_input", "text": "x"})
        assert any("dotted answer namespace" in p for p in _problems(data))


class TestRankingAnswer:
    def test_full_permutation_validates(self) -> None:
        form = form_from_dict(_ranking())
        got = collect_form_response(form, {"prio": ["docs", "auth", "search", "billing"]})
        assert got.responses["prio"] == ["docs", "auth", "search", "billing"]

    def test_top_n_list_validates(self) -> None:
        form = form_from_dict(_ranking(top_n=2))
        assert collect_form_response(form, {"prio": ["search", "auth"]}).responses["prio"] == [
            "search",
            "auth",
        ]

    @pytest.mark.parametrize(
        ("value", "needle"),
        [
            (["auth", "billing"], "exactly 4"),
            (["auth", "auth", "billing", "search"], "more than once"),
            (["auth", "billing", "search", "zzz"], "out-of-option"),
            ("auth", "ordered list"),
            ([1, 2, 3, 4], "ordered list"),
        ],
    )
    def test_bad_answers_named(self, value, needle) -> None:
        form = form_from_dict(_ranking())
        with pytest.raises(FormValidationError, match=needle):
            collect_form_response(form, {"prio": value})

    def test_missing_required_named(self) -> None:
        form = form_from_dict(_ranking())
        with pytest.raises(FormValidationError, match="'prio' is required"):
            collect_form_response(form, {"prio": []})

    def test_suggested_is_never_the_answer(self) -> None:
        """A suggested order is a proposal: an empty submit is still
        missing, it does not fall back to the suggestion."""
        form = form_from_dict(_ranking(suggested=["auth", "billing", "search", "docs"]))
        with pytest.raises(FormValidationError, match="required"):
            collect_form_response(form, {})

    def test_dotted_slots_fold_in_slot_order(self) -> None:
        form = form_from_dict(_ranking(top_n=3))
        got = collect_form_response(form, {"prio.3": "auth", "prio.1": "docs", "prio.2": "search"})
        assert got.responses["prio"] == ["docs", "search", "auth"]

    def test_folded_repeat_is_named(self) -> None:
        form = form_from_dict(_ranking(top_n=2))
        with pytest.raises(FormValidationError, match="more than once"):
            collect_form_response(form, {"prio.1": "auth", "prio.2": "auth"})

    def test_routes_to_widget(self) -> None:
        assert needs_widget(form_from_dict(_ranking())) is True


class TestRankingSurfaces:
    def test_widget_renders_pool_and_empty_ranked_list(self) -> None:
        html = form_to_widget_html(form_from_dict(_ranking(top_n=2)), instance_id="r")
        assert 'data-ftype="ranking"' in html
        assert 'data-rank-n="2"' in html
        ranked = html.split('class="ae-rank-ranked"')[1].split("</ol>")[0]
        pool = html.split('class="ae-rank-pool"')[1].split("</ul>")[0]
        assert 'data-opt="' not in ranked
        assert all(f'data-opt="{o}"' in pool for o in _OPTIONS)
        assert "proposed" not in html.split("<script>")[0]

    def test_widget_prefills_suggested_order_as_proposal(self) -> None:
        html = form_to_widget_html(
            form_from_dict(_ranking(top_n=2, suggested=["search", "auth"])), instance_id="r"
        )
        ranked = html.split('class="ae-rank-ranked"')[1].split("</ol>")[0]
        assert ranked.index('data-opt="search"') < ranked.index('data-opt="auth"')
        assert 'class="ae-rank-sug">proposed' in html

    def test_widget_script_reads_ranked_order_and_moves_rows(self) -> None:
        html = form_to_widget_html(form_from_dict(_ranking()), instance_id="r")
        script = html.split("<script>")[1]
        assert "ftype === 'ranking'" in script
        assert ".ae-rank-ranked [data-control]" in script
        for action in ("add", "up", "down", "drop"):
            assert f"'{action}'" in script

    def test_option_text_is_escaped(self) -> None:
        spicy = 'R&D "fast" <path>'
        html = form_to_widget_html(
            form_from_dict(_ranking(options=[spicy, "plain"])), instance_id="r"
        )
        assert "<path>" not in html.split("<script>")[0]
        assert "R&amp;D &quot;fast&quot; &lt;path&gt;" in html

    def test_ask_fallback_is_one_single_select_per_slot(self) -> None:
        payloads = [
            p
            for batch in form_to_askuserquestion(
                form_from_dict(_ranking(top_n=2, suggested=["search", "auth"]))
            )
            for p in batch
        ]
        assert [p["question_id"] for p in payloads] == ["prio.1", "prio.2"]
        assert all(p["type"] == "single_select" for p in payloads)
        assert all(p["options"] == _OPTIONS for p in payloads)
        assert [p["default"] for p in payloads] == ["search", "auth"]
        assert "Rank #1" in payloads[0]["question"]

    def test_single_payload_contract_raises_loudly(self) -> None:
        q = form_from_dict(_ranking()).questions[0]
        with pytest.raises(ValueError, match="to_ask_user_formats"):
            q.to_ask_user_format()

    def test_elicitation_schema_is_bounded_unique_array(self) -> None:
        schema = form_to_elicitation_schema(
            form_from_dict(_ranking(top_n=3, suggested=["auth", "docs", "search"]))
        )
        prop = schema["properties"]["prio"]
        assert prop["type"] == "array"
        assert prop["items"] == {"type": "string", "enum": _OPTIONS}
        assert prop["minItems"] == prop["maxItems"] == 3
        assert prop["uniqueItems"] is True
        assert prop["default"] == ["auth", "docs", "search"]
        assert "prio" in schema["required"]

    def test_markdown_renders_rule_and_skeleton(self) -> None:
        md = form_to_markdown(form_from_dict(_ranking(top_n=2, suggested=["search", "auth"])))
        assert "Rank the top 2, best first (each option once):" in md
        assert "→ proposed order: search, auth" in md
        skeleton = json.loads(md.split("```json")[1].split("```")[0])
        assert skeleton["answers"]["prio"] == ["search", "auth"]

    def test_markdown_full_permutation_has_empty_skeleton(self) -> None:
        md = form_to_markdown(form_from_dict(_ranking()))
        assert "Rank all of these, best first" in md
        skeleton = json.loads(md.split("```json")[1].split("```")[0])
        assert skeleton["answers"]["prio"] == []


class TestRankingIngestion:
    def test_comma_list_in_order(self) -> None:
        form = form_from_dict(_ranking(top_n=3))
        answers, problems = markdown_to_answers(form, "prio: billing, docs, auth")
        assert (answers, problems) == ({"prio": ["billing", "docs", "auth"]}, [])

    def test_leading_ordinals_are_shaping_noise(self) -> None:
        form = form_from_dict(_ranking(top_n=3))
        answers, _ = markdown_to_answers(form, "prio: 1. billing, 2) docs, 3. auth")
        assert answers == {"prio": ["billing", "docs", "auth"]}

    def test_dotted_slots_one_per_line(self) -> None:
        form = form_from_dict(_ranking(top_n=3))
        answers, problems = markdown_to_answers(form, "prio.2: docs\nprio.1: billing\nprio.3: auth")
        assert (answers, problems) == ({"prio": ["billing", "docs", "auth"]}, [])

    def test_bad_slot_is_a_named_problem(self) -> None:
        form = form_from_dict(_ranking(top_n=3))
        _, problems = markdown_to_answers(form, "prio.4: docs")
        assert problems == ["unknown rank slot: 'prio.4'"]

    def test_typed_slot_overrides_pasted_skeleton(self) -> None:
        form = form_from_dict(_ranking(top_n=3, suggested=["auth", "search", "billing"]))
        md = form_to_markdown(form)
        skeleton = md[md.index("```json") :]
        answers, problems = markdown_to_answers(form, skeleton + "\nprio.1: docs")
        assert problems == []
        assert answers["prio"] == ["docs", "search", "billing"]

    def test_bad_ranking_re_asks_only_that_field(self) -> None:
        data = _ranking(top_n=2)
        data["fields"].insert(0, {"id": "name", "type": "text_input", "text": "Name?"})
        form = form_from_dict(data)
        answers, _ = markdown_to_answers(form, "name: x\nprio: auth, auth")
        with pytest.raises(FormValidationError) as excinfo:
            collect_form_response(form, answers)
        re_ask = problems_to_markdown(form, excinfo.value.problems)
        assert "more than once" in re_ask
        assert "**Order the work**" in re_ask
        assert "**Name?**" not in re_ask


_DIGIT_LABELS = ["3.12", "2) legacy", "main"]


class TestReviewFindings:
    """Regressions pinned from the 2026-08-16 five-lens review of this
    construct's diff (four findings confirmed by two skeptics each,
    three more from the unverified pool reproduced by the lead). Report:
    ~/.attune/reports/reviews/ranking-construct-review-2026-08-16.json."""

    def test_exact_digit_leading_labels_ingest_exactly(self) -> None:
        """Confirmed: the ordinal strip ate labels that legitimately
        start "<digits>." / "<digits>)" — "3.12" ingested as "12",
        "2) legacy" as "legacy" — so an EXACT typed ranking failed
        membership and every retry failed identically. The strip now
        applies only when it turns a non-option into an option."""
        form = form_from_dict(
            {
                "title": "V",
                "fields": [
                    {
                        "id": "ver",
                        "text": "Order versions",
                        "type": "ranking",
                        "options": list(_DIGIT_LABELS),
                        "top_n": 2,
                    }
                ],
            }
        )
        # Comma-list path.
        answers, problems = markdown_to_answers(form, "ver: 3.12, 2) legacy")
        assert (answers, problems) == ({"ver": ["3.12", "2) legacy"]}, [])
        # Dotted-slot path.
        answers, problems = markdown_to_answers(form, "ver.1: 3.12\nver.2: main")
        assert (answers, problems) == ({"ver": ["3.12", "main"]}, [])
        # Shaping noise ("1. billing") still strips …
        noisy = form_from_dict(_ranking(top_n=2))
        answers, _ = markdown_to_answers(noisy, "prio: 1. billing, 2) docs")
        assert answers == {"prio": ["billing", "docs"]}
        # … and a genuine miss passes through RAW, named as typed.
        answers, _ = markdown_to_answers(form, "ver: 9. nonsense, main")
        assert answers == {"ver": ["9. nonsense", "main"]}

    @pytest.mark.parametrize("bad_slot", ["prio.3", "prio.0"])
    def test_out_of_range_slots_are_named_not_dropped(self, bad_slot: str) -> None:
        """Confirmed: slot 0 and slots past the budget were silently
        DISCARDED by the fold, so an over-long dotted ranking was
        accepted with ranks missing. Every decimal slot now folds and
        the validator names the wrong length."""
        form = form_from_dict(_ranking(top_n=2))
        raw = {"prio.1": "auth", "prio.2": "docs", bad_slot: "search"}
        with pytest.raises(FormValidationError, match=r"exactly 2 option\(s\) \(got 3\)"):
            collect_form_response(form, raw)

    def test_unicode_digit_slot_never_raises_raw_valueerror(self) -> None:
        """Confirmed: str.isdigit() is True for 95 BMP characters int()
        rejects (², ①, …), so a Unicode-digit suffix raised a RAW
        ValueError out of collect_form_response and the MCP collect tool.
        decimal_key_number() (ASCII-only) now guards all three sites."""
        form = form_from_dict(_ranking(top_n=2))
        # Collect path: not a slot key, ignored like any undeclared key.
        got = collect_form_response(form, {"prio.²": "auth", "prio.1": "docs", "prio.2": "search"})
        assert got.responses["prio"] == ["docs", "search"]
        # Markdown surface: named at parse time, no exception.
        _, problems = markdown_to_answers(form, "prio.²: auth")
        assert problems == ["unknown rank slot: 'prio.²'"]
        # Field-number branch of _resolve_line_key: same guard.
        _, problems = markdown_to_answers(form, "²: auth")
        assert problems == ["unknown field: '²'"]

    def test_quoted_slots_never_override_a_typed_list(self) -> None:
        """Reproduced from the unverified pool: a pasted JSON block's
        dotted rank slots silently overrode a TYPED `prio: …` line,
        inverting the typed-beats-quoted contract. Quoted slots now
        overlay only a quoted base; typed slots still overlay both."""
        form = form_from_dict(_ranking(top_n=3, suggested=["auth", "search", "billing"]))
        typed_plus_quoted_slot = (
            'prio: docs, billing, auth\n```json\n{"answers": {"prio.1": "search"}}\n```'
        )
        answers, problems = markdown_to_answers(form, typed_plus_quoted_slot)
        assert (answers["prio"], problems) == (["docs", "billing", "auth"], [])
        # Quoted slots still overlay a QUOTED base (the pasted skeleton).
        quoted_only = (
            '```json\n{"answers": {"prio": ["auth", "search", "billing"], "prio.1": "docs"}}\n```'
        )
        answers, _ = markdown_to_answers(form, quoted_only)
        assert answers["prio"] == ["docs", "search", "billing"]
        # And a TYPED slot still overlays a quoted base list.
        typed_slot = (
            '```json\n{"answers": {"prio": ["auth", "search", "billing"]}}\n```\nprio.1: docs'
        )
        answers, _ = markdown_to_answers(form, typed_slot)
        assert answers["prio"] == ["docs", "search", "billing"]

    def test_widget_gate_blocks_a_partial_optional_ranking(self) -> None:
        """Reproduced from the unverified pool: an OPTIONAL ranking with
        0 < len < slots posted its partial list, which the validator
        always rejects — after the widget has disabled itself. The
        submit gate now blocks any partial ranking regardless of
        `required`, naming the count ("Order the work (1/2)")."""
        html = form_to_widget_html(
            form_from_dict(_ranking(top_n=2, required=False)), instance_id="r"
        )
        script = html.split("<script>")[1]
        assert "Rank every slot or none: " in script
        assert ".ae-field:not([data-required])" in script
        assert "data-rank-n" in script
