"""Declarative-form → ``show_widget`` HTML renderer (elicitation v2 / S1).

The "escape hatch" surface from decision D8: render the SAME declarative
artifact (D3) as an inline HTML form for the ``mcp__visualize__show_widget``
tool. Unlike the AskUserQuestion bridge (v1) and native MCP elicitation
(v2 lead surface), this surface renders the v2.1 rich controls
(``number``/``date``/``textarea`` with real spinner/date-picker/multiline
widgets) and is the home for controls no other surface can express.

Return path (the S1-specific shape — D4/D8): the widget has no structured
callback, only the global ``sendPrompt(text)``. On submit it serializes the
answers to JSON inside a sentinel-marked message; the agent parses that and
re-uses the existing :func:`attune_forms.collect_form_response`
validation seam (R4). This module owns ONLY the pure
``FormSchema -> html`` transform — no agent or tool dependency — so it is
fully testable.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from html import escape

from attune_forms.bridge import is_fully_inferred
from attune_forms.form_events import log_form_rendered
from attune_forms.models import (
    ASSUMPTION_RULINGS,
    BOOLEAN_OPTIONS,
    PROGRESS_STATUS_ICONS,
    RATIONALE_HEADERS,
    FormQuestion,
    FormSchema,
    QuestionType,
    confirm_consequences,
    endorsement_map,
    expansion_items,
    ranking_slot_count,
    recommended_first,
    suggested_pick,
)
from attune_forms.theme import CSS_BASE as _CSS_BASE
from attune_forms.theme import CSS_FAMILIES as _CSS_FAMILIES

#: Sentinel key the submit payload carries so the agent can recognise a
#: form postback among ordinary chat messages and route it to
#: ``collect_form_response``. Kept in sync with the ``elicit`` skill.
WIDGET_RESPONSE_MARKER = "__elicitation_response__"


def _esc(value: object) -> str:
    """HTML-escape a value for safe use in text or a quoted attribute."""
    return escape(str(value), quote=True)


def _list_html(q: FormQuestion, *, multi: bool) -> str:
    """Render select options as an ordered/unordered selectable list.

    A presentation variant of SINGLE_SELECT (radios) / MULTI_SELECT
    (checkboxes) used when ``q.list_style`` is set: the items render as
    ``<ol>``/``<ul>`` entries, each pickable by mouse or keyboard. The
    answer path is unchanged — the inputs still carry ``data-control`` and
    the submit script reads them the same way it reads any select.

    Args:
        q: The select question to render.
        multi: True for MULTI_SELECT (checkboxes), False for SINGLE_SELECT
            (radios).

    Returns:
        An HTML fragment for the list control.
    """
    tag = "ol" if q.list_style == "ordered" else "ul"
    input_type = "checkbox" if multi else "radio"
    name = "" if multi else f' name="{_esc(q.id)}"'
    role = "" if multi else ' role="radiogroup"'
    items = ""
    for opt in q.options:
        items += (
            f'<li class="ae-list-item"><label>'
            f'<input type="{input_type}"{name} data-control '
            f'value="{_esc(opt)}"{_checked(q, opt)}> '
            f"<span>{_esc(opt)}</span></label></li>"
        )
    return f'<{tag} class="ae-list"{role}>{items}</{tag}>'


def _control_decision_html(q: FormQuestion) -> str:
    """Render a DECISION control: recommended-first cards with notes."""
    notes = q.option_notes or {}
    cards = ""
    for opt in recommended_first(q):
        is_rec = opt == q.recommended
        badge = '<span class="ae-rec-badge">Recommended</span>' if is_rec else ""
        note = f'<span class="ae-card-note">{_esc(notes[opt])}</span>' if opt in notes else ""
        checked = " checked" if q.default == opt else ""
        cls = "ae-card ae-card-rec" if is_rec else "ae-card"
        cards += (
            f'<label class="{cls}">'
            f'<input type="radio" name="{_esc(q.id)}" data-control '
            f'value="{_esc(opt)}"{checked}>'
            f'{badge}<span class="ae-card-title">{_esc(opt)}</span>{note}</label>'
        )
    return f'<div class="ae-cards" role="radiogroup">{cards}</div>'


def _control_pushback_html(q: FormQuestion) -> str:
    """Render a PUSHBACK control.

    Dissent framing: the agent's alternative (``recommended``) is badged
    "I'd suggest instead" and ordered first; the user's stated approach
    (``user_position``) carries a muted "your approach" tag. Same radio
    answer path as DECISION.
    """
    notes = q.option_notes or {}
    cards = ""
    for opt in recommended_first(q):
        is_rec = opt == q.recommended
        is_user = opt == q.user_position
        badge = '<span class="ae-rec-badge">I&#x27;d suggest instead</span>' if is_rec else ""
        tag = '<span class="ae-yours-tag">your approach</span>' if is_user else ""
        note = f'<span class="ae-card-note">{_esc(notes[opt])}</span>' if opt in notes else ""
        checked = " checked" if q.default == opt else ""
        cls = "ae-card ae-card-rec" if is_rec else "ae-card"
        cards += (
            f'<label class="{cls}">'
            f'<input type="radio" name="{_esc(q.id)}" data-control '
            f'value="{_esc(opt)}"{checked}>'
            f'{badge}{tag}<span class="ae-card-title">{_esc(opt)}</span>{note}</label>'
        )
    return f'<div class="ae-cards" role="radiogroup">{cards}</div>'


def _control_progress_report_html(q: FormQuestion) -> str:
    """Render PROGRESS in v5.1 "report" style: a neutral digest.

    Item status is a free-form category tag (no task semantics, no
    strikethrough); items named in options render as pickable "go
    deeper" cards, the rest as static tagged rows. Same radio answer
    path as the default style.
    """
    items = q.progress_items or []
    notes = q.option_notes or {}
    by_label = {it.get("label"): it for it in items}
    rows = ""
    for it in items:
        if it.get("label") in q.options:
            continue
        tag = f'<span class="ae-prog-tag">{_esc(it.get("status", ""))}</span>'
        detail = _detail_html(it["detail"], "ae-prog-detail") if it.get("detail") else ""
        rows += (
            f'<div class="ae-prog-row ae-prog-report">'
            f'{tag}<span class="ae-prog-label">{_esc(it.get("label", ""))}</span>'
            f"{detail}</div>"
        )
    cards = ""
    for opt in recommended_first(q):
        it = by_label.get(opt, {})
        is_rec = opt == q.recommended
        badge = '<span class="ae-rec-badge">suggested next</span>' if is_rec else ""
        tag = f'<span class="ae-prog-tag">{_esc(it.get("status", ""))}</span>'
        note_text = notes.get(opt) or it.get("detail")
        note = f'<span class="ae-card-note">{_esc(note_text)}</span>' if note_text else ""
        checked = " checked" if q.default == opt else ""
        cls = "ae-card ae-card-rec" if is_rec else "ae-card"
        cards += (
            f'<label class="{cls}">'
            f'<input type="radio" name="{_esc(q.id)}" data-control '
            f'value="{_esc(opt)}"{checked}>'
            f'{badge}{tag}<span class="ae-card-title">{_esc(opt)}</span>{note}</label>'
        )
    picker = (
        '<div class="ae-prog-blocked-h">Pick one to go deeper:</div>'
        f'<div class="ae-cards" role="radiogroup">{cards}</div>'
        if cards
        else ""
    )
    rows_html = f'<div class="ae-prog-rows">{rows}</div>' if rows else ""
    return f'<div class="ae-progress">{rows_html}{picker}</div>'


def _control_progress_html(q: FormQuestion) -> str:
    """Render PROGRESS in the default task style.

    Done/in_flight items render as static rows; the blocked items
    become the radiogroup picker (recommended first, "suggested next"
    badge). With no blocked items the picker is omitted and the
    control is a pure status display.
    """
    items = q.progress_items or []
    notes = q.option_notes or {}
    by_status: dict[str, list[dict[str, str]]] = {"done": [], "in_flight": [], "blocked": []}
    for it in items:
        st = it.get("status", "")
        if st in by_status:
            by_status[st].append(it)
    rows = ""
    status_rows = (
        ("done", PROGRESS_STATUS_ICONS["done"], "done"),
        ("in_flight", PROGRESS_STATUS_ICONS["in_flight"], "in progress"),
    )
    for status_key, icon, sr in status_rows:
        for it in by_status[status_key]:
            detail = _detail_html(it["detail"], "ae-prog-detail") if it.get("detail") else ""
            rows += (
                f'<div class="ae-prog-row ae-prog-{status_key}">'
                f'<span class="ae-prog-icon" aria-hidden="true">{icon}</span>'
                f'<span class="ae-prog-label">{_esc(it.get("label", ""))}</span>{detail}'
                f'<span class="sr-only"> ({sr})</span></div>'
            )
    detail_by_label = {it.get("label"): it.get("detail") for it in by_status["blocked"]}
    cards = ""
    for opt in recommended_first(q):
        is_rec = opt == q.recommended
        badge = '<span class="ae-rec-badge">suggested next</span>' if is_rec else ""
        note_text = notes.get(opt) or detail_by_label.get(opt)
        note = f'<span class="ae-card-note">{_esc(note_text)}</span>' if note_text else ""
        checked = " checked" if q.default == opt else ""
        cls = "ae-card ae-card-rec" if is_rec else "ae-card"
        cards += (
            f'<label class="{cls}">'
            f'<input type="radio" name="{_esc(q.id)}" data-control '
            f'value="{_esc(opt)}"{checked}>'
            f'<span class="ae-prog-icon ae-prog-blocked" aria-hidden="true">'
            f"{PROGRESS_STATUS_ICONS['blocked']}</span>"
            f'{badge}<span class="ae-card-title">{_esc(opt)}</span>{note}</label>'
        )
    picker = (
        '<div class="ae-prog-blocked-h">Blocked — pick one to tackle:</div>'
        f'<div class="ae-cards" role="radiogroup">{cards}</div>'
        if cards
        else ""
    )
    rows_html = f'<div class="ae-prog-rows">{rows}</div>' if rows else ""
    return f'<div class="ae-progress">{rows_html}{picker}</div>'


def _control_deliberation_html(q: FormQuestion) -> str:
    """Render a DELIBERATION control.

    Multi-voice framing: each option card carries chips naming the
    voices that endorsed it (``endorsements``), so a 2-1 split and its
    minority are visible at a glance; the synthesis pick
    (``recommended``) is badged and ordered first. Same radio answer
    path as DECISION — the user chairs the pick.
    """
    notes = q.option_notes or {}
    endorse = endorsement_map(q)
    cards = ""
    for opt in recommended_first(q):
        is_rec = opt == q.recommended
        badge = '<span class="ae-rec-badge">Synthesis pick</span>' if is_rec else ""
        chips = "".join(
            f'<span class="ae-seat">{_esc(name)}</span>' for name in endorse.get(opt, [])
        )
        seats = f'<span class="ae-seats">{chips}</span>' if chips else ""
        note = f'<span class="ae-card-note">{_esc(notes[opt])}</span>' if opt in notes else ""
        checked = " checked" if q.default == opt else ""
        cls = "ae-card ae-card-rec" if is_rec else "ae-card"
        cards += (
            f'<label class="{cls}">'
            f'<input type="radio" name="{_esc(q.id)}" data-control '
            f'value="{_esc(opt)}"{checked}>'
            f'{badge}<span class="ae-card-title">{_esc(opt)}</span>{seats}{note}</label>'
        )
    return f'<div class="ae-cards" role="radiogroup">{cards}</div>'


def _detail_html(text: str, cls: str) -> str:
    """An item ``detail`` as an inline span, or a BLOCK when multi-line.

    A multi-line detail — a diff hunk, a log excerpt — rendered as an
    inline span inside a flex row collapses: HTML folds its newlines and
    leading indentation into single spaces, so a diff arrives as one
    run-on line (found probing the triage encoding for hunk review,
    round table q-forms-hunk-review-001). As an ``ae-detail-block`` it
    takes its own full-width line with ``white-space:pre-wrap`` and
    keeps the shape the author wrote.

    Single-line details stay inline spans — the common case renders
    exactly as before.
    """
    if "\n" in text:
        return f'<div class="{cls} ae-detail-block">{_esc(text)}</div>'
    return f'<span class="{cls}">{_esc(text)}</span>'


def _control_triage_html(q: FormQuestion) -> str:
    """Render a TRIAGE control: one row per item, each row its own
    disposition radiogroup.

    A ``suggested`` ruling renders pre-selected with a "suggested" mark —
    the agent's guess stays visible and overridable, never silently
    accepted (the inference-first discipline). The row carries
    ``data-item`` so the submit script can rebuild the
    ``{label: disposition}`` mapping generically.
    """
    rows = ""
    for idx, (key, item) in enumerate(expansion_items(q)):
        label = item.get("label", "")
        tag = f'<span class="ae-triage-tag">{_esc(item["tag"])}</span>' if item.get("tag") else ""
        detail = _detail_html(item["detail"], "ae-triage-detail") if item.get("detail") else ""
        pick = suggested_pick(q, key)
        opts = ""
        for disposition in q.dispositions or []:
            checked = " checked" if pick == disposition else ""
            mark = '<span class="ae-triage-sug">suggested</span>' if pick == disposition else ""
            opts += (
                f'<label class="ae-triage-opt">'
                f'<input type="radio" name="{_esc(q.id)}::{idx}" data-control '
                f'value="{_esc(disposition)}"{checked}> '
                f"<span>{_esc(disposition)}</span>{mark}</label>"
            )
        rows += (
            f'<div class="ae-triage-row" data-item="{_esc(key)}">'
            f'<div class="ae-triage-head">{tag}'
            f'<span class="ae-triage-label">{_esc(label)}</span>{detail}</div>'
            f'<div class="ae-triage-opts" role="radiogroup" '
            f'aria-label="{_esc(label)}">{opts}</div></div>'
        )
    return f'<div class="ae-triage">{rows}</div>'


def _control_confirm_html(q: FormQuestion) -> str:
    """Render a CONFIRM control: consequences preview + two-way gate.

    The consequences render first, each with its severity visibly
    tagged; the two options render as UNCHECKED radios — by D2 nothing
    is ever pre-selected or badged, so approving is an explicit act.
    """
    rows = ""
    for item in confirm_consequences(q):
        tag = (
            f'<span class="ae-gate-tag">{_esc(item["severity"])}</span>'
            if item.get("severity")
            else ""
        )
        detail = _detail_html(item["detail"], "ae-gate-detail") if item.get("detail") else ""
        rows += (
            f'<div class="ae-gate-row">{tag}'
            f'<span class="ae-gate-label">{_esc(item.get("label", ""))}</span>'
            f"{detail}</div>"
        )
    opts = "".join(
        f'<label class="ae-gate-opt"><input type="radio" '
        f'name="{_esc(q.id)}" data-control value="{_esc(opt)}"> '
        f"<span>{_esc(opt)}</span></label>"
        for opt in q.options
    )
    return (
        f'<div class="ae-gate"><div class="ae-gate-h">If approved:</div>'
        f"{rows}"
        f'<div class="ae-gate-opts" role="radiogroup">{opts}</div></div>'
    )


def _control_ranking_html(q: FormQuestion) -> str:
    """Render a RANKING control: a ranked list plus an unranked pool.

    Two lists, no drag dependency (spec R3): every option starts in the
    unranked pool with an "add" button; the ranked ``<ol>`` shows the
    order (native numbering) with move-up / move-down / remove buttons.
    Moving an option is the explicit act — with no ``suggested`` order
    every option starts in the pool, so an untouched form posts nothing
    at all, never the author's option order by accident.

    A ``suggested`` order pre-populates the ranked list with a visible
    "proposed" badge (D2-c: a proposal to confirm, never silently the
    answer). It is ranked from the start, so submitting without touching
    it posts the proposal — that submit IS the confirmation, and the
    badge is what makes it visible rather than silent.

    Each row carries a hidden ``data-control`` input holding the option,
    so the submit script (and the round-trip simulator) read the ranked
    list generically; the answer is the ranked rows' values in DOM order.
    """
    slots = ranking_slot_count(q)
    proposed = q.suggested if isinstance(q.suggested, list) else []
    buttons = "".join(
        f'<button type="button" class="ae-rank-btn" data-rank="{action}" '
        f'aria-label="{aria}">{glyph}</button>'
        for action, aria, glyph in (
            ("add", "Add to ranking", "+"),
            ("up", "Move up", "↑"),
            ("down", "Move down", "↓"),
            ("drop", "Remove from ranking", "×"),
        )
    )

    def row(opt: str) -> str:
        return (
            f'<li class="ae-rank-row" data-opt="{_esc(opt)}">'
            f'<input type="hidden" data-control value="{_esc(opt)}">'
            f'<span class="ae-rank-label">{_esc(opt)}</span>'
            f'<span class="ae-rank-btns">{buttons}</span></li>'
        )

    ranked = "".join(row(opt) for opt in proposed)
    pool = "".join(row(opt) for opt in q.options if opt not in proposed)
    badge = '<span class="ae-rank-sug">proposed</span>' if proposed else ""
    return (
        f'<div class="ae-rank" data-rank-n="{slots}">'
        f'<div class="ae-rank-h">Ranked <span class="ae-rank-count">{len(proposed)}</span>'
        f"/{slots}{badge}</div>"
        f'<ol class="ae-rank-ranked">{ranked}</ol>'
        f'<div class="ae-rank-h">Unranked</div>'
        f'<ul class="ae-rank-pool">{pool}</ul></div>'
    )


def _control_assumption_review_html(q: FormQuestion) -> str:
    """Render an ASSUMPTION_REVIEW control: one row per inferred
    assumption, each a fixed accept / edit / reject radiogroup with an
    inline replacement-text input that the script reveals when "edit" is
    picked (pre-filled with the label, so the user edits rather than
    retypes).

    Rows reuse the triage row family (label / detail / radiogroup); the
    ``source`` renders muted so the user can see WHERE the agent inferred
    it from. A ``suggested`` accept renders pre-selected with a visible
    "suggested" mark (D2-b) — a proposal to confirm, never silently the
    answer. Rows carry ``data-item`` so the submit script rebuilds the
    ``{key: ruling}`` mapping generically; the text input is
    ``data-control`` too, so the round-trip simulator sees it.
    """
    rows = ""
    for idx, (key, item) in enumerate(expansion_items(q)):
        label = item.get("label", "")
        source = (
            f'<span class="ae-assume-src">from {_esc(item["source"])}</span>'
            if item.get("source")
            else ""
        )
        detail = _detail_html(item["detail"], "ae-triage-detail") if item.get("detail") else ""
        pick = suggested_pick(q, key)
        opts = ""
        for ruling in ASSUMPTION_RULINGS:
            checked = " checked" if pick == ruling else ""
            mark = '<span class="ae-triage-sug">suggested</span>' if pick == ruling else ""
            opts += (
                f'<label class="ae-triage-opt">'
                f'<input type="radio" name="{_esc(q.id)}::{idx}" data-control '
                f'data-assume="{ruling}" value="{ruling}"{checked}> '
                f"<span>{ruling}</span>{mark}</label>"
            )
        rows += (
            f'<div class="ae-triage-row" data-assume-row data-item="{_esc(key)}">'
            f'<div class="ae-triage-head">'
            f'<span class="ae-triage-label">{_esc(label)}</span>{detail}{source}</div>'
            f'<div class="ae-triage-opts" role="radiogroup" '
            f'aria-label="{_esc(label)}">{opts}</div>'
            f'<input type="text" data-control class="ae-input ae-assume-edit" '
            f'value="{_esc(label)}" aria-label="Replacement text for {_esc(label)}"></div>'
        )
    return f'<div class="ae-triage">{rows}</div>'


def _control_multi_select_html(q: FormQuestion) -> str:
    """Render MULTI_SELECT: a list_style list, or plain checkboxes."""
    if q.list_style:
        return _list_html(q, multi=True)
    boxes = "".join(
        f'<label class="ae-check"><input type="checkbox" data-control '
        f'value="{_esc(opt)}"{_checked(q, opt)}> {_esc(opt)}</label>'
        for opt in q.options
    )
    return f'<div class="ae-checks">{boxes}</div>'


def _control_single_select_html(q: FormQuestion) -> str:
    """Render SINGLE_SELECT: a list_style list, or a native <select>."""
    if q.list_style:
        return _list_html(q, multi=False)
    opts = '<option value="">— choose —</option>' + "".join(
        f'<option value="{_esc(opt)}"{_selected(q, opt)}>{_esc(opt)}</option>' for opt in q.options
    )
    return f'<select data-control class="ae-input">{opts}</select>'


def _control_boolean_html(q: FormQuestion) -> str:
    """Render BOOLEAN as a Yes/No <select>."""
    opts = '<option value="">—</option>' + "".join(
        f'<option value="{_esc(o)}"{_selected(q, o)}>{_esc(o)}</option>' for o in BOOLEAN_OPTIONS
    )
    return f'<select data-control class="ae-input">{opts}</select>'


def _control_number_html(q: FormQuestion) -> str:
    """Render NUMBER with min/max bounds mirrored onto native attrs."""
    bounds = ""
    if q.minimum is not None:
        bounds += f' min="{_esc(q.minimum)}"'
    if q.maximum is not None:
        bounds += f' max="{_esc(q.maximum)}"'
    default = f' value="{_esc(q.default)}"' if q.default is not None else ""
    return f'<input type="number" step="any" data-control class="ae-input"{bounds}{default}>'


def _control_date_html(q: FormQuestion) -> str:
    """Render DATE as a native date input."""
    default = f' value="{_esc(q.default)}"' if q.default is not None else ""
    return f'<input type="date" data-control class="ae-input"{default}>'


def _control_textarea_html(q: FormQuestion) -> str:
    """Render TEXTAREA with max_length mirrored onto native attrs."""
    maxlen = f' maxlength="{_esc(q.max_length)}"' if q.max_length else ""
    default = _esc(q.default) if q.default is not None else ""
    return (
        f'<textarea data-control class="ae-input ae-textarea" rows="3"{maxlen}>{default}</textarea>'
    )


def _control_text_input_html(q: FormQuestion) -> str:
    """Render TEXT_INPUT — also the fallback for any other type."""
    maxlen = f' maxlength="{_esc(q.max_length)}"' if q.max_length else ""
    default = f' value="{_esc(q.default)}"' if q.default is not None else ""
    return f'<input type="text" data-control class="ae-input"{maxlen}{default}>'


#: Per-type control renderers. PROGRESS is special-cased in
#: ``_control_html`` (it branches further on ``progress_style``); any
#: type not present here falls back to ``_control_text_input_html``,
#: matching the original's unconditional TEXT_INPUT tail.
_CONTROL_RENDERERS: dict[QuestionType, Callable[[FormQuestion], str]] = {
    QuestionType.DECISION: _control_decision_html,
    QuestionType.PUSHBACK: _control_pushback_html,
    QuestionType.DELIBERATION: _control_deliberation_html,
    QuestionType.TRIAGE: _control_triage_html,
    QuestionType.CONFIRM: _control_confirm_html,
    QuestionType.RANKING: _control_ranking_html,
    QuestionType.ASSUMPTION_REVIEW: _control_assumption_review_html,
    QuestionType.MULTI_SELECT: _control_multi_select_html,
    QuestionType.SINGLE_SELECT: _control_single_select_html,
    QuestionType.BOOLEAN: _control_boolean_html,
    QuestionType.NUMBER: _control_number_html,
    QuestionType.DATE: _control_date_html,
    QuestionType.TEXTAREA: _control_textarea_html,
}


def _control_html(q: FormQuestion) -> str:
    """Render the input control for one question (no label/wrapper).

    Every control carries ``data-control`` so the submit script can find
    it generically; numeric/length bounds are mirrored onto the native
    attributes for in-widget feedback, but the authoritative check is
    still server-side ``collect_form_response`` (R4).

    Args:
        q: The question to render a control for.

    Returns:
        An HTML fragment for the control.
    """
    if q.type == QuestionType.PROGRESS:
        return (
            _control_progress_report_html(q)
            if q.progress_style == "report"
            else _control_progress_html(q)
        )
    return _CONTROL_RENDERERS.get(q.type, _control_text_input_html)(q)


#: Per-type ``data-collect`` mode: HOW the submit script reads a field's
#: answer out of the DOM. Emitted on the field wrapper at render time;
#: the script switches on the attribute, never on the construct type —
#: so a new construct that answers like an existing one (one checked
#: radio, a ranked list, per-row rulings…) registers its mode here and
#: needs NO script edit. Types absent here collect as ``value`` (the
#: switch's else-tail: read the field's one control directly).
_COLLECT_MODES: dict[QuestionType, str] = {
    QuestionType.DECISION: "checked-one",
    QuestionType.PUSHBACK: "checked-one",
    QuestionType.DELIBERATION: "checked-one",
    QuestionType.PROGRESS: "checked-one",
    QuestionType.CONFIRM: "checked-one",
    QuestionType.MULTI_SELECT: "checked-many",
    QuestionType.TRIAGE: "rulings",
    QuestionType.ASSUMPTION_REVIEW: "rulings-with-text",
    QuestionType.RANKING: "ranked",
}


def _collect_mode(q: FormQuestion) -> str:
    """Return the ``data-collect`` mode for one question's field.

    SINGLE_SELECT is the one type whose mode depends on presentation:
    a ``list_style`` list renders radios (read the checked one), the
    default renders a native ``<select>`` (read its value).
    """
    if q.type == QuestionType.SINGLE_SELECT and q.list_style:
        return "checked-one"
    return _COLLECT_MODES.get(q.type, "value")


def _checked(q: FormQuestion, opt: str) -> str:
    """Return ``checked`` if ``opt`` is (or is in) the question's default.

    A MULTI_SELECT default is a list — the same shape as its answer — so
    membership pre-checks any number of boxes.
    """
    if isinstance(q.default, list):
        return " checked" if opt in q.default else ""
    return " checked" if q.default is not None and opt == q.default else ""


def _selected(q: FormQuestion, opt: str) -> str:
    """Return ``selected`` if ``opt`` is the question's default value."""
    return " selected" if q.default is not None and opt == q.default else ""


