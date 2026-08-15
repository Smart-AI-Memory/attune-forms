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
import math
import re
from typing import Any

from attune_forms.markdown_surface import _field_lines
from attune_forms.models import (
    FormQuestion,
    FormSchema,
    QuestionType,
    triage_item_key,
)
from attune_forms.widget import WIDGET_RESPONSE_MARKER

#: A fenced code block with ANY language tag (``` / ```json /
#: ```python / ```c# …), lazily matched. The tag class is CommonMark's
#: info-string rule — any run of non-whitespace, non-backtick
#: characters — so tags like ``c#``/``.net`` are fences too
#: (ultrareview finding: an alnum-only class let their bodies leak
#: into line parsing). Every fence is excluded from line parsing; only
#: bare/json-tagged bodies are JSON-reply candidates — a pasted code
#: snippet must never be ingested as answers.
_FENCE_RE = re.compile(r"```([^\s`]*)[ \t]*\n(.*?)```", re.DOTALL)

#: One shorthand line: optional list bullet, a key (field id, 1-based
#: number, or dotted triage row — item keys may contain spaces, since
#: an id-less item is keyed by its label), ``:`` or ``=``, the value.
_LINE_RE = re.compile(r"^\s*(?:[-*]\s+)?([^:=]+?)\s*[:=]\s*(.+?)\s*$")


def _coerce(question: FormQuestion, value: str) -> Any:
    """Type-aware value shaping for one shorthand value.

    Deterministic shaping only — membership, bounds, and format checks
    stay in the validator. NUMBER parses numerically; a non-number or a
    non-finite value ("nan"/"inf" would defeat the validator's bounds
    checks) passes through as a string so the validator names it.
    MULTI_SELECT takes the whole value when it exactly matches one
    option, else splits on commas.
    """
    if question.type is QuestionType.NUMBER:
        try:
            as_float = float(value)
        except ValueError:
            return value
        if not math.isfinite(as_float):
            return value
        return int(as_float) if as_float.is_integer() else as_float
    if question.type is QuestionType.MULTI_SELECT:
        if value in question.options:
            return [value]
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _known_keys(form: FormSchema) -> set[str]:
    """Every answer key a form can legitimately carry: field ids plus
    the dotted per-item keys of each triage board."""
    keys = {q.id for q in form.questions}
    for q in form.questions:
        if q.type is QuestionType.TRIAGE:
            keys |= {f"{q.id}.{triage_item_key(it)}" for it in q.triage_items or []}
    return keys


def _json_block_answers(form: FormSchema, reply: str) -> tuple[dict[str, Any] | None, list[str]]:
    """Extract answers from the LAST parseable JSON block, if any.

    Accepts the full sentinel payload (``{"__elicitation_response__":
    true, ..., "answers": {...}}``) or a bare answers object. ``null``
    values are dropped — in the emitted skeleton they mean
    "unanswered", and passing them through would read as empty answers
    rather than absent ones. Keys that match no field and no dotted
    triage row are named problems and excluded — the shorthand path's
    unknown-id honesty applies to the JSON path too (a typo'd id must
    never vanish silently).
    """
    candidates = [body for tag, body in _FENCE_RE.findall(reply) if tag in ("", "json")]
    for block in reversed(candidates):
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
        known = _known_keys(form)
        problems: list[str] = []
        cleaned: dict[str, Any] = {}
        for key, value in answers.items():
            # Untouched skeleton placeholders mean "unanswered": bare
            # null, the empty multi-select list, and null triage rulings.
            if isinstance(value, dict):
                value = {k: v for k, v in value.items() if v is not None}
            if value is None or value == [] or value == {}:
                continue
            if key not in known:
                problems.append(f"unknown field: {key!r}")
                continue
            cleaned[key] = value
        return cleaned, problems
    if candidates:
        return None, ["fenced code block is not valid JSON"]
    return None, []


def _resolve_line_key(form: FormSchema, key: str) -> tuple[str | None, str | None]:
    """Resolve one shorthand key to its answer key.

    Returns ``(answer_key, problem)`` — exactly one is set. The answer
    key is a field id (for id and 1-based number keys) or a dotted
    triage row key (item keys may contain spaces — an id-less item is
    keyed by its label).
    """
    by_id = {q.id: q for q in form.questions}
    if key in by_id:
        return key, None
    if key.isdigit():
        index = int(key) - 1
        if 0 <= index < len(form.questions):
            return form.questions[index].id, None
        return None, f"unknown field number: {key}"
    if "." in key:
        root = key.split(".", 1)[0]
        if root in by_id:
            if by_id[root].type is QuestionType.TRIAGE:
                return key, None
            return None, f"dotted key on non-triage field: {key!r}"
    return None, f"unknown field: {key!r}"


def markdown_to_answers(form: FormSchema, reply: str) -> tuple[dict[str, Any], list[str]]:
    """Parse a typed reply to a markdown-rendered form (R1).

    A parseable fenced JSON block is the base (it IS the wire format),
    and shorthand lines outside fences OVERRIDE it — what the user
    TYPED always beats what they quoted, so pasting the original
    message (whose emitted skeleton carries recommended/suggested
    prefills) can never overwrite a typed answer. With a JSON block
    present, non-shorthand lines are treated as accompanying prose and
    ignored; with no block, every non-blank line must be shorthand —
    ``field_id: value``, ``N: value`` (1-based field position), or
    ``field_id.item_key: disposition`` for triage rows (the dotted keys
    fold in ``collect_form_response``) — and anything else is a named
    problem. A repeated key deterministically keeps the LAST value.

    Returns ``(answers, problems)``: raw answers ready for
    :func:`attune_forms.collect_form_response`, plus a named problem
    for every unknown key on either path — nothing is guessed or
    silently dropped.
    """
    json_answers, problems = _json_block_answers(form, reply)
    has_block = json_answers is not None
    answers: dict[str, Any] = dict(json_answers or {})

    by_id = {q.id: q for q in form.questions}
    text_outside_fences = _FENCE_RE.sub("", reply)
    for line in text_outside_fences.splitlines():
        if not line.strip():
            continue
        match = _LINE_RE.match(line)
        if not match:
            if not has_block:
                problems.append(f"unparseable line: {line.strip()!r}")
            continue
        key, value = match.group(1), match.group(2)
        answer_key, problem = _resolve_line_key(form, key)
        if answer_key is None:
            # Prose around a pasted block often contains colons
            # ("Note: ..."); with a block present, an unresolvable line
            # is prose, not a claim.
            if not has_block:
                problems.append(problem)
            continue
        question = by_id.get(answer_key)
        answers[answer_key] = _coerce(question, value) if question else value

    # Typed dotted rows must survive a quoted skeleton that already
    # carries the board's mapping (a suggested prefill keeps it
    # non-empty): merge "<board>.<item>" siblings into the mapping,
    # typed wins — otherwise the collect-time fold, whose mapping-wins
    # rule serves the other surfaces, strands them and the validator
    # re-asks an item the user answered (ultrareview finding).
    for q in form.questions:
        if q.type is not QuestionType.TRIAGE:
            continue
        mapping = answers.get(q.id)
        if not isinstance(mapping, dict):
            continue
        prefix = f"{q.id}."
        for key in [k for k in answers if k.startswith(prefix)]:
            mapping[key[len(prefix) :]] = answers.pop(key)

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
    known_ids = {q.id for q in form.questions}
    offender_ids: list[str] = []
    for problem in problems:
        for quoted in _QUOTED_ID_RE.findall(problem):
            root = quoted.split(".", 1)[0]
            if root in known_ids and root not in offender_ids:
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
