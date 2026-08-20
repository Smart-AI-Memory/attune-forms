"""Declarative form → portable markdown (the S4 surface).

The fourth render surface, for hosts with neither an HTML widget pane
nor a question tool — Codex CLI, Antigravity, plain chat. The form
renders as markdown any terminal can show; the reply travels as the
SAME sentinel-marked JSON payload the widget posts (a skeleton is
emitted under the form), so every surface funnels into
:func:`attune_forms.collect_form_response` unchanged.

Like every renderer here this is a pure ``FormSchema -> str`` transform
— no agent or tool dependency — so it is fully testable and any host
agent (whatever the model) can call it through the library or the MCP
server and relay the text verbatim.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
from typing import Any

from attune_forms.models import (
    ASSUMPTION_RULINGS,
    PROGRESS_STATUS_ICONS,
    RATIONALE_HEADERS,
    FormQuestion,
    FormSchema,
    QuestionType,
    expansion_items,
    ranking_slot_count,
    recommended_first,
    suggested_pick,
)
from attune_forms.widget import WIDGET_RESPONSE_MARKER

def _option_lines(q: FormQuestion, *, badge_for: dict[str, str] | None = None) -> list[str]:
    """Bullet (or numbered) lines for a select-like question's options.

    ``badge_for`` maps option -> a parenthesised tag rendered after it
    (e.g. "recommended", "your approach"). ``option_notes`` and the
    default marker render inline.
    """
    badges = badge_for or {}
    notes = q.option_notes or {}
    ordered = recommended_first(q) if badges else list(q.options)
    lines = []
    for idx, opt in enumerate(ordered):
        marker = f"{idx + 1}." if q.list_style == "ordered" else "-"
        line = f"{marker} {opt}"
        if opt in badges:
            line += f" **({badges[opt]})**"
        is_default = opt in q.default if isinstance(q.default, list) else q.default == opt
        if is_default:
            line += " *(default)*"
        if opt in notes:
            line += f" — {notes[opt]}"
        lines.append(line)
    return lines


def _endorsement_suffix(q: FormQuestion, opt: str) -> str:
    """ " — endorsed by: a, b" for a deliberation option, or ""."""
    names = (q.endorsements or {}).get(opt)
    return f" — endorsed by: {', '.join(names)}" if names else ""


def _progress_lines(q: FormQuestion) -> list[str]:
    """Status rows + the picker for a PROGRESS question."""
    lines = []
    for item in q.progress_items or []:
        label = item.get("label", "")
        status = item.get("status", "")
        detail = f" — {item['detail']}" if item.get("detail") else ""
        if q.progress_style == "report":
            lines.append(f"- `{status}` {label}{detail}")
        else:
            icon = PROGRESS_STATUS_ICONS.get(status, "•")
            lines.append(f"- {icon} {label}{detail}")
    if q.options:
        head = (
            "Pick one to go deeper:"
            if q.progress_style == "report"
            else ("Blocked — pick one to tackle:")
        )
        lines.append("")
        lines.append(head)
        badges = {q.recommended: "suggested next"} if q.recommended else {}
        lines.extend(_option_lines(q, badge_for=badges))
    return lines


def _triage_lines(q: FormQuestion) -> list[str]:
    """Item rows + the shared ruling vocabulary for a TRIAGE question."""
    vocabulary = " / ".join(f"`{d}`" for d in q.dispositions or [])
    lines = [f"Rule each item as one of: {vocabulary}"]
    for key, item in expansion_items(q):
        tag = f" `{item['tag']}`" if item.get("tag") else ""
        detail = f" — {item['detail']}" if item.get("detail") else ""
        line = f"- **{item.get('label', '')}**{tag}{detail}"
        pick = suggested_pick(q, key)
        if pick is not None:
            line += f" → suggested: `{pick}`"
        lines.append(line)
    return lines


def _ranking_lines(q: FormQuestion) -> list[str]:
    """Option list + the ordering rule for a RANKING question."""
    slots = ranking_slot_count(q)
    scope = f"the top {slots}" if slots < len(q.options) else "all of these"
    lines = [f"Rank {scope}, best first (each option once):"]
    lines += [f"- {opt}" for opt in q.options]
    if isinstance(q.suggested, list) and q.suggested:
        lines.append(f"→ proposed order: {', '.join(q.suggested)}")
    return lines


def _assumption_lines(q: FormQuestion) -> list[str]:
    """Assumption rows + the fixed ruling rule for an ASSUMPTION_REVIEW."""
    accept, edit, reject = ASSUMPTION_RULINGS
    lines = [f"Rule each assumption: `{accept}` / `{edit}: <replacement text>` / `{reject}`"]
    for key, item in expansion_items(q):
        detail = f" — {item['detail']}" if item.get("detail") else ""
        source = f" *(from {item['source']})*" if item.get("source") else ""
        line = f"- **{item.get('label', '')}**{detail}{source}"
        pick = suggested_pick(q, key)
        if pick is not None:
            line += f" → suggested: `{pick}`"
        lines.append(line)
    return lines


def _control_lines(q: FormQuestion) -> list[str]:
    """The control-specific body lines for one question."""
    if q.type == QuestionType.BOOLEAN:
        return ["- Yes / No"]
    if q.type == QuestionType.NUMBER:
        bounds = []
        if q.minimum is not None:
            bounds.append(f"min {q.minimum:g}")
        if q.maximum is not None:
            bounds.append(f"max {q.maximum:g}")
        suffix = f" ({', '.join(bounds)})" if bounds else ""
        return [f"*number{suffix}*"]
    if q.type == QuestionType.DATE:
        return ["*date (YYYY-MM-DD)*"]
    if q.type in (QuestionType.TEXT_INPUT, QuestionType.TEXTAREA):
        suffix = f" (max {q.max_length} chars)" if q.max_length else ""
        return [f"*free text{suffix}*"]
    if q.type == QuestionType.DECISION:
        badges = {q.recommended: "recommended"} if q.recommended else {}
        return _option_lines(q, badge_for=badges)
    if q.type == QuestionType.PUSHBACK:
        badges: dict[str, str] = {}
        if q.recommended:
            badges[q.recommended] = "I'd suggest instead"
        if q.user_position:
            badges[q.user_position] = "your approach"
        return _option_lines(q, badge_for=badges)
    if q.type == QuestionType.DELIBERATION:
        badges = {q.recommended: "synthesis pick"} if q.recommended else {}
        lines = _option_lines(q, badge_for=badges)
        return [
            line + _endorsement_suffix(q, opt)
            for line, opt in zip(
                lines, recommended_first(q) if badges else list(q.options), strict=False
            )
        ]
    if q.type == QuestionType.PROGRESS:
        return _progress_lines(q)
    if q.type == QuestionType.TRIAGE:
        return _triage_lines(q)
    if q.type == QuestionType.RANKING:
        return _ranking_lines(q)
    if q.type == QuestionType.ASSUMPTION_REVIEW:
        return _assumption_lines(q)
    if q.type == QuestionType.CONFIRM:
        lines = ["If approved:"]
        for item in q.consequences or []:
            tag = f" `{item['severity']}`" if item.get("severity") else ""
            detail = f" — {item['detail']}" if item.get("detail") else ""
            lines.append(f"- {item.get('label', '')}{tag}{detail}")
        lines.append("")
        lines.append("Answer one of: " + " / ".join(f"**{opt}**" for opt in q.options))
        return lines
    # SINGLE_SELECT / MULTI_SELECT (and any future select-like fallback)
    lines = _option_lines(q)
    if q.type == QuestionType.MULTI_SELECT:
        lines.append("*(pick any that apply)*")
    return lines


def _field_lines(q: FormQuestion) -> list[str]:
    """All markdown lines for one question."""
    req = "" if q.required else " *(optional)*"
    lines = [f"**{q.text}**{req}"]
    if q.help_text:
        lines.append(f"*{q.help_text}*")
    if q.inferred_from:
        # The guess must never read as settled — same discipline as the
        # widget's "guessed" badge.
        lines.append(f"> guessed: `{q.default}` — {q.inferred_from}")
    lines.extend(_control_lines(q))
    if q.rationale:
        header = RATIONALE_HEADERS.get(q.type, "Why")
        lines.append(f"> **{header}:** {q.rationale}")
    return lines


def _skeleton_value(q: FormQuestion) -> Any:
    """The reply skeleton's placeholder value for one question."""
    if q.type == QuestionType.CONFIRM:
        # Never prefilled — approval must be an explicit act (D2
        # projected to S4); the construct also has no default to offer.
        return None
    if q.type == QuestionType.MULTI_SELECT:
        # The default is a list (the answer's shape); a scalar from a
        # directly-built form still renders as a one-item prefill.
        if isinstance(q.default, list):
            return list(q.default)
        return [q.default] if q.default else []
    if q.type == QuestionType.RANKING:
        # The proposed order prefills (a visible proposal — the reply
        # rules say typed shorthand overrides it); else an empty list.
        return list(q.suggested) if isinstance(q.suggested, list) else []
    if q.type in (QuestionType.TRIAGE, QuestionType.ASSUMPTION_REVIEW):
        return {key: suggested_pick(q, key) for key, _ in expansion_items(q)}
    # `is not None`, never truthiness: a falsy default (0, "") is still
    # a default, not "unanswered" (review finding, 2026-08-14).
    if q.default is not None:
        return q.default
    return q.recommended if q.recommended else None


