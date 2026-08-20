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
    ASSUMPTION_TEXT_SUFFIX,
    FormQuestion,
    FormSchema,
    QuestionType,
    decimal_key_number,
    ranking_slot_count,
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

#: A leading ordinal on one entry of a typed ranking ("1. b", "2) a").
_ORDINAL_PREFIX_RE = re.compile(r"^\d+[.)]\s*")

#: A typed assumption edit: ``edit: <replacement text>`` (or ``edit =``);
#: a bare ``edit`` with no text is shaped to ``{"edit": ""}`` so the
#: validator names it — never guessed into an accept.
_ASSUMPTION_EDIT_RE = re.compile(r"^edit(?:\s*[:=]\s*(.*))?$", re.DOTALL)


def _rank_entry(question: FormQuestion, part: str) -> str:
    """Shape ONE typed ranking entry, stripping a leading ordinal only
    when that strip turns a non-option into an option.

    A user re-typing the rendered list often carries its numbering
    ("1. billing"), which is shaping noise. But an option label may
    itself begin with digits and a dot or paren — "3.12", "2) Ship",
    "10.5%" — and stripping unconditionally ate the label the user
    copied EXACTLY, so the validator then named entries ('12', 'Ship')
    nobody typed and every retry failed identically (review finding,
    2026-08-16). Membership is still the validator's call: an entry
    that matches nothing either way passes through RAW, so a genuine
    miss is named as the user typed it (ingestion D1).
    """
    if part in question.options:
        return part
    stripped = _ORDINAL_PREFIX_RE.sub("", part)
    return stripped if stripped in question.options else part


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
    if question.type is QuestionType.RANKING:
        # An ordered comma list; a leading ordinal ("1. b", "2) a") is
        # shaping noise, stripped by :func:`_rank_entry` only when the
        # strip finds an option. Membership, repeats, and length stay
        # the validator's call.
        if value in question.options:
            return [value]
        return [_rank_entry(question, part.strip()) for part in value.split(",") if part.strip()]
    return value


def _known_keys(form: FormSchema) -> set[str]:
    """Every answer key a form can legitimately carry: field ids plus
    the dotted per-item keys of each triage board."""
    keys = {q.id for q in form.questions}
    for q in form.questions:
        if q.type is QuestionType.TRIAGE:
            keys |= {f"{q.id}.{triage_item_key(it)}" for it in q.triage_items or []}
        elif q.type is QuestionType.RANKING:
            keys |= {f"{q.id}.{k}" for k in range(1, ranking_slot_count(q) + 1)}
        elif q.type is QuestionType.ASSUMPTION_REVIEW:
            for it in q.assumptions or []:
                keys.add(f"{q.id}.{triage_item_key(it)}")
                keys.add(f"{q.id}.{triage_item_key(it)}{ASSUMPTION_TEXT_SUFFIX}")
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
        by_id = {q.id: q for q in form.questions}
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
            cleaned[key] = _shape_assumption_json(form, by_id, key, value)
        return cleaned, problems
    if candidates:
        return None, ["fenced code block is not valid JSON"]
    return None, []


def _shape_edit_ruling(value: Any) -> Any:
    """Shape one typed assumption ruling: ``edit: <text>`` (the form the
    rendered rule line teaches) becomes ``{"edit": text}``; a bare
    ``edit`` becomes ``{"edit": ""}`` so the validator names it; anything
    else passes through untouched for the validator to judge.
    """
    if not isinstance(value, str):
        return value
    match = _ASSUMPTION_EDIT_RE.match(value)
    return {"edit": (match.group(1) or "").strip()} if match else value


