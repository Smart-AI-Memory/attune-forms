"""Tolerant reply ingestion for the S4 markdown surface.

The other half of :mod:`attune_forms.markdown_surface` (round-table
ruling, thread q-forms-grammar-expansion-001: rendering without
ingestion is "documentation, not a surface"). A user replying to a
markdown-rendered form may paste back the filled JSON skeleton or type
line shorthand; :func:`markdown_to_answers` parses either
DETERMINISTICALLY into raw answers for
:func:`attune_forms.collect_form_response` — which remains the sole
validation truth (spec ``markdown-ingestion`` D1). Free-text replies
are the host agent's lane, taught by the skill, and also funnel into
the same validator.

The honesty rule mirrors the validator's: every unparseable non-blank
line and every unknown field id becomes a named problem — the parser
never guesses and never drops input silently. Option matching is EXACT
(D1: a miss is a named re-ask; prefix/fuzzy matching is a v2 ruling).

:func:`problems_to_markdown` closes the loop: validation problems
render back as a markdown re-ask of ONLY the offending fields, so a
text-only host re-asks exactly what failed — never the whole form.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import json
import re
from typing import Any

from attune_forms.markdown_surface import _field_lines
from attune_forms.models import FormQuestion, FormSchema, QuestionType
from attune_forms.widget import WIDGET_RESPONSE_MARKER

#: A fenced code block (``` ... ```), lazily matched; used both to find
#: JSON reply blocks and to exclude fenced content from line parsing.
_FENCE_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)

#: One shorthand line: optional list bullet, a key (field id, 1-based
#: number, or dotted triage id), ``:`` or ``=``, and the value.
_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?([A-Za-z0-9_.\-]+)\s*[:=]\s*(.+?)\s*$")


def _coerce(question: FormQuestion, value: str) -> Any:
    """Type-aware value shaping for one shorthand value.

    Deterministic shaping only — membership, bounds, and format checks
    stay in the validator. NUMBER parses numerically (a non-number
    passes through as a string so the validator names it);
    MULTI_SELECT takes the whole value when it exactly matches one
    option, else splits on commas.
    """
    if question.type is QuestionType.NUMBER:
        try:
            as_float = float(value)
        except ValueError:
            return value
        return int(as_float) if as_float.is_integer() else as_float
    if question.type is QuestionType.MULTI_SELECT:
        if value in question.options:
            return [value]
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _json_block_answers(reply: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract answers from the LAST fenced JSON block, if any.

    Accepts the full sentinel payload (``{"__elicitation_response__":
    true, ..., "answers": {...}}``) or a bare answers object. ``null``
    values are dropped — in the emitted skeleton they mean
    "unanswered", and passing them through would read as empty answers
    rather than absent ones.
    """
    blocks = _FENCE_RE.findall(reply)
    for block in reversed(blocks):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        answers = (
            data.get("answers") if WIDGET_RESPONSE_MARKER in data or "answers" in data else data
        )
        if not isinstance(answers, dict):
            return None, ["json block has no 'answers' object"]
        cleaned: dict[str, Any] = {}
        for key, value in answers.items():
            # Untouched skeleton placeholders mean "unanswered": bare
            # null, the empty multi-select list, and null triage rulings.
            if isinstance(value, dict):
                value = {k: v for k, v in value.items() if v is not None}
            if value is None or value == [] or value == {}:
                continue
            cleaned[key] = value
        return cleaned, []
    if blocks:
        return None, ["fenced code block is not valid JSON"]
    return None, []


def markdown_to_answers(form: FormSchema, reply: str) -> tuple[dict[str, Any], list[str]]:
    """Parse a typed reply to a markdown-rendered form (R1).

    Precedence: a parseable fenced JSON block wins outright (it IS the
    wire format). Otherwise every non-blank line outside code fences
    must be shorthand — ``field_id: value``, ``N: value`` (1-based
    field position), or ``field_id.item_key: disposition`` for triage
    rows (the dotted keys fold in ``collect_form_response``). A
    repeated key deterministically keeps the LAST value.

    Returns ``(answers, problems)``: raw answers ready for
    :func:`attune_forms.collect_form_response`, plus a named problem
    for every line that parsed nowhere and every key that matched no
    field — nothing is guessed or silently dropped.
    """
    json_answers, json_problems = _json_block_answers(reply)
    if json_answers is not None:
        return json_answers, []
    problems = list(json_problems)

    by_id = {q.id: q for q in form.questions}
    answers: dict[str, Any] = {}
    text_outside_fences = _FENCE_RE.sub("", reply)
    for line in text_outside_fences.splitlines():
        if not line.strip():
            continue
        match = _LINE_RE.match(line)
        if not match:
            problems.append(f"unparseable line: {line.strip()!r}")
            continue
        key, value = match.group(1), match.group(2)

        if key in by_id:
            answers[key] = _coerce(by_id[key], value)
            continue
        if key.isdigit():
            index = int(key) - 1
            if 0 <= index < len(form.questions):
                question = form.questions[index]
                answers[question.id] = _coerce(question, value)
            else:
                problems.append(f"unknown field number: {key}")
            continue
        if "." in key and key.split(".", 1)[0] in by_id:
            dotted_root = by_id[key.split(".", 1)[0]]
            if dotted_root.type is QuestionType.TRIAGE:
                answers[key] = value
                continue
            problems.append(f"dotted key on non-triage field: {key!r}")
            continue
        problems.append(f"unknown field: {key!r}")

    return answers, problems


#: Quoted-id pattern used to attribute a validation problem to a field
#: (``collect_form_response`` names fields as ``'field_id'``).
_QUOTED_ID_RE = re.compile(r"'([^']+)'")


def problems_to_markdown(form: FormSchema, problems: list[str]) -> str:
    """Render validation problems as a markdown re-ask (R2).

    Re-renders ONLY the fields the problems name (attributed by the
    validator's quoted field ids; a dotted triage id attributes to its
    root field), each with its original position number so shorthand
    replies keep working. Problems naming no field render in the
    header only. Fields that validated are never re-asked.
    """
    offender_ids: list[str] = []
    for problem in problems:
        for quoted in _QUOTED_ID_RE.findall(problem):
            root = quoted.split(".", 1)[0]
            if any(q.id == root for q in form.questions) and root not in offender_ids:
                offender_ids.append(root)

    lines = ["Some answers need another pass:"]
    lines += [f"- {problem}" for problem in problems]
    for idx, q in enumerate(form.questions, start=1):
        if q.id not in offender_ids:
            continue
        field = _field_lines(q)
        field[0] = f"{idx}. {field[0]}"
        lines += ["", *field]
    if offender_ids:
        lines += [
            "",
            "Reply for just these fields — shorthand works " "(`field_id: value` or `N: value`).",
        ]
    return "\n".join(lines)