def _field_html(q: FormQuestion) -> str:
    """Render one labelled field (label + optional help + control).

    For a DECISION question a ``rationale`` callout ("why this
    recommendation") is rendered beneath the option cards; for a PUSHBACK
    the same callout is headed "Why I'd push back"; for a PROGRESS report
    it is headed "Summary".
    """
    req = '<span class="ae-req" title="required">*</span>' if q.required else ""
    help_html = f'<div class="ae-help">{_esc(q.help_text)}</div>' if q.help_text else ""
    rationale_h = _esc(RATIONALE_HEADERS.get(q.type, "Why"))
    rationale_html = (
        f'<div class="ae-rationale"><span class="ae-rationale-h">{rationale_h}</span>'
        f"{_esc(q.rationale)}</div>"
        if q.rationale
        else ""
    )
    # An inferred value is the agent's GUESS. It must never read as a
    # settled fact — the badge is what makes a wrong inference catchable,
    # and is the difference between inference-first being a mechanism and
    # being a paragraph of guidance.
    inferred_html = (
        f'<div class="ae-inferred"><span class="ae-inferred-b">guessed</span>'
        f"{_esc(q.inferred_from)}</div>"
        if q.inferred_from
        else ""
    )
    inferred_attr = ' data-inferred="1"' if q.inferred_from else ""
    required_attr = ' data-required="1"' if q.required else ""
    return (
        f'<div class="ae-field" data-fid="{_esc(q.id)}" '
        f'data-ftype="{_esc(q.type.value)}" data-collect="{_collect_mode(q)}"'
        f"{inferred_attr}{required_attr}>"
        f'<label class="ae-label">{_esc(q.text)}{req}</label>'
        f"{help_html}{inferred_html}{_control_html(q)}{rationale_html}</div>"
    )