def _shape_assumption_json(
    form: FormSchema, by_id: dict[str, FormQuestion], key: str, value: Any
) -> Any:
    """Apply :func:`_shape_edit_ruling` inside a JSON reply — to the values
    of an assumption review's mapping and to its dotted per-item keys —
    so the ``edit: <text>`` string form the markdown rule line documents
    is accepted on the JSON path exactly as on the shorthand path (never
    a guess: the same deterministic regex).
    """
    question = by_id.get(key)
    if question is not None and question.type is QuestionType.ASSUMPTION_REVIEW:
        if isinstance(value, dict):
            return {item: _shape_edit_ruling(ruling) for item, ruling in value.items()}
        return value
    root_id, _, suffix = key.partition(".")
    root = by_id.get(root_id) if suffix else None
    if (
        root is not None
        and root.type is QuestionType.ASSUMPTION_REVIEW
        and not suffix.endswith(ASSUMPTION_TEXT_SUFFIX)
    ):
        return _shape_edit_ruling(value)
    return value


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
    number = decimal_key_number(key)
    if number is not None:
        index = number - 1
        if 0 <= index < len(form.questions):
            return form.questions[index].id, None
        return None, f"unknown field number: {key}"
    if "." in key:
        root, suffix = key.split(".", 1)
        if root in by_id:
            if by_id[root].type is QuestionType.TRIAGE:
                return key, None
            if by_id[root].type is QuestionType.ASSUMPTION_REVIEW:
                known = {triage_item_key(it) for it in by_id[root].assumptions or []}
                bare = (
                    suffix[: -len(ASSUMPTION_TEXT_SUFFIX)]
                    if suffix.endswith(ASSUMPTION_TEXT_SUFFIX)
                    else suffix
                )
                if suffix in known or (bare != suffix and bare in known):
                    return key, None
                return None, f"unknown assumption: {key!r}"
            if by_id[root].type is QuestionType.RANKING:
                slot = decimal_key_number(suffix)
                if slot is not None and 1 <= slot <= ranking_slot_count(by_id[root]):
                    return key, None
                return None, f"unknown rank slot: {key!r}"
            return None, f"dotted key on a field that has no dotted rows: {key!r}"
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
    silently dropped. Two same-precedence keys claiming one rank slot
    (``"prio.01"`` and ``"prio.1"`` both fold to slot 1) are a named
    problem too, matching the collect-time fold.
    """
    json_answers, problems = _json_block_answers(form, reply)
    has_block = json_answers is not None
    answers: dict[str, Any] = dict(json_answers or {})

    by_id = {q.id: q for q in form.questions}
    # Which keys the user TYPED (vs quoted in a pasted block) — the
    # ranking merge below needs the difference to keep typed precedence.
    typed_keys: set[str] = set()
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
        typed_keys.add(answer_key)
        question = by_id.get(answer_key)
        if question is None and "." in answer_key:
            root = by_id.get(answer_key.split(".", 1)[0])
            if root is not None and root.type is QuestionType.RANKING:
                # A dotted rank slot carries ONE option — never comma-split it,
                # and strip its ordinal only when that finds an option.
                answers[answer_key] = _rank_entry(root, value)
                continue
            if (
                root is not None
                and root.type is QuestionType.ASSUMPTION_REVIEW
                and not answer_key.endswith(ASSUMPTION_TEXT_SUFFIX)
            ):
                # ``edit: <text>`` shapes to the edit lane; accept/reject
                # (or anything else) pass through for the validator. A
                # typed ``<id>.<key>.text`` line is raw text for the fold.
                answers[answer_key] = _shape_edit_ruling(value)
                continue
        answers[answer_key] = _coerce(question, value) if question else value

    # Typed dotted rows must survive a quoted skeleton that already
    # carries the board's mapping (a suggested prefill keeps it
    # non-empty): merge "<board>.<item>" siblings into the mapping,
    # typed wins — otherwise the collect-time fold, whose mapping-wins
    # rule serves the other surfaces, strands them and the validator
    # re-asks an item the user answered (ultrareview finding).
    for q in form.questions:
        prefix = f"{q.id}."
        if q.type is QuestionType.TRIAGE:
            mapping = answers.get(q.id)
            if not isinstance(mapping, dict):
                continue
            for key in [k for k in answers if k.startswith(prefix)]:
                mapping[key[len(prefix) :]] = answers.pop(key)
        elif q.type is QuestionType.ASSUMPTION_REVIEW:
            mapping = answers.get(q.id)
            if not isinstance(mapping, dict):
                continue
            typed = {
                k[len(prefix) :]: answers.pop(k) for k in list(answers) if k.startswith(prefix)
            }
            # Rulings first, then text lanes pair onto edit rulings (a text
            # for a non-edit ruling is dropped — it is only read on edit).
            for item, value in typed.items():
                if not item.endswith(ASSUMPTION_TEXT_SUFFIX):
                    mapping[item] = value
            for item, value in typed.items():
                if not item.endswith(ASSUMPTION_TEXT_SUFFIX):
                    continue
                target = item[: -len(ASSUMPTION_TEXT_SUFFIX)]
                current = mapping.get(target)
                # Same precedence as the collect-time fold: a text lane
                # fills an EMPTY edit; inline `edit: <text>` wins otherwise.
                if current == "edit" or (
                    isinstance(current, dict) and not str(current.get("edit") or "").strip()
                ):
                    mapping[target] = {"edit": value}
        elif q.type is QuestionType.RANKING:
            # Same rule for a ranking: typed slots overlay a quoted list
            # (the skeleton may carry the proposed order); the merged
            # list is rebuilt in slot order so the validator sees one
            # answer, not a stranded slot. Quoted slots only overlay a
            # quoted list — never a TYPED one, which would invert this
            # function's precedence rule and discard the line the user
            # actually wrote (review finding, 2026-08-16). Two keys of
            # the SAME precedence folding to one slot ("prio.01" and
            # "prio.1" both fold to slot 1) is a named problem, not an
            # arbitrary winner — same rule as the collect-time fold
            # (pilot review finding, 2026-08-19); typed-over-quoted on
            # one slot stays the precedence rule, not a collision.
            typed: dict[int, Any] = {}
            quoted: dict[int, Any] = {}
            slot_sources: dict[tuple[bool, int], str] = {}
            for key in [k for k in answers if k.startswith(prefix)]:
                slot = decimal_key_number(key[len(prefix) :])
                if slot is None:
                    continue
                is_typed = key in typed_keys
                value = answers.pop(key)
                bucket = typed if is_typed else quoted
                if slot in bucket:
                    problems.append(
                        f"{q.id!r} rank slot {slot} is supplied more than "
                        f"once ({slot_sources[(is_typed, slot)]!r} and {key!r})"
                    )
                    continue
                slot_sources[(is_typed, slot)] = key
                bucket[slot] = value
            if not typed and not quoted:
                continue
            base = answers.get(q.id)
            slots = {i + 1: v for i, v in enumerate(base)} if isinstance(base, list) else {}
            if not (q.id in typed_keys and slots):
                slots.update(quoted)
            slots.update(typed)
            answers[q.id] = [slots[k] for k in sorted(slots)]

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
        # Attribute by the FIRST quoted token only: every collect-time
        # problem opens with the offending field id, and later quoted
        # tokens are values or vocabulary that may collide with a sibling
        # field's id (review finding, 2026-08-15 — a field named "edit"
        # was re-asked for an assumption board's bad ruling).
        quoted_tokens = _QUOTED_ID_RE.findall(problem)
        if not quoted_tokens:
            continue
        root = quoted_tokens[0].split(".", 1)[0]
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
            "Reply for just these fields — shorthand works (`field_id: value` or `N: value`).",
        ]
    return "\n".join(lines)
