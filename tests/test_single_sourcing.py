"""Single-sourcing pins for cross-surface policy constants.

The 0.6.x cleanup batch moved the last policy duplications into
:mod:`attune_forms.models`: the Yes/No boolean vocabulary, the confirm
gate's default options, the recommended-first option ordering, the
rationale callout headers, and the progress status icons. Each was
previously defined per surface with a "matches the widget" comment
nothing enforced. These tests pin the single-sourcing so a
reintroduced local copy (or a surface that stops consuming the shared
one) fails red instead of silently drifting.
"""

from __future__ import annotations

from attune_forms import bridge, form_from_dict, widget
from attune_forms.markdown_surface import form_to_markdown
from attune_forms.models import (
    BOOLEAN_OPTIONS,
    CONFIRM_DEFAULT_OPTIONS,
    PROGRESS_STATUS_ICONS,
    RATIONALE_HEADERS,
    QuestionType,
    recommended_first,
)
from attune_forms.widget import form_to_widget_html


def _form(field: dict) -> dict:
    return {"title": "Single sourcing", "fields": [field]}


class TestNoLocalCopies:
    """The bridge and widget modules must consume the models constants,
    not shadow them — the CHANGELOG's single-sourcing claim was false
    once already (architecture review finding F4a, 2026-08-20)."""

    def test_bridge_has_no_local_confirm_default_options(self) -> None:
        assert not hasattr(bridge, "_CONFIRM_DEFAULT_OPTIONS")

    def test_bridge_boolean_options_is_the_models_constant(self) -> None:
        assert not hasattr(bridge, "_BOOLEAN_OPTIONS")
        assert bridge.BOOLEAN_OPTIONS is BOOLEAN_OPTIONS

    def test_widget_boolean_options_is_the_models_constant(self) -> None:
        assert not hasattr(widget, "_BOOLEAN_OPTIONS")
        assert widget.BOOLEAN_OPTIONS is BOOLEAN_OPTIONS

    def test_confirm_defaults_to_the_shared_options(self) -> None:
        form = form_from_dict(
            _form(
                {"id": "gate", "type": "confirm", "text": "Go?", "consequences": [{"label": "x"}]}
            )
        )
        assert tuple(form.questions[0].options) == CONFIRM_DEFAULT_OPTIONS


class TestRecommendedFirstOrdering:
    """All three surfaces order options through
    :func:`~attune_forms.models.recommended_first`."""

    _DECISION = {
        "id": "route",
        "type": "decision",
        "text": "Which route?",
        "options": ["a", "b", "c"],
        "recommended": "b",
        "rationale": "because",
    }

    def test_helper_moves_the_recommendation_first(self) -> None:
        form = form_from_dict(_form(self._DECISION))
        assert recommended_first(form.questions[0]) == ["b", "a", "c"]

    def test_widget_cards_render_in_helper_order(self) -> None:
        form = form_from_dict(_form(self._DECISION))
        html = form_to_widget_html(form, instance_id="ss")
        positions = [html.index(f'value="{o}"') for o in recommended_first(form.questions[0])]
        assert positions == sorted(positions)

    def test_markdown_options_render_in_helper_order(self) -> None:
        form = form_from_dict(_form(self._DECISION))
        md = form_to_markdown(form)
        positions = [md.index(f"- {o}") for o in recommended_first(form.questions[0])]
        assert positions == sorted(positions)

    def test_ask_fallback_options_are_the_helper_order(self) -> None:
        form = form_from_dict(_form(self._DECISION))
        payload = form.questions[0].to_ask_user_format()
        assert payload["options"] == recommended_first(form.questions[0])


class TestSharedPresentationConstants:
    def test_widget_and_markdown_show_the_same_rationale_header(self) -> None:
        field = {
            "id": "push",
            "type": "pushback",
            "text": "You proposed X.",
            "options": ["X", "Y"],
            "user_position": "X",
            "recommended": "Y",
            "rationale": "Y is safer.",
        }
        form = form_from_dict(_form(field))
        header = RATIONALE_HEADERS[QuestionType.PUSHBACK]
        html = form_to_widget_html(form, instance_id="ss")
        assert widget._esc(header) in html
        assert f"**{header}:**" in form_to_markdown(form)

    def test_widget_and_markdown_show_the_same_progress_icons(self) -> None:
        field = {
            "id": "prog",
            "type": "progress",
            "text": "Status.",
            "options": ["Blocked one"],
            "progress_items": [
                {"label": "Done one", "status": "done"},
                {"label": "Rolling one", "status": "in_flight"},
                {"label": "Blocked one", "status": "blocked"},
            ],
        }
        form = form_from_dict(_form(field))
        html = form_to_widget_html(form, instance_id="ss")
        md = form_to_markdown(form)
        for status in ("done", "in_flight", "blocked"):
            assert PROGRESS_STATUS_ICONS[status] in html
        for status in ("done", "in_flight"):
            assert PROGRESS_STATUS_ICONS[status] in md