#: The form CSS lives in :mod:`attune_forms.theme` — the ONE
#: tracked source (workflow-intake-forms Task 3), projected here as
#: inline injection and to the ops dashboard as /static/form-theme.css.
#: ``_CSS_BASE``/``_CSS_FAMILIES`` are imported aliases; the per-form
#: family selection below is unchanged: every form emits BASE, each
#: field pulls in only the family its control renders with, so a form
#: never ships styles for controls it lacks. See :func:`_needed_css`.


def _families_for(question: FormQuestion) -> set[str]:
    """Return the CSS families one question's control renders with."""
    qtype = question.type
    if qtype == QuestionType.PROGRESS:
        return {"CARDS", "PROGRESS"}  # blocked picker reuses the cards
    if qtype in (QuestionType.DECISION, QuestionType.PUSHBACK, QuestionType.DELIBERATION):
        return {"CARDS"}  # deliberation's seat chips live in CARDS
    if qtype == QuestionType.TRIAGE:
        return {"TRIAGE"}
    if qtype == QuestionType.CONFIRM:
        return {"CONFIRM"}
    if qtype == QuestionType.RANKING:
        return {"RANK"}
    if qtype == QuestionType.ASSUMPTION_REVIEW:
        return {"TRIAGE", "INPUT", "ASSUME"}  # rows + edit box reuse; ASSUME adds the reveal
    if qtype == QuestionType.MULTI_SELECT:
        return {"LIST"} if question.list_style else {"CHECKS"}
    if qtype == QuestionType.SINGLE_SELECT:
        return {"LIST"} if question.list_style else {"INPUT"}
    return {"INPUT"}  # boolean, number, date, textarea, text_input, fallback


