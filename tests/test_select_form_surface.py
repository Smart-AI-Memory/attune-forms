"""Tests for the surface router and its inputs.

Covers ``select_form_surface`` (the host-native-by-default product
router since attune-ai host-surface-parity D15/D16), ``is_trivial_form``
(the mechanical triviality predicate), ``keyboard_mode_enabled`` (the
per-project opt-out), and ``form_response_summary`` (the collapse path).

History: the original default was "cheapest surface that fits"; D21
flipped it to the widget; D15/D16 flipped it again to the host's own
question control for every form the installed host-question profile
admits, with the widget reserved for forms it cannot carry. The
``test_*_routes_to_*`` tests below pin the current default.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attune_forms import (
    collect_form_response,
    form_from_dict,
    form_response_summary,
    is_trivial_form,
    keyboard_mode_enabled,
    needs_widget,
    select_form_surface,
)


def _form(fields: list[dict]) -> object:
    """Build a FormSchema from field dicts."""
    return form_from_dict({"title": "T", "description": "d", "fields": fields})


def _select(**options: object) -> dict:
    """A single_select field with the given overrides."""
    base = {"id": "a", "type": "single_select", "text": "Which?", "options": ["x", "y"]}
    base.update(options)
    return base


@pytest.fixture(autouse=True)
def _isolate_telemetry_and_env(tmp_path, monkeypatch):
    """Keep routing telemetry and the opt-out out of the real home/cwd."""
    monkeypatch.setenv("ATTUNE_HOME", str(tmp_path / "attune-home"))
    monkeypatch.delenv("ATTUNE_KEYBOARD_MODE", raising=False)
    monkeypatch.chdir(tmp_path)


# --------------------------------------------------------------------
# select_form_surface — the host-native default (D15/D16)
# --------------------------------------------------------------------


def test_multi_dimension_expressible_form_routes_to_the_host_control() -> None:
    """D15/D16: a form the host-question profile admits is asked natively.

    Two selects fit one AskUserQuestion call, so the router says ``"ask"``
    even though the widget would render them too. If this returns
    ``"widget"``, the host-native default was reverted.
    """
    form = _form([_select(id="a", text="Which a?"), _select(id="b", text="Which b?")])
    assert needs_widget(form) is False
    assert select_form_surface(form) == "ask"


def test_two_questions_with_identical_text_cannot_be_correlated_and_take_the_widget() -> None:
    """The host keys answers by emitted question text, so identical texts are
    ambiguous; the router sends them to the widget rather than guess."""
    form = _form([_select(id="a"), _select(id="b")])  # both "Which?"
    assert select_form_surface(form) == "widget"


def test_four_options_route_to_the_host_control_and_five_to_the_widget() -> None:
    assert select_form_surface(_form([_select(options=["w", "x", "y", "z"])])) == "ask"
    assert select_form_surface(_form([_select(options=["v", "w", "x", "y", "z"])])) == "widget"


def test_ranking_and_over_cap_triage_route_to_the_widget() -> None:
    ranking = _form(
        [{"id": "r", "type": "ranking", "text": "Order", "options": ["a", "b", "c", "d"]}]
    )
    assert select_form_surface(ranking) == "widget"
    items = [{"id": f"i{k}", "label": f"Item {k}"} for k in range(5)]
    triage = _form(
        [
            {
                "id": "t",
                "type": "triage",
                "text": "Rule",
                "triage_items": items,
                "dispositions": ["apply", "defer"],
            }
        ]
    )
    assert select_form_surface(triage) == "widget"
    assert select_form_surface(_form([{"id": "n", "type": "text_input", "text": "?"}])) == "widget"


def test_trivial_boolean_routes_to_ask() -> None:
    form = _form([{"id": "q", "type": "boolean", "text": "Proceed?"}])
    assert select_form_surface(form) == "ask"


def test_non_widget_client_falls_back_even_for_rich_form() -> None:
    """Capability is a constraint, not a preference — it outranks everything."""
    form = _form([{"id": "n", "type": "number", "text": "How many?"}])
    assert select_form_surface(form, widget_capable=False) == "ask"


def test_keyboard_mode_falls_back_for_expressible_form() -> None:
    form = _form([_select(id="a"), _select(id="b")])
    assert select_form_surface(form, keyboard_mode=True) == "ask"


def test_no_portable_control_outranks_keyboard_mode() -> None:
    """The opt-out must never silently drop a field the surface can't render."""
    for control in ("number", "date", "textarea"):
        form = _form([{"id": "f", "type": control, "text": "?"}])
        assert select_form_surface(form, keyboard_mode=True) == "widget", control