def reply_skeleton(form: FormSchema, questions: list[FormQuestion] | None = None) -> dict[str, Any]:
    """The sentinel-marked reply skeleton for a form (or a subset of it).

    ``questions`` restricts the ``answers`` map to those fields — the
    re-ask path emits a skeleton for only the offending fields. The
    skeleton is always emitted as the LAST fenced block so it wins under
    ``_json_block_answers``' last-block rule: that is what keeps a fenced
    ``answers`` block quoted inside author-supplied field text from being
    ingested as a reply (confirmation pass 2, 2026-08-20).
    """
    chosen = questions if questions is not None else form.questions
    return {
        WIDGET_RESPONSE_MARKER: True,
        "title": form.title,
        "answers": {q.id: _skeleton_value(q) for q in chosen},
    }


def form_to_markdown(form: FormSchema, message: str = "") -> str:
    """Render a declarative form as portable markdown (S4).

    For hosts that render neither HTML widgets nor a question tool: the
    host agent relays this text, the user answers in whatever way suits
    the host, and the agent maps the answers into the emitted JSON
    skeleton — the exact sentinel-marked payload shape the widget posts
    — then validates through :func:`collect_form_response`. One postback
    grammar across all four surfaces.

    Args:
        form: The validated form to render (build it with
            :func:`form_from_dict` first).
        message: Optional prompt shown above the form.

    Returns:
        A markdown string ready to relay to any text host.
    """
    lines = [f"## {form.title}"]
    if message:
        lines += ["", message]
    if form.description:
        lines += ["", f"*{form.description}*"]
    for idx, q in enumerate(form.questions, start=1):
        field = _field_lines(q)
        field[0] = f"{idx}. {field[0]}"
        lines += ["", *field]
    skeleton = reply_skeleton(form)
    lines += [
        "",
        "---",
        "Reply by filling the `answers` values below, or with shorthand "
        "lines — `field_id: value` or `N: value` (field number); a triage "
        "row is `field_id.item_id: disposition`; a ranking is a comma list "
        "in order (`field_id: b, a, c`) or one slot per line "
        "(`field_id.1: b`); an assumption row is `field_id.item_id: accept`, "
        "`field_id.item_id: reject`, or `field_id.item_id: edit: <text>`:",
        "",
        "```json",
        json.dumps(skeleton, indent=2, ensure_ascii=False),
        "```",
    ]
    return "\n".join(lines)