def _needed_css(form: FormSchema) -> str:
    """Return BASE plus only the family CSS the form's controls use."""
    used: set[str] = set()
    for question in form.questions:
        used |= _families_for(question)
    return _CSS_BASE + "".join(css for name, css in _CSS_FAMILIES if name in used)


def form_to_widget_html(
    form: FormSchema,
    message: str = "",
    instance_id: str | None = None,
    submit_label: str | None = None,
    submit_action: str | None = None,
) -> str:
    """Render a declarative form as an inline ``show_widget`` HTML form.

    The S1 surface (D8). The returned HTML is self-contained (scoped
    styles + a submit script) and theme-native (Claude Design System CSS
    variables, transparent background, no ``position: fixed``). On submit
    it posts a sentinel-marked JSON payload via the global
    ``sendPrompt`` so the agent can validate it through
    :func:`collect_form_response`.

    All form-supplied text is HTML-escaped, and no form data is
    interpolated into executable script — the submit handler reads the
    DOM generically by ``data-*`` attributes (each field's
    ``data-collect`` names HOW its answer is read — see
    :data:`_COLLECT_MODES`) — so a malicious label or option cannot
    inject markup or script.

    Element ids are suffixed per render so two forms shown on the same
    page (e.g. a demo's basic + advanced beats) never collide in the
    DOM — a duplicate id would make the second form's submit script
    read the first form's fields.

    Args:
        form: The validated form to render (build it with
            :func:`form_from_dict` first).
        message: Optional prompt shown above the form.
        instance_id: Optional alphanumeric suffix for the element ids;
            defaults to a fresh random one per call. Pass a fixed value
            only when a deterministic render is needed (tests, golden
            output).
        submit_label: Optional action-specific button label. Existing
            callers retain the inferred Confirm/Submit label.
        submit_action: Optional stable host action id included beside
            the validated answers in the postback.

    Returns:
        An HTML string ready to pass straight to
        ``mcp__visualize__show_widget``.
    """
    start = time.perf_counter()
    sfx = "".join(c for c in (instance_id or "") if c.isalnum()) or uuid.uuid4().hex[:8]
    form_id = f"attune-elicit-form-{sfx}"
    intro = f'<p class="ae-msg">{_esc(message)}</p>' if message else ""
    desc = f'<p class="ae-desc">{_esc(form.description)}</p>' if form.description else ""
    fields = "".join(_field_html(q) for q in form.questions)
    css = _needed_css(form).replace("#attune-elicit-form", f"#{form_id}")

    # Fully-inferred forms are confirmations, not questions: the agent
    # believes it knows every answer already. Chair-ruled 2026-07-25 to
    # RENDER rather than skip — a silent correct-looking guess is the one
    # failure a form cannot recover from. The banner and button label are
    # what tell the user this is a review, not an interrogation.
    confirm = is_fully_inferred(form)
    confirm_html = (
        '<p class="ae-confirm">Everything below was filled in from '
        "context. Change anything that&#x27;s wrong, then confirm.</p>"
        if confirm
        else ""
    )
    button_label = submit_label or ("Confirm" if confirm else "Submit")
    action_js = json.dumps(submit_action)

    html = f"""<h2 class="sr-only">{_esc(form.title)} — interactive form</h2>
<form id="{form_id}" data-form-title="{_esc(form.title)}">
<style>
{css}</style>
<h3>{_esc(form.title)}</h3>
{intro}{desc}{confirm_html}
{fields}
<button type="button" id="ae-submit-{sfx}" class="ae-submit">{_esc(button_label)}</button>
<div id="ae-error-{sfx}" class="ae-error" role="alert"></div>
<script>
(function() {{
  var form = document.getElementById('{form_id}');
  var btn = document.getElementById('ae-submit-{sfx}');
  var err = document.getElementById('ae-error-{sfx}');
  if (!form || !btn) return;
  // Ranking controls: move a row between the pool and the ranked list,
  // or within the ranked list. Pure DOM moves — the ranked list's order
  // is the answer, read at submit time.
  // Assumption rows: reveal the replacement-text box only while "edit"
  // is the picked ruling.
  form.addEventListener('change', function(e) {{
    var radio = e.target;
    if (!radio || !radio.hasAttribute || !radio.hasAttribute('data-assume')) return;
    var row = radio.closest ? radio.closest('[data-assume-row]') : null;
    if (row) row.classList.toggle('ae-assume-editing', radio.value === 'edit');
  }});
  form.addEventListener('click', function(e) {{
    var b = e.target.closest ? e.target.closest('[data-rank]') : null;
    if (!b || !form.contains(b)) return;
    var row = b.closest('.ae-rank-row'), box = b.closest('.ae-rank');
    if (!row || !box) return;
    var ranked = box.querySelector('.ae-rank-ranked');
    var pool = box.querySelector('.ae-rank-pool');
    var n = Number(box.getAttribute('data-rank-n')), act = b.getAttribute('data-rank');
    if (act === 'add') {{
      if (ranked.children.length < n) ranked.appendChild(row);
    }} else if (act === 'drop') {{
      pool.appendChild(row);
    }} else if (act === 'up' && row.previousElementSibling) {{
      ranked.insertBefore(row, row.previousElementSibling);
    }} else if (act === 'down' && row.nextElementSibling) {{
      ranked.insertBefore(row.nextElementSibling, row);
    }}
    var count = box.querySelector('.ae-rank-count');
    if (count) count.textContent = ranked.children.length;
  }});
  btn.addEventListener('click', function() {{
    var answers = {{}};
    // The reader switches on data-collect — HOW to read the answer —
    // never on the construct type, so a new construct that answers like
    // an existing one needs no edit here (it registers its mode at
    // render time, in _COLLECT_MODES).
    form.querySelectorAll('.ae-field').forEach(function(f) {{
      var fid = f.getAttribute('data-fid');
      var mode = f.getAttribute('data-collect');
      if (mode === 'checked-many') {{
        var vals = [];
        f.querySelectorAll('[data-control]:checked').forEach(function(c) {{
          vals.push(c.value);
        }});
        answers[fid] = vals;
      }} else if (mode === 'checked-one') {{
        // the one checked radio; with nothing checked no answer is
        // posted (e.g. a progress report with nothing blocked is
        // display-only).
        var picked = f.querySelector('[data-control]:checked');
        if (picked) answers[fid] = picked.value;
      }} else if (mode === 'rulings') {{
        // rebuild {{item key: ruling}} from the per-row ([data-item])
        // pickers; rows left unruled are simply absent.
        var rulings = {{}};
        f.querySelectorAll('[data-item]').forEach(function(r) {{
          var p = r.querySelector('[data-control]:checked');
          if (p) rulings[r.getAttribute('data-item')] = p.value;
        }});
        if (Object.keys(rulings).length) answers[fid] = rulings;
      }} else if (mode === 'rulings-with-text') {{
        // rulings plus an edit lane: {{item key: ruling | {{edit: text}}}}
        // — an edit ruling carries the row's text box (empty text is
        // posted as-is — the validator names it).
        var rulings = {{}};
        f.querySelectorAll('[data-item]').forEach(function(r) {{
          var p = r.querySelector('input[type=radio][data-control]:checked');
          if (!p) return;
          var t = r.querySelector('input[type=text][data-control]');
          rulings[r.getAttribute('data-item')] =
            (p.value === 'edit') ? {{ edit: (t ? t.value : '') }} : p.value;
        }});
        if (Object.keys(rulings).length) answers[fid] = rulings;
      }} else if (mode === 'ranked') {{
        // the ranked list's rows in DOM order ARE the answer; an
        // untouched (empty) ranking posts nothing.
        var order = [];
        f.querySelectorAll('.ae-rank-ranked [data-control]').forEach(function(c) {{
          order.push(c.value);
        }});
        if (order.length) answers[fid] = order;
      }} else {{
        // 'value': the field's one control, read directly; a number
        // input posts a Number (el.type, not the construct, decides).
        var el = f.querySelector('[data-control]');
        if (!el || el.value === '') return;
        answers[fid] = (el.type === 'number') ? Number(el.value) : el.value;
      }}
    }});
    // Required-field gate: an unanswered required field must surface a
    // visible error and leave the button alive — never post a payload
    // the server-side validator will reject after the widget is dead.
    var missing = [];
    form.querySelectorAll('.ae-field[data-required]').forEach(function(f) {{
      var v = answers[f.getAttribute('data-fid')];
      // A required rulings board (triage / assumption review — any
      // [data-item] rows) is complete only when EVERY row is ruled;
      // a required ranking only when EVERY slot is filled.
      var rows = f.querySelectorAll('[data-item]').length;
      var rank = f.querySelector('.ae-rank');
      var slots = rank ? Number(rank.getAttribute('data-rank-n')) : 0;
      // An assumption ruled "edit" with no replacement text is not
      // answered — never post it for the validator to reject after
      // the widget is dead.
      var blankEdit = false;
      if (v && typeof v === 'object' && !Array.isArray(v)) {{
        Object.keys(v).forEach(function(k) {{
          var r = v[k];
          if (r && typeof r === 'object' && !String(r.edit || '').trim()) blankEdit = true;
        }});
      }}
      var empty = v === undefined || v === '' ||
        (Array.isArray(v) && v.length === 0) ||
        (rows > 0 && (!v || Object.keys(v).length < rows)) ||
        (slots > 0 && (!v || v.length < slots)) || blankEdit;
      f.classList.toggle('ae-field-missing', empty);
      if (empty) {{
        var lbl = f.querySelector('.ae-label');
        missing.push(lbl ? lbl.textContent.replace(/\\*$/, '')
          : f.getAttribute('data-fid'));
      }}
    }});
    // A ranking is all-or-nothing at the validator — exactly N ranked
    // or nothing at all, whether or not the field is required — so a
    // half-filled OPTIONAL ranking is blocked here too. The loop above
    // never sees it, and posting it would hand the validator the very
    // payload this gate exists to prevent (review finding, 2026-08-16).
    var partial = [];
    form.querySelectorAll('.ae-field:not([data-required])').forEach(function(f) {{
      var rank = f.querySelector('.ae-rank');
      if (!rank) return;
      var v = answers[f.getAttribute('data-fid')];
      var slots = Number(rank.getAttribute('data-rank-n'));
      if (!Array.isArray(v) || v.length === 0 || v.length >= slots) return;
      f.classList.add('ae-field-missing');
      var lbl = f.querySelector('.ae-label');
      partial.push((lbl ? lbl.textContent.replace(/\\*$/, '')
        : f.getAttribute('data-fid')) + ' (' + v.length + '/' + slots + ')');
    }});
    if (missing.length || partial.length) {{
      var notes = [];
      if (missing.length) notes.push('Required: ' + missing.join(', '));
      if (partial.length) {{
        notes.push('Rank every slot or none: ' + partial.join(', '));
      }}
      err.textContent = notes.join(' — ');
      return;
    }}
    err.textContent = '';
    var payload = {{ {WIDGET_RESPONSE_MARKER!r}: true,
      title: form.getAttribute('data-form-title'), answers: answers }};
    var submitAction = {action_js};
    if (submitAction !== null) payload.action = submitAction;
    if (typeof sendPrompt === 'function') {{
      sendPrompt('Elicitation form submitted — parse and validate this '
        + 'response:\\n```json\\n' + JSON.stringify(payload) + '\\n```');
      btn.disabled = true; btn.textContent = 'Submitted \\u2713';
    }} else {{
      err.textContent = 'This surface cannot post back (sendPrompt '
        + 'unavailable). Use the AskUserQuestion fallback.';
    }}
  }});
}})();
</script>
</form>"""
    # form.form_id, not the DOM id above: the DOM suffix is fresh per
    # render, while the telemetry id must match what collect re-derives.
    log_form_rendered(
        form.form_id,
        duration_ms=(time.perf_counter() - start) * 1000.0,
        html_bytes=len(html.encode("utf-8")),
    )
    return html