@pytest.mark.parametrize("construct", ["decision", "pushback", "progress"])
def test_constructs_route_to_the_host_control(construct: str) -> None:
    """Decision-shaped constructs are expressible (recommendation-first
    single-select), so under D16 they take the host control by default
    and under keyboard mode alike; only number/date/textarea are
    impossible there.
    """
    field = {
        "id": "d",
        "type": construct,
        "text": "Which approach?",
        "options": ["x", "y"],
        "recommended": "x",
    }
    if construct == "progress":
        # A progress form reports items by status; the blocked subset's
        # labels must equal ``options``.
        field["progress_items"] = [
            {"label": "done thing", "status": "done"},
            {"label": "x", "status": "blocked"},
            {"label": "y", "status": "blocked"},
        ]
    form = _form([field])
    assert select_form_surface(form) == "ask"
    assert select_form_surface(form, keyboard_mode=True) == "ask"


# --------------------------------------------------------------------
# is_trivial_form — the narrow exemption
# --------------------------------------------------------------------


def test_trivial_requires_single_question() -> None:
    assert is_trivial_form(_form([_select(id="a")])) is True
    assert is_trivial_form(_form([_select(id="a"), _select(id="b")])) is False


def test_trivial_rejects_more_than_three_options() -> None:
    assert is_trivial_form(_form([_select(options=["a", "b", "c"])])) is True
    assert is_trivial_form(_form([_select(options=["a", "b", "c", "d"])])) is False


def test_long_option_label_is_not_trivial() -> None:
    """Long labels mean tradeoffs were folded into the text — that wants a card."""
    assert is_trivial_form(_form([_select(options=["ok", "x" * 121])])) is False
    assert is_trivial_form(_form([_select(options=["ok", "x" * 120])])) is True


def test_multi_select_is_not_trivial() -> None:
    field = {"id": "m", "type": "multi_select", "text": "Which?", "options": ["a"]}
    assert is_trivial_form(_form([field])) is False


# --------------------------------------------------------------------
# keyboard_mode_enabled — per-project, env override
# --------------------------------------------------------------------


def test_keyboard_mode_defaults_off(tmp_path: Path) -> None:
    assert keyboard_mode_enabled(tmp_path) is False


def test_keyboard_mode_reads_project_config(tmp_path: Path) -> None:
    (tmp_path / "attune.config.json").write_text(json.dumps({"keyboard_mode": True}))
    assert keyboard_mode_enabled(tmp_path) is True


def test_env_overrides_project_config_both_directions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "attune.config.json").write_text(json.dumps({"keyboard_mode": True}))
    monkeypatch.setenv("ATTUNE_KEYBOARD_MODE", "0")
    assert keyboard_mode_enabled(tmp_path) is False
    monkeypatch.setenv("ATTUNE_KEYBOARD_MODE", "1")
    assert keyboard_mode_enabled(tmp_path) is True


def test_malformed_project_config_is_not_an_error(tmp_path: Path) -> None:
    """Routing must never fail because a config file is bad."""
    (tmp_path / "attune.config.json").write_text("{not json")
    assert keyboard_mode_enabled(tmp_path) is False


# --------------------------------------------------------------------
# form_response_summary — the collapse path
# --------------------------------------------------------------------


def test_response_summary_renders_answers_and_omits_unanswered() -> None:
    form = _form(
        [
            _select(id="scope", text="Which path?", options=["src", "tests"]),
            {
                "id": "concerns",
                "type": "multi_select",
                "text": "Which concerns?",
                "options": ["impl", "docs"],
                "required": False,
            },
            {"id": "skipped", "type": "text_input", "text": "Notes?", "required": False},
        ]
    )
    response = collect_form_response(form, {"scope": "src", "concerns": ["impl", "docs"]})
    summary = form_response_summary(form, response)

    assert "Which path?: **src**" in summary
    assert "Which concerns?: **impl, docs**" in summary
    assert "Notes?" not in summary  # unanswered questions are omitted
    assert summary.count("\n") == 2  # title + 2 answered bullets


# --------------------------------------------------------------------
# the decay receipt
# --------------------------------------------------------------------


def test_routing_decisions_are_logged_and_readable() -> None:
    """Non-mocked round trip: route -> persist -> read back the mix."""
    from attune_forms.form_events import surface_mix

    rich = _form([{"id": "n", "type": "number", "text": "How many?"}])
    native = _form([_select(id="a", text="Which a?"), _select(id="b", text="Which b?")])

    select_form_surface(rich)
    select_form_surface(rich)
    select_form_surface(native)

    assert surface_mix() == {"widget": 2, "ask": 1}


def test_telemetry_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from attune_forms.form_events import surface_mix

    monkeypatch.setenv("ATTUNE_FORM_TELEMETRY", "0")
    select_form_surface(_form([_select(id="a"), _select(id="b")]))
    assert surface_mix() == {}


# --------------------------------------------------------------------
# the opt-out's affordance — reachable and discoverable (D17)
# --------------------------------------------------------------------
#
# The mechanism shipping without these is how D17 sat unbuilt for a
# month: every seat called the opt-out "essential", and an opt-out
# nobody can find is not one.


def test_set_keyboard_mode_round_trips(tmp_path: Path) -> None:
    from attune_forms import set_keyboard_mode

    set_keyboard_mode(True, tmp_path)
    assert keyboard_mode_enabled(tmp_path) is True
    set_keyboard_mode(False, tmp_path)
    assert keyboard_mode_enabled(tmp_path) is False


def test_set_keyboard_mode_preserves_other_settings(tmp_path: Path) -> None:
    """Writing one key must not eat the user's other config."""
    from attune_forms import set_keyboard_mode

    (tmp_path / "attune.config.json").write_text(json.dumps({"project_name": "attune", "tier": 3}))
    set_keyboard_mode(True, tmp_path)

    data = json.loads((tmp_path / "attune.config.json").read_text())
    assert data == {"project_name": "attune", "tier": 3, "keyboard_mode": True}


def test_set_keyboard_mode_refuses_to_clobber_bad_json(tmp_path: Path) -> None:
    """Malformed config raises — overwriting would silently lose data."""
    from attune_forms import set_keyboard_mode

    (tmp_path / "attune.config.json").write_text("{not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        set_keyboard_mode(True, tmp_path)


def test_keyboard_hint_fires_once_at_the_threshold() -> None:
    from attune_forms.form_events import (
        _HINT_AFTER_SUBMISSIONS,
        log_submission,
        maybe_keyboard_hint,
    )

    for _ in range(_HINT_AFTER_SUBMISSIONS - 1):
        log_submission()
        assert maybe_keyboard_hint() is None  # not yet earned

    log_submission()
    assert maybe_keyboard_hint() is not None  # earned

    log_submission()
    assert maybe_keyboard_hint() is None  # and never again


def test_keyboard_hint_never_fires_for_users_already_opted_in() -> None:
    from attune_forms.form_events import (
        _HINT_AFTER_SUBMISSIONS,
        log_submission,
        maybe_keyboard_hint,
    )

    for _ in range(_HINT_AFTER_SUBMISSIONS + 5):
        log_submission()
    assert maybe_keyboard_hint(keyboard_mode=True) is None
