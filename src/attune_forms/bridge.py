"""Declarative-form ↔ AskUserQuestion transforms.

See :mod:`attune_forms` for the package overview. This module
holds the three pure functions that build, render, and collect a
declarative form, reusing the surface-agnostic model in
:mod:`attune_forms.models` (decision D6 — reuse, don't
duplicate).

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from attune_forms.form_events import log_form_build, log_surface_decision
from attune_forms.models import (
    ASSUMPTION_RULINGS,
    ASSUMPTION_TEXT_SUFFIX,
    BOOLEAN_OPTIONS,
    CONFIRM_DEFAULT_OPTIONS,
    FormQuestion,
    FormResponse,
    FormSchema,
    QuestionType,
    decimal_key_number,
    expansion_items,
    ranking_slot_count,
    triage_item_key,
)

#: ISO-8601 calendar-date format used by DATE questions.
_DATE_FORMAT = "%Y-%m-%d"


def _is_number(value: Any) -> bool:
    """True if ``value`` is a real number (int or float, but not bool)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


class FormValidationError(ValueError):
    """Raised when a form definition or a set of answers is invalid.

    Carries a list of human-readable problems so a caller (or the agent)
    can re-ask exactly the offending fields rather than guess.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


def _parse_field_identity(
    where: str, raw: dict[str, Any], seen_ids: set[str]
) -> tuple[Any, Any, list[str]]:
    """Parse and validate a field's ``id`` and ``text``/``label``.

    Adds ``fid`` to ``seen_ids`` in place when it is a new, valid id.
    Returns the raw (possibly invalid) ``fid``/``text`` values alongside
    any problems — the caller only builds a :class:`FormQuestion` when
    both turn out to be non-empty strings, mirroring the original
    inline check at the end of the field loop.
    """
    problems: list[str] = []

    fid = raw.get("id")
    if not fid or not isinstance(fid, str):
        problems.append(f"{where} 'id' is required and must be a string")
    elif fid in seen_ids:
        problems.append(f"{where} duplicate id {fid!r}")
    else:
        seen_ids.add(fid)

    text = raw.get("text", raw.get("label"))
    if not text or not isinstance(text, str):
        problems.append(f"{where} 'text' (or 'label') is required")

    return fid, text, problems


def _resolve_question_type(where: str, type_str: Any) -> tuple[QuestionType | None, list[str]]:
    """Resolve a field's ``type`` string to a :class:`QuestionType`.

    Returns ``(None, [problem])`` on an unrecognised value. The caller
    must skip the rest of that field's parsing in that case — no
    options/bounds/extras are checked for a field whose type didn't
    resolve, matching the original's ``continue``.
    """
    try:
        return QuestionType(type_str), []
    except ValueError:
        valid = ", ".join(t.value for t in QuestionType)
        return None, [f"{where} invalid type {type_str!r} (use one of: {valid})"]


#: Question types whose control needs at least one option.
_OPTIONS_REQUIRED_TYPES = (
    QuestionType.SINGLE_SELECT,
    QuestionType.MULTI_SELECT,
    QuestionType.DECISION,
    QuestionType.PUSHBACK,
    QuestionType.DELIBERATION,
    QuestionType.RANKING,
)


def _parse_options(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[list[str], list[str]]:
    """Parse ``options`` and enforce non-empty for select-like types."""
    problems: list[str] = []
    options = raw.get("options", [])
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        problems.append(f"{where} 'options' must be a list of strings")
        options = []
    if qtype in _OPTIONS_REQUIRED_TYPES and not options:
        problems.append(f"{where} type {qtype.value} requires non-empty 'options'")
    return options, problems


def _parse_rich_control_constraints(
    where: str, raw: dict[str, Any]
) -> tuple[Any, Any, int | None, list[str]]:
    """Parse the v2.1 rich-control constraints: NUMBER range
    (``minimum``/``maximum``) and TEXT/TEXTAREA length (``max_length``).
    """
    problems: list[str] = []

    minimum = raw.get("minimum")
    if minimum is not None and not _is_number(minimum):
        problems.append(f"{where} 'minimum' must be a number")
        minimum = None
    maximum = raw.get("maximum")
    if maximum is not None and not _is_number(maximum):
        problems.append(f"{where} 'maximum' must be a number")
        maximum = None
    if _is_number(minimum) and _is_number(maximum) and minimum > maximum:
        problems.append(f"{where} 'minimum' {minimum} exceeds 'maximum' {maximum}")

    max_length = raw.get("max_length")
    if max_length is not None and (
        not isinstance(max_length, int) or isinstance(max_length, bool) or max_length <= 0
    ):
        problems.append(f"{where} 'max_length' must be a positive integer")
        max_length = None

    return minimum, maximum, max_length, problems


def _parse_decision_extras(
    where: str, raw: dict[str, Any], options: list[str]
) -> tuple[str | None, str | None, dict[str, str] | None, list[str]]:
    """Parse the v3 DECISION extras: rationale callout + recommended
    option + per-option tradeoffs. Parsed generically; only DECISION
    renders them. ``recommended`` must be an option; ``option_notes``
    keys too.
    """
    problems: list[str] = []

    rationale = raw.get("rationale")
    if rationale is not None and not isinstance(rationale, str):
        problems.append(f"{where} 'rationale' must be a string")
        rationale = None

    recommended = raw.get("recommended")
    if recommended is not None and not isinstance(recommended, str):
        problems.append(f"{where} 'recommended' must be a string")
        recommended = None
    elif recommended is not None and options and recommended not in options:
        problems.append(f"{where} 'recommended' {recommended!r} not in options")

    option_notes = raw.get("option_notes")
    if option_notes is not None and (
        not isinstance(option_notes, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in option_notes.items())
    ):
        problems.append(f"{where} 'option_notes' must be a map of strings")
        option_notes = None
    elif isinstance(option_notes, dict) and options:
        stray = [k for k in option_notes if k not in options]
        if stray:
            problems.append(f"{where} 'option_notes' keys not in options: {stray}")

    return rationale, recommended, option_notes, problems


def _parse_user_position(
    where: str, raw: dict[str, Any], options: list[str]
) -> tuple[str | None, list[str]]:
    """Parse the v4 PUSHBACK extra: ``user_position`` — the option that
    is the user's stated approach (tagged "your approach"). Parsed
    generically; only PUSHBACK renders it. Must be one of options when
    set.
    """
    user_position = raw.get("user_position")
    if user_position is not None and not isinstance(user_position, str):
        return None, [f"{where} 'user_position' must be a string"]
    if user_position is not None and options and user_position not in options:
        return user_position, [f"{where} 'user_position' {user_position!r} not in options"]
    return user_position, []


def _parse_progress_style(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[str | None, list[str]]:
    """Parse the v5.1 render variant ``progress_style``.

    "report" renders a neutral digest (status = free-form category tag,
    options = any subset of item labels offered as a "go deeper"
    picker). Pure presentation; the answer path is unchanged.
    """
    progress_style = raw.get("progress_style")
    if progress_style is None:
        return None, []
    if progress_style != "report":
        return None, [f"{where} 'progress_style' must be 'report'"]
    if qtype is not QuestionType.PROGRESS:
        return None, [f"{where} 'progress_style' is only valid on progress (got {qtype.value})"]
    return progress_style, []


def _validate_progress_item(
    where: str, idx: int, item: dict[str, Any], progress_style: str | None
) -> tuple[str | None, str | None, list[str]]:
    """Validate one ``progress_items`` entry.

    Returns ``(label_for_all_labels, label_for_blocked_labels,
    problems)``. The two label slots use different validity rules (the
    original's independent conditions, preserved exactly): the first
    requires a non-empty string label; the second only requires
    ``status == "blocked"`` and ``isinstance(label, str)`` — an empty
    string label on a blocked item still counts as blocked.
    """
    problems: list[str] = []
    valid_status = {"done", "in_flight", "blocked"}

    label = item.get("label")
    status = item.get("status")
    valid_label = label if isinstance(label, str) and label else None
    if valid_label is None:
        problems.append(f"{where} progress_items[{idx}] needs a 'label' string")

    if progress_style == "report":
        if not isinstance(status, str) or not status:
            problems.append(
                f"{where} progress_items[{idx}] 'status' must be "
                f"a non-empty tag string in report style"
            )
    elif status not in valid_status:
        problems.append(f"{where} progress_items[{idx}] 'status' must be one of {valid_status}")

    if "detail" in item and not isinstance(item["detail"], str):
        problems.append(f"{where} progress_items[{idx}] 'detail' must be a string")

    blocked_label = label if status == "blocked" and isinstance(label, str) else None
    return valid_label, blocked_label, problems


def _check_progress_item_consistency(
    where: str,
    qtype: QuestionType,
    progress_style: str | None,
    options: list[str],
    all_labels: list[str],
    blocked_labels: list[str],
) -> list[str]:
    """PROGRESS-only cross-check between ``options`` and the parsed
    items: "report" style options must name existing item labels;
    default style options must equal exactly the blocked-item labels.
    """
    if qtype is not QuestionType.PROGRESS:
        return []
    if progress_style == "report":
        stray = [o for o in options if o not in all_labels]
        if stray:
            return [f"{where} PROGRESS report options must be item labels; not items: {stray}"]
        return []
    if set(blocked_labels) != set(options):
        return [
            f"{where} PROGRESS blocked items {sorted(set(blocked_labels))} "
            f"must equal options {sorted(set(options))}"
        ]
    return []


def _parse_progress_items(
    where: str,
    raw: dict[str, Any],
    qtype: QuestionType,
    progress_style: str | None,
    options: list[str],
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """Parse the v5 PROGRESS extra ``progress_items``: the reported
    items keyed by status. Parsed generically; only PROGRESS renders
    them. Each item is {label, status, detail?}. Default (task) style:
    status in {done, in_flight, blocked}; the blocked subset's labels
    must equal options (the picker offers exactly the actionable
    items). "report" style: status is any non-empty category tag;
    options may be any subset of item labels. Both allow empty options
    (a pure status display).
    """
    progress_items = raw.get("progress_items")
    if progress_items is None:
        if qtype is QuestionType.PROGRESS:
            return None, [f"{where} type progress requires 'progress_items'"]
        return None, []

    if not isinstance(progress_items, list) or not all(
        isinstance(it, dict) for it in progress_items
    ):
        return None, [f"{where} 'progress_items' must be a list of dicts"]

    problems: list[str] = []
    all_labels: list[str] = []
    blocked_labels: list[str] = []
    for idx, item in enumerate(progress_items):
        valid_label, blocked_label, item_problems = _validate_progress_item(
            where, idx, item, progress_style
        )
        problems.extend(item_problems)
        if valid_label is not None:
            all_labels.append(valid_label)
        if blocked_label is not None:
            blocked_labels.append(blocked_label)

    problems.extend(
        _check_progress_item_consistency(
            where, qtype, progress_style, options, all_labels, blocked_labels
        )
    )
    return progress_items, problems


def _parse_progress_extras(
    where: str, raw: dict[str, Any], qtype: QuestionType, options: list[str]
) -> tuple[str | None, list[dict[str, Any]] | None, list[str]]:
    """Parse the v5.1 ``progress_style`` render variant and the v5
    PROGRESS ``progress_items`` payload. ``progress_style`` is resolved
    first so the item validation can branch on it, matching the
    original single-pass order.
    """
    progress_style, style_problems = _parse_progress_style(where, raw, qtype)
    progress_items, item_problems = _parse_progress_items(
        where, raw, qtype, progress_style, options
    )
    return progress_style, progress_items, [*style_problems, *item_problems]


def _parse_endorsements(
    where: str, raw: dict[str, Any], qtype: QuestionType, options: list[str]
) -> tuple[dict[str, list[str]] | None, list[str]]:
    """Parse the v6 DELIBERATION extra ``endorsements``: {option: [voice,
    ...]} naming which deliberating voices back each option. Required
    and non-empty for DELIBERATION (without any endorsement the
    construct is just a decision — ``{}`` used to satisfy the check
    vacuously; chair ruling 2026-08-20), invalid elsewhere. Keys must be
    options; each value a non-empty list of non-empty names. Options
    nobody endorsed are allowed — the chair may table a position no
    voice proposed.
    """
    endorsements = raw.get("endorsements")
    if endorsements is None:
        if qtype is QuestionType.DELIBERATION:
            return None, [f"{where} type deliberation requires 'endorsements'"]
        return None, []
    if qtype is not QuestionType.DELIBERATION:
        return None, [f"{where} 'endorsements' is only valid on deliberation (got {qtype.value})"]
    if not isinstance(endorsements, dict) or not all(
        isinstance(opt, str)
        and isinstance(names, list)
        and names
        and all(isinstance(n, str) and n for n in names)
        for opt, names in endorsements.items()
    ):
        return None, [f"{where} 'endorsements' must map option -> non-empty list of names"]
    if not endorsements:
        return None, [
            f"{where} type deliberation requires at least one endorsement "
            "(an empty 'endorsements' is just a decision)"
        ]
    stray = [opt for opt in endorsements if opt not in options]
    if stray:
        return None, [f"{where} 'endorsements' keys not in options: {stray}"]
    return endorsements, []


def _parse_triage_items(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[list[dict[str, str]] | None, list[str]]:
    """Parse the v6 TRIAGE extra ``triage_items``: the reviewed items as
    {label, detail?, tag?} dicts. Required for TRIAGE, invalid elsewhere.
    Labels must be unique non-empty strings — they key the answer mapping,
    so a duplicate would make two rulings collide.
    """
    triage_items = raw.get("triage_items")
    if triage_items is None:
        if qtype is QuestionType.TRIAGE:
            return None, [f"{where} type triage requires 'triage_items'"]
        return None, []
    if qtype is not QuestionType.TRIAGE:
        return None, [f"{where} 'triage_items' is only valid on triage (got {qtype.value})"]
    if not isinstance(triage_items, list) or not triage_items:
        return None, [f"{where} 'triage_items' must be a non-empty list"]

    problems: list[str] = []
    seen_keys: set[str] = set()
    for idx, item in enumerate(triage_items):
        if not isinstance(item, dict):
            problems.append(f"{where} triage_items[{idx}] must be a mapping")
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label:
            problems.append(f"{where} triage_items[{idx}] needs a 'label' string")
            continue
        if "id" in item and (not isinstance(item["id"], str) or not item["id"]):
            problems.append(f"{where} triage_items[{idx}] 'id' must be a non-empty string")
            continue
        key = triage_item_key(item)
        if key in seen_keys:
            problems.append(f"{where} triage_items[{idx}] duplicate key {key!r}")
        else:
            seen_keys.add(key)
        for extra in ("detail", "tag"):
            if extra in item and not isinstance(item[extra], str):
                problems.append(f"{where} triage_items[{idx}] '{extra}' must be a string")
    return (triage_items if not problems else None), problems


def _parse_dispositions(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[list[str] | None, list[str]]:
    """Parse the v6 TRIAGE extra ``dispositions``: the shared per-item
    ruling vocabulary. Required for TRIAGE, invalid elsewhere. At least
    two unique non-empty strings — a one-word vocabulary is a rubber
    stamp, not a ruling.
    """
    dispositions = raw.get("dispositions")
    if dispositions is None:
        if qtype is QuestionType.TRIAGE:
            return None, [f"{where} type triage requires 'dispositions'"]
        return None, []
    if qtype is QuestionType.ASSUMPTION_REVIEW:
        return None, []  # named (with the D2-a reason) by _parse_assumption_extras
    if qtype is not QuestionType.TRIAGE:
        return None, [f"{where} 'dispositions' is only valid on triage (got {qtype.value})"]
    if (
        not isinstance(dispositions, list)
        or len(dispositions) < 2
        or not all(isinstance(d, str) and d for d in dispositions)
        or len(set(dispositions)) != len(dispositions)
    ):
        return None, [f"{where} 'dispositions' must be >=2 unique non-empty strings"]
    return dispositions, []


def _parse_suggested(
    where: str,
    raw: dict[str, Any],
    qtype: QuestionType,
    triage_items: list[dict[str, str]] | None,
    dispositions: list[str] | None,
) -> tuple[dict[str, str] | None, list[str]]:
    """Parse the v6 TRIAGE extra ``suggested``: {item label: disposition},
    the agent's proposed ruling per item (rendered pre-selected + marked).
    Optional; keys must be item labels, values dispositions.
    """
    suggested = raw.get("suggested")
    if suggested is None or qtype in (QuestionType.RANKING, QuestionType.ASSUMPTION_REVIEW):
        # A ranking's ``suggested`` is an ORDER (a list), parsed by
        # ``_parse_ranking_extras``; an assumption review's is parsed by
        # ``_parse_assumption_extras`` (accept-only, D2-b).
        return None, []
    if qtype is not QuestionType.TRIAGE:
        return None, [
            f"{where} 'suggested' is only valid on triage, ranking or "
            f"assumption_review (got {qtype.value})"
        ]
    if not isinstance(suggested, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in suggested.items()
    ):
        return None, [f"{where} 'suggested' must be a map of item key -> disposition"]
    keys = {triage_item_key(it) for it in triage_items or []}
    stray = [k for k in suggested if k not in keys]
    if stray:
        return None, [f"{where} 'suggested' keys not in triage item keys: {stray}"]
    if dispositions is not None:
        bad = [f"{k}: {v!r}" for k, v in suggested.items() if v not in dispositions]
        if bad:
            return None, [f"{where} 'suggested' values not in dispositions: {bad}"]
    return suggested, []


#: The D2 constructs forbid a ``default`` outright — a pre-selected
#: approval, a pre-filled order, or a pre-marked ruling defeats the
#: two-way gate; approving/ordering/ruling must be an explicit act.
#: Each entry is the rationale clause appended to the rejection message
#: so one word ("default") keeps one meaning across constructs. The
#: prohibition is enforced BOTH definition-side (the ``_parse_*_extras``
#: helpers, via :func:`form_from_dict`) AND on the collect/inject path
#: (:func:`collect_form_response`) — a :class:`FormQuestion` built
#: directly by the dataclass constructor bypasses ``form_from_dict``,
#: and without the collect-path guard an unanswered gate would silently
#: inject its default as the answer (checkpoint-2 promoted item,
#: 2026-08-20).
_NO_DEFAULT_REASON: dict[QuestionType, str] = {
    QuestionType.CONFIRM: "D2: no pre-selected approval",
    QuestionType.RANKING: "D2-c: a proposed order is 'suggested'",
    QuestionType.ASSUMPTION_REVIEW: "a pre-marked ruling is 'suggested'",
}


def _parse_confirm_extras(
    where: str, raw: dict[str, Any], qtype: QuestionType, options: list[str]
) -> tuple[list[dict[str, str]] | None, list[str], list[str]]:
    """Parse the v7 CONFIRM extras and enforce its gate rules.

    Returns ``(consequences, options, problems)`` — options come back
    defaulted to :data:`~attune_forms.models.CONFIRM_DEFAULT_OPTIONS`
    when the author named none, and any count other than two is a
    definition error (D1: the gate is two-way, always).

    ``consequences`` is required for CONFIRM (a confirm with nothing to
    preview is a bare boolean and should be one) and invalid elsewhere:
    a non-empty list of {label, severity?, detail?} dicts.

    D2 (chair-ratified 2026-08-14): ``default`` and ``recommended`` are
    REJECTED on a confirm — a pre-selected or pre-badged approval
    defeats the gate; approving must be an explicit act.
    """
    consequences = raw.get("consequences")
    if qtype is not QuestionType.CONFIRM:
        if consequences is not None:
            return (
                None,
                options,
                [f"{where} 'consequences' is only valid on confirm (got {qtype.value})"],
            )
        return None, options, []

    problems: list[str] = []

    if not options:
        options = list(CONFIRM_DEFAULT_OPTIONS)
    elif len(options) != 2:
        problems.append(f"{where} type confirm requires exactly 2 options (got {len(options)})")

    if raw.get("default") is not None:
        problems.append(
            f"{where} 'default' is not permitted on confirm "
            f"({_NO_DEFAULT_REASON[QuestionType.CONFIRM]})"
        )
    if raw.get("recommended") is not None:
        problems.append(
            f"{where} 'recommended' is not permitted on confirm (D2: no pre-badged approval)"
        )

    if consequences is None:
        problems.append(f"{where} type confirm requires 'consequences'")
        return None, options, problems
    if (
        not isinstance(consequences, list)
        or not consequences
        or not all(isinstance(c, dict) for c in consequences)
    ):
        problems.append(f"{where} 'consequences' must be a non-empty list of dicts")
        return None, options, problems

    for idx, item in enumerate(consequences):
        label = item.get("label")
        if not isinstance(label, str) or not label:
            problems.append(f"{where} consequences[{idx}] needs a 'label' string")
        for extra in ("severity", "detail"):
            if extra in item and not isinstance(item[extra], str):
                problems.append(f"{where} consequences[{idx}] '{extra}' must be a string")

    return (consequences if not problems else None), options, problems


def _parse_ranking_extras(
    where: str, raw: dict[str, Any], qtype: QuestionType, options: list[str]
) -> tuple[int | None, list[str] | None, list[str]]:
    """Parse the v8 RANKING extras and enforce its rules (spec R1).

    Returns ``(top_n, suggested_order, problems)``.

    - ``options``: >= 2 unique non-empty strings (a ranking of one is
      not a ranking; a repeated option cannot be ordered).
    - ``top_n``: optional int with ``1 <= top_n <= len(options)``; when
      absent the answer is a full permutation.
    - ``suggested``: optional proposed order — a list of distinct
      options whose length equals the answer length (D2-c: rendered
      visibly as a proposal, never as the answer).
    - ``default``: REJECTED (D2-c) — a pre-filled order is ``suggested``,
      so the answer stays an explicit act and one word keeps one meaning
      across constructs.

    ``top_n`` is invalid on every other type.
    """
    top_n = raw.get("top_n")
    if qtype is not QuestionType.RANKING:
        if top_n is not None:
            return None, None, [f"{where} 'top_n' is only valid on ranking (got {qtype.value})"]
        return None, None, []

    problems: list[str] = []
    if len(options) < 2 or len(set(options)) != len(options) or not all(options):
        problems.append(f"{where} type ranking requires >= 2 unique non-empty options")

    if top_n is not None:
        if isinstance(top_n, bool) or not isinstance(top_n, int):
            problems.append(f"{where} 'top_n' must be an integer")
            top_n = None
        elif not 1 <= top_n <= len(options):
            problems.append(f"{where} 'top_n' must be between 1 and {len(options)} (got {top_n})")
            top_n = None

    if raw.get("default") is not None:
        problems.append(
            f"{where} 'default' is not permitted on ranking "
            f"({_NO_DEFAULT_REASON[QuestionType.RANKING]})"
        )

    suggested = raw.get("suggested")
    if suggested is not None:
        expected = top_n if top_n is not None else len(options)
        if not isinstance(suggested, list) or not all(isinstance(s, str) for s in suggested):
            problems.append(f"{where} 'suggested' on ranking must be a list of options (an order)")
            suggested = None
        else:
            order_problems: list[str] = []
            stray = [s for s in suggested if s not in options]
            if stray:
                order_problems.append(f"{where} 'suggested' entries not in options: {stray}")
            if len(set(suggested)) != len(suggested):
                order_problems.append(f"{where} 'suggested' order repeats an option")
            if len(suggested) != expected:
                order_problems.append(
                    f"{where} 'suggested' order must name exactly {expected} option(s) "
                    f"(got {len(suggested)})"
                )
            if order_problems:
                problems.extend(order_problems)
                suggested = None

    return top_n, suggested, problems


def _parse_assumption_extras(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[list[dict[str, str]] | None, dict[str, str] | None, list[str]]:
    """Parse the v8 ASSUMPTION_REVIEW extras and enforce its rules (spec R1).

    Returns ``(assumptions, suggested, problems)``.

    - ``assumptions``: required, non-empty list of {label, id?, detail?,
      source?} — the ``triage_items`` shape plus ``source``; keys
      (:func:`triage_item_key`) unique.
    - The ruling vocabulary is FIXED (:data:`ASSUMPTION_RULINGS`, D2-a):
      ``dispositions`` is rejected here — a renameable vocabulary would
      let the construct drift into a triage clone.
    - ``suggested``: optional {item key: "accept"} — accept ONLY (D2-b);
      pre-marking edit or reject on the user's behalf is rejected.
    - ``default``: rejected (a pre-marked ruling is ``suggested``).

    ``assumptions`` is invalid on every other type.
    """
    assumptions = raw.get("assumptions")
    if qtype is not QuestionType.ASSUMPTION_REVIEW:
        if assumptions is not None:
            return (
                None,
                None,
                [f"{where} 'assumptions' is only valid on assumption_review (got {qtype.value})"],
            )
        return None, None, []

    problems: list[str] = []
    if raw.get("dispositions") is not None:
        problems.append(
            f"{where} 'dispositions' is not permitted on assumption_review "
            f"(D2-a: the vocabulary is fixed — {' / '.join(ASSUMPTION_RULINGS)})"
        )
    if raw.get("default") is not None:
        problems.append(
            f"{where} 'default' is not permitted on assumption_review "
            f"({_NO_DEFAULT_REASON[QuestionType.ASSUMPTION_REVIEW]})"
        )

    if assumptions is None:
        problems.append(f"{where} type assumption_review requires 'assumptions'")
        return None, None, problems
    if not isinstance(assumptions, list) or not assumptions:
        problems.append(f"{where} 'assumptions' must be a non-empty list")
        return None, None, problems

    seen_keys: set[str] = set()
    seen_labels: set[str] = set()
    for idx, item in enumerate(assumptions):
        if not isinstance(item, dict):
            problems.append(f"{where} assumptions[{idx}] must be a mapping")
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label:
            problems.append(f"{where} assumptions[{idx}] needs a 'label' string")
            continue
        if "id" in item and (not isinstance(item["id"], str) or not item["id"]):
            problems.append(f"{where} assumptions[{idx}] 'id' must be a non-empty string")
            continue
        key = triage_item_key(item)
        if key in seen_keys:
            problems.append(f"{where} assumptions[{idx}] duplicate key {key!r}")
        else:
            seen_keys.add(key)
        if label in seen_labels:
            # R1: labels unique — two identical rows would be
            # indistinguishable to the user even with distinct ids.
            problems.append(f"{where} assumptions[{idx}] duplicate label {label!r}")
        seen_labels.add(label)
        if key.endswith(ASSUMPTION_TEXT_SUFFIX):
            # The paired flat-surface text question is "<id>.<key>.text";
            # a key that itself ends in ".text" would be read as another
            # item's text lane.
            problems.append(
                f"{where} assumptions[{idx}] key {key!r} may not end with "
                f"'{ASSUMPTION_TEXT_SUFFIX}' (reserved for the edit-text lane)"
            )
        for extra in ("detail", "source"):
            if extra in item and not isinstance(item[extra], str):
                problems.append(f"{where} assumptions[{idx}] '{extra}' must be a string")

    suggested = raw.get("suggested")
    if suggested is not None:
        if not isinstance(suggested, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in suggested.items()
        ):
            problems.append(f"{where} 'suggested' must be a map of item key -> 'accept'")
            suggested = None
        else:
            stray = [k for k in suggested if k not in seen_keys]
            if stray:
                problems.append(f"{where} 'suggested' keys not in assumption keys: {stray}")
            not_accept = [f"{k}: {v!r}" for k, v in suggested.items() if v != "accept"]
            if not_accept:
                problems.append(
                    f"{where} 'suggested' may pre-mark 'accept' only (D2-b): {not_accept}"
                )
            if stray or not_accept:
                suggested = None

    return (assumptions if not problems else None), suggested, problems


def _parse_inferred_from(where: str, raw: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Parse ``inferred_from`` — the provenance of an inferred default.

    An inference with no value is meaningless, so ``inferred_from``
    requires ``default``. Rejecting that pairing here keeps the renderer
    honest: it can mark a field as a guess only when there is a guess to
    mark, so a "(guessed)" badge can never appear over an empty control.
    """
    inferred_from = raw.get("inferred_from")
    if inferred_from is None:
        return None, []
    if not isinstance(inferred_from, str) or not inferred_from.strip():
        return None, [f"{where} 'inferred_from' must be a non-empty string"]
    if raw.get("default") is None:
        return None, [f"{where} 'inferred_from' requires 'default' (the inferred value)"]
    return inferred_from.strip(), []


def _parse_list_style(
    where: str, raw: dict[str, Any], qtype: QuestionType
) -> tuple[str | None, list[str]]:
    """Parse the render variant ``list_style``: render select options as
    an ordered/unordered selectable list. Only valid on the select
    types; pure presentation, the answer and its validation are
    unchanged.
    """
    list_style = raw.get("list_style")
    if list_style is None:
        return None, []
    if list_style not in ("ordered", "unordered"):
        return None, [f"{where} 'list_style' must be 'ordered' or 'unordered'"]
    if qtype not in (QuestionType.SINGLE_SELECT, QuestionType.MULTI_SELECT):
        return None, [
            f"{where} 'list_style' is only valid on single_select / "
            f"multi_select (got {qtype.value})"
        ]
    return list_style, []


# The definition-side twin of the #37 answer-side gate: a key the field
# parsers never read is a typo or an unsupported construct, and silently
# ignoring it invents a constraint that does not exist ("maximun": 10 →
# the bound is never built and collect(99999) validates clean). These
# sets must track exactly what form_from_dict and its _parse_* helpers
# read; the parity test against the MCP _field_schema ratchets that.
_DEFINITION_TOP_KEYS = frozenset({"title", "description", "fields", "questions", "form_id"})

#: An explicit definition ``form_id``: short, filesystem/log-safe token.
_FORM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _derived_form_id(data: dict[str, Any]) -> str:
    """Deterministic id from the definition content.

    The render call and the collect call each re-parse the same dict,
    so hashing the canonical JSON gives both the SAME id — lifecycle
    stages join in telemetry without the agent threading anything.
    Content-addressed, not unique-per-cast: two casts of an identical
    definition share an id, which is exactly what the stage-latency
    join wants (first render → first submission).
    """
    try:
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:  # noqa: BLE001
        # ``default=str`` re-raises whatever a value's __str__ raises, so
        # TypeError/ValueError alone is not enough — a telemetry id must
        # never make a valid definition fail to parse (codex cross-review
        # finding 3, 2026-08-24).
        return ""
    digest = hashlib.sha1(canonical.encode("utf-8", "replace"), usedforsecurity=False)
    return digest.hexdigest()[:12]


_DEFINITION_FIELD_KEYS = frozenset(
    {
        "id",
        "text",
        "label",
        "type",
        "options",
        "default",
        "help_text",
        "required",
        "minimum",
        "maximum",
        "max_length",
        "rationale",
        "recommended",
        "option_notes",
        "user_position",
        "progress_items",
        "progress_style",
        "endorsements",
        "triage_items",
        "dispositions",
        "suggested",
        "consequences",
        "list_style",
        "inferred_from",
        "top_n",
        "assumptions",
    }
)


def form_from_dict(data: dict[str, Any], *, source: str = "dict") -> FormSchema:
    """Build a :class:`FormSchema` from plain serializable data (D3).

    The declarative artifact a skill / future designer / data source
    produces. Validates the form *definition* (not answers) and raises
    :class:`FormValidationError` listing every problem. A key the
    parser does not read — top-level or field-level — is a definition
    problem, not ignorable extra data: a typo'd ``"maximun"`` would
    otherwise silently drop the bound it meant to declare.

    Args:
        data: ``{"title": str, "description"?: str, "fields": [ ... ]}``.
            Each field: ``{"id": str, "text": str, "type": str,
            "options"?: list[str], "default"?: str, "help_text"?: str,
            "required"?: bool}``. ``"label"`` is accepted as an alias for
            ``"text"``; ``"questions"`` as an alias for ``"fields"``.
            An optional top-level ``"form_id"`` (short
            ``[A-Za-z0-9._-]`` token) names the telemetry lifecycle id
            explicitly; omitted, a deterministic content hash is used.
        source: Where the definition came from, recorded on the
            ``form_build`` telemetry event — ``"dict"`` (default) or
            ``"template:<name>"`` (set by ``form_from_template``).

    Returns:
        A validated :class:`FormSchema`.

    Raises:
        FormValidationError: If the definition is malformed, including
            any unknown definition key.
    """
    problems: list[str] = []

    if not isinstance(data, dict):
        raise FormValidationError(["form must be a mapping"])

    title = data.get("title")
    if not title or not isinstance(title, str):
        problems.append("form 'title' is required and must be a string")

    raw_fields = data.get("fields", data.get("questions"))
    if not isinstance(raw_fields, list) or not raw_fields:
        problems.append("form must have a non-empty 'fields' list")
        raw_fields = []

    form_id = ""
    raw_form_id = data.get("form_id")
    if raw_form_id is not None:
        if isinstance(raw_form_id, str) and _FORM_ID_RE.match(raw_form_id):
            form_id = raw_form_id
        else:
            problems.append(
                "form 'form_id' must be a 1-64 char [A-Za-z0-9._-] string"
                " starting with a letter or digit"
            )

    for key in data:
        if key not in _DEFINITION_TOP_KEYS:
            problems.append(f"form has unknown definition key {key!r}")

    seen_ids: set[str] = set()
    questions: list[FormQuestion] = []
    for idx, raw in enumerate(raw_fields):
        where = f"field[{idx}]"
        if not isinstance(raw, dict):
            problems.append(f"{where} must be a mapping")
            continue

        for key in raw:
            if key not in _DEFINITION_FIELD_KEYS:
                problems.append(f"{where} unknown definition key {key!r}")

        fid, text, id_problems = _parse_field_identity(where, raw, seen_ids)
        problems.extend(id_problems)

        qtype, type_problems = _resolve_question_type(where, raw.get("type"))
        problems.extend(type_problems)
        if qtype is None:
            continue

        options, options_problems = _parse_options(where, raw, qtype)
        problems.extend(options_problems)

        minimum, maximum, max_length, constraint_problems = _parse_rich_control_constraints(
            where, raw
        )
        problems.extend(constraint_problems)

        rationale, recommended, option_notes, decision_problems = _parse_decision_extras(
            where, raw, options
        )
        problems.extend(decision_problems)

        user_position, position_problems = _parse_user_position(where, raw, options)
        problems.extend(position_problems)

        progress_style, progress_items, progress_problems = _parse_progress_extras(
            where, raw, qtype, options
        )
        problems.extend(progress_problems)

        # A PROGRESS with no options is a pure status display: there is
        # nothing to answer, so an omitted `required` defaults to False
        # instead of the usual True — otherwise the definition passes but
        # collect fails both ways (no answer → required, any answer → not
        # in options). An EXPLICIT required=True is the author asserting
        # an answerable picker, so it is named as a definition problem
        # rather than silently overridden.
        required = bool(raw.get("required", True))
        if qtype is QuestionType.PROGRESS and not options:
            if raw.get("required"):
                problems.append(
                    f"{where} PROGRESS with no options is display-only and cannot be required"
                )
            required = False

        endorsements, endorsement_problems = _parse_endorsements(where, raw, qtype, options)
        problems.extend(endorsement_problems)

        triage_items, triage_item_problems = _parse_triage_items(where, raw, qtype)
        problems.extend(triage_item_problems)

        dispositions, disposition_problems = _parse_dispositions(where, raw, qtype)
        problems.extend(disposition_problems)

        suggested, suggested_problems = _parse_suggested(
            where, raw, qtype, triage_items, dispositions
        )
        problems.extend(suggested_problems)

        consequences, options, confirm_problems = _parse_confirm_extras(where, raw, qtype, options)
        problems.extend(confirm_problems)

        top_n, suggested_order, ranking_problems = _parse_ranking_extras(where, raw, qtype, options)
        problems.extend(ranking_problems)
        if suggested_order is not None:
            suggested = suggested_order

        assumptions, suggested_accepts, assumption_problems = _parse_assumption_extras(
            where, raw, qtype
        )
        problems.extend(assumption_problems)
        if suggested_accepts is not None:
            suggested = suggested_accepts

        list_style, list_style_problems = _parse_list_style(where, raw, qtype)
        problems.extend(list_style_problems)

        inferred_from, inferred_problems = _parse_inferred_from(where, raw)
        problems.extend(inferred_problems)

        if fid and text and isinstance(fid, str) and isinstance(text, str):
            question = FormQuestion(
                id=fid,
                text=text,
                type=qtype,
                options=options,
                default=raw.get("default"),
                help_text=raw.get("help_text"),
                required=required,
                minimum=minimum,
                maximum=maximum,
                max_length=max_length,
                rationale=rationale,
                option_notes=option_notes,
                recommended=recommended,
                user_position=user_position,
                progress_items=progress_items,
                progress_style=progress_style,
                endorsements=endorsements,
                triage_items=triage_items,
                dispositions=dispositions,
                suggested=suggested,
                consequences=consequences,
                list_style=list_style,
                inferred_from=inferred_from,
                top_n=top_n,
                assumptions=assumptions,
            )
            # R4 applies to the definition too: a `default` is a
            # pre-supplied answer, so it passes the same per-type
            # validator an agent's answer would — otherwise collect
            # injects it unvalidated and an out-of-vocabulary or
            # wrongly-typed default lands in a "validated" FormResponse
            # (pilot review finding, 2026-08-19). The D2 constructs
            # (CONFIRM / RANKING / ASSUMPTION_REVIEW) already rejected
            # `default` outright before this point.
            if question.default is not None:
                default_problem = _validate_answer(question, question.default)
                if default_problem:
                    problems.append(f"{where} invalid 'default': {default_problem}")
            questions.append(question)

    # The dotted answer namespace must be collision-free BY DEFINITION:
    # every flat surface (AskUserQuestion expansion, elicitation schema,
    # markdown shorthand) writes triage answers as "<board id>.<item>"
    # and ranking answers as "<field id>.<slot>", and the collect-time
    # fold claims every key with that prefix — a sibling field id inside
    # the namespace would have its answer stolen (review finding,
    # 2026-08-14). Rejecting the definition keeps every downstream
    # consumer safe without per-surface guards.
    for owner in questions:
        if owner.type not in _EXPANDING_TYPES:
            continue
        for question in questions:
            if question.id != owner.id and question.id.startswith(f"{owner.id}."):
                problems.append(
                    f"field id {question.id!r} collides with {owner.type.value} "
                    f"{owner.id!r}'s dotted answer namespace ('{owner.id}.<key>')"
                )

    # The widget's "::" radio-group namespace needs the SAME by-definition
    # guard: a TRIAGE / ASSUMPTION_REVIEW board with id "a" renders one
    # radio group per item named "a::<idx>", so a sibling field whose id is
    # literally "a::1" emits a group sharing that name — the browser fuses
    # them into one mutually-exclusive group and one field becomes
    # unanswerable (confirmation-pass-2 finding, 2026-08-20). Reject at
    # definition, symmetric with the dotted guard above.
    for owner in questions:
        if owner.type not in _WIDGET_RADIO_GROUP_TYPES:
            continue
        for question in questions:
            if question.id != owner.id and question.id.startswith(f"{owner.id}::"):
                problems.append(
                    f"field id {question.id!r} collides with {owner.type.value} "
                    f"{owner.id!r}'s widget radio-group namespace ('{owner.id}::<idx>')"
                )

    if problems:
        raise FormValidationError(problems)

    schema = FormSchema(
        title=title,
        description=data.get("description", "") or "",
        questions=questions,
        form_id=form_id or _derived_form_id(data),
    )
    log_form_build(schema.form_id, source=source, question_count=len(questions))
    return schema


#: Question types that lose fidelity on ``AskUserQuestion`` — either
#: because the surface has no control for them at all
#: (:data:`_NO_PORTABLE_CONTROL`) or because the construct's card layout
#: flattens into prose (``decision`` / ``pushback`` / ``progress``).
#: See :func:`needs_widget`.
_WIDGET_ONLY_TYPES = frozenset(
    {
        QuestionType.NUMBER,
        QuestionType.DATE,
        QuestionType.TEXTAREA,
        QuestionType.DECISION,
        QuestionType.PUSHBACK,
        QuestionType.PROGRESS,
        QuestionType.DELIBERATION,
        QuestionType.TRIAGE,
        QuestionType.CONFIRM,
        QuestionType.RANKING,
        QuestionType.ASSUMPTION_REVIEW,
    }
)

#: Types whose answer has no single flat-surface payload and therefore
#: EXPANDS to dotted keys (``"<id>.<key>"``), folding back in
#: :func:`collect_form_response`: TRIAGE (one key per item) and RANKING
#: (one key per rank slot, D2-b), and ASSUMPTION_REVIEW (one key per
#: item plus a paired ``"<id>.<key>.text"`` for the edit lane). Which
#: surfaces expand differs by type: AskUserQuestion and markdown
#: shorthand expand all three, while the elicitation schema expands
#: triage and assumption review but carries a ranking as ONE bounded
#: array property (``elicitation_schema._property_for``) — the fold
#: accepts either shape.
_EXPANDING_TYPES = frozenset(
    {QuestionType.TRIAGE, QuestionType.RANKING, QuestionType.ASSUMPTION_REVIEW}
)

#: Types whose widget renders one radio *group per item*, named
#: ``"<field id>::<item index>"`` (see ``_control_triage_html`` /
#: ``_control_assumption_review_html``). That ``::`` group namespace is a
#: second reserved namespace — a sibling field whose literal id is
#: ``"<board id>::<N>"`` would emit a radio group sharing the board row's
#: ``name``, and the browser would treat them as ONE mutually-exclusive
#: group, making one field unanswerable (confirmation-pass-2 finding,
#: 2026-08-20). RANKING is in :data:`_EXPANDING_TYPES` but NOT here: its
#: widget groups by ``data-opt``, never by a ``::`` radio name, so it owns
#: no such namespace.
_WIDGET_RADIO_GROUP_TYPES = frozenset({QuestionType.TRIAGE, QuestionType.ASSUMPTION_REVIEW})

#: The strict subset with NO portable ``AskUserQuestion`` control at
#: all. A form using any of these cannot be asked on ``AskUserQuestion``
#: in any form — unlike the v3–v5 constructs, which are expressible but
#: lossy (they degrade to a recommendation-first single-select). D21
#: splits these two cases: "impossible" is a hard routing constraint,
#: "lossy" is a fidelity preference the user may override.
_NO_PORTABLE_CONTROL = frozenset(
    {
        QuestionType.NUMBER,
        QuestionType.DATE,
        QuestionType.TEXTAREA,
    }
)

#: An option label longer than this is evidence the author folded
#: tradeoffs into the label text — the thing a card renders properly.
#: Used by :func:`is_trivial_form` as a mechanical "this wanted to be a
#: card" detector (D21, Claude seat).
_TRIVIAL_OPTION_LABEL_MAX = 120

#: Max options a form may carry and still count as trivial. Comparison
#: strain starts around here, and it is also ``AskUserQuestion``'s own
#: practical ceiling for a scannable button row.
_TRIVIAL_MAX_OPTIONS = 3


def needs_widget(form: FormSchema) -> bool:
    """Return True iff ``form`` loses fidelity on ``AskUserQuestion``.

    True when any field is a rich control (``number`` / ``date`` /
    ``textarea``) or a v3–v5 construct (``decision`` / ``pushback`` /
    ``progress``) — the controls that either have no portable
    ``AskUserQuestion`` equivalent or flatten into prose on it.

    .. note::
       This predicate no longer owns the surface decision (D21). It is
       the low-level *controls* check; :func:`select_form_surface` is
       the product-level router and calls this as one input among
       several. Prefer the selector at call sites.

    Args:
        form: The form to inspect.

    Returns:
        True if rendering on ``AskUserQuestion`` would lose fidelity.
    """
    return any(question.type in _WIDGET_ONLY_TYPES for question in form.questions)


def is_trivial_form(form: FormSchema) -> bool:
    """Return True iff ``form`` is small enough that buttons lose nothing.

    Mechanical and deliberately narrow (D21): a form is trivial only
    when it is a single low-ceremony choice with nothing to compare.
    Every clause must hold — one question, a plain select/boolean,
    at most :data:`_TRIVIAL_MAX_OPTIONS` options, and no option label
    long enough to suggest a tradeoff was folded into it.

    The length clause is the load-bearing one: when an author smuggles
    tradeoffs into option text, the strings get long, and that is
    exactly the form that wanted a card.

    Args:
        form: The form to inspect.

    Returns:
        True if the form can go to ``AskUserQuestion`` with no loss.
    """
    if len(form.questions) != 1:
        return False
    question = form.questions[0]
    if question.type not in (QuestionType.SINGLE_SELECT, QuestionType.BOOLEAN):
        return False
    options = question.options or []
    if len(options) > _TRIVIAL_MAX_OPTIONS:
        return False
    return all(len(str(option)) <= _TRIVIAL_OPTION_LABEL_MAX for option in options)


def is_fully_inferred(form: FormSchema) -> bool:
    """Return True iff every field's value was inferred from context.

    Such a form has nothing left to ask — the agent already believes it
    knows every answer. It is still rendered, as a one-tap confirmation
    rather than a question (chair-ruled 2026-07-25): skipping would be
    faster, but a silent correct-looking guess is the one failure a form
    cannot recover from, because the user never gets the chance to catch
    it. Confirmation keeps inference reviewable.

    Empty forms are not "fully inferred" — there is nothing to confirm.

    Args:
        form: The form to inspect.

    Returns:
        True if every question carries an inferred value.
    """
    if not form.questions:
        return False
    return all(question.inferred_from for question in form.questions)


def inferred_field_count(form: FormSchema) -> int:
    """Number of fields whose value was inferred from context."""
    return sum(1 for question in form.questions if question.inferred_from)


def select_form_surface(
    form: FormSchema,
    *,
    widget_capable: bool = True,
    keyboard_mode: bool = False,
    chosen: str | None = None,
) -> str:
    """Choose the surface to render ``form`` on. Returns ``"widget"`` or ``"ask"``.

    The product-level router (D21). The rich widget is the **default**;
    ``AskUserQuestion`` is the explicit fallback. Latency is not an
    input — the axis is how much of the option space the user can see
    at once, not how many tool calls it costs.

    .. note::
       Authority (architecture review F9, 2026-08-20): in the shipped
       plugin this router is **advisory** — the agent's choice of MCP
       tool is the effective surface decision, made from the skill's
       prose ladder, and the MCP handlers call this only *after the
       fact* (passing ``chosen``) so telemetry records agreement vs
       disagreement. Its return value is binding only for library
       consumers who route their own render calls through it. The
       markdown surface is outside its range entirely (it can return
       only ``"widget"`` / ``"ask"``) — revisit when the markdown
       surface gains an MCP tool.

    Precedence, highest first:

    1. **Capability floor** — a client that cannot render widgets gets
       ``"ask"`` regardless of fidelity loss. A constraint, not a
       preference.
    2. **No portable control** — ``number`` / ``date`` / ``textarea``
       have no ``AskUserQuestion`` equivalent, so the widget is forced.
       This outranks ``keyboard_mode`` so the opt-out can never
       silently drop a field.
    3. **Keyboard mode** — the user's opt-out (D17). Applies only to
       forms ``AskUserQuestion`` can actually express, which by this
       point is all that remain.
    4. **Triviality** — see :func:`is_trivial_form`.
    5. Otherwise the widget, which is the default.

    Args:
        form: The form to route.
        widget_capable: Whether the client can render inline HTML.
        keyboard_mode: Whether the user opted into terse/keyboard mode.
        chosen: The surface the caller actually used, when known. The MCP
            handlers pass this because the tool the agent invoked *is* its
            choice, which lets the telemetry record agreement rather than
            only the recommendation. ``None`` when the caller is asking
            before deciding.

    Returns:
        ``"widget"`` or ``"ask"``.
    """
    surface, reason = _route(form, widget_capable=widget_capable, keyboard_mode=keyboard_mode)
    log_surface_decision(
        surface,
        reason=reason,
        form_id=form.form_id,
        question_count=len(form.questions),
        chosen=chosen,
        agreed=None if chosen is None else chosen == surface,
        inferred_fields=inferred_field_count(form),
        fully_inferred=is_fully_inferred(form),
    )
    return surface


def _route(
    form: FormSchema,
    *,
    widget_capable: bool,
    keyboard_mode: bool,
) -> tuple[str, str]:
    """Pure routing decision + the reason, for :func:`select_form_surface`.

    Split out so the reason is available to telemetry without the
    caller-facing signature carrying it.
    """
    if not widget_capable:
        return "ask", "client_not_widget_capable"
    if any(question.type in _NO_PORTABLE_CONTROL for question in form.questions):
        return "widget", "no_portable_control"
    if keyboard_mode:
        return "ask", "keyboard_mode"
    if is_trivial_form(form):
        return "ask", "trivial_form"
    return "widget", "default"


#: Values read as "on" / "off" for :func:`keyboard_mode_enabled`.
_TRUTHY = frozenset({"1", "true", "yes", "on"})
_FALSEY = frozenset({"0", "false", "no", "off"})

#: Project-local config files the preference persists in. The
#: collision-proof name is the public default (P1 naming ruling,
#: attune-forms-plugin spec D2, 2026-08-12); the legacy attune-ai name
#: stays honored so existing repos keep working byte-identically.
#: Read precedence: new > legacy. Write target: explicit override >
#: whichever file exists (new first) > legacy default (flipping the
#: fresh-write default to the new name is deferred until attune-ai
#: pins its name explicitly — public surfaces pass ``config_name``).
_PROJECT_CONFIG_NEW = "attune-forms.config.json"
_PROJECT_CONFIG_LEGACY = "attune.config.json"

#: The key holding the preference inside :data:`_PROJECT_CONFIG`.
_KEYBOARD_MODE_KEY = "keyboard_mode"


def _project_keyboard_mode(project_root: Path | None = None) -> bool:
    """Read the persisted per-project preference. False on any problem.

    Best-effort: a missing file, unreadable file, malformed JSON, or
    absent key all mean "not opted in" rather than an error. Surface
    routing must never fail because a config file is bad.
    """
    base = Path(project_root) if project_root is not None else Path.cwd()
    path = base / _PROJECT_CONFIG_NEW
    if not path.exists():
        path = base / _PROJECT_CONFIG_LEGACY
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    value = data.get(_KEYBOARD_MODE_KEY)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def keyboard_mode_enabled(project_root: Path | None = None) -> bool:
    """True when the user opted into terse/keyboard mode.

    D17 ratified keyboard mode as an on-demand opt-in available from day
    one — no tenure timer, no per-user tenure state. The chair ruled
    (2026-07-25) that the preference persists **per project**, so it
    lives under ``keyboard_mode`` in the project-local
    ``attune.config.json``.

    ``ATTUNE_FORMS_KEYBOARD_MODE`` (legacy fallback:
    ``ATTUNE_KEYBOARD_MODE``, consulted only when the preferred name is
    unset) remains a session-scoped override in both directions: set it
    truthy to force terse mode for one shell, or falsey to force rich
    forms even where the project opted out. Unset (or unrecognised)
    defers to the project file.

    Args:
        project_root: Directory holding ``attune.config.json``. Defaults
            to the current working directory.

    Returns:
        True if terse/keyboard mode is on.
    """
    for var in ("ATTUNE_FORMS_KEYBOARD_MODE", "ATTUNE_KEYBOARD_MODE"):
        env = os.environ.get(var, "").strip().lower()
        if env in _TRUTHY:
            return True
        if env in _FALSEY:
            return False
    return _project_keyboard_mode(project_root)


def set_keyboard_mode(
    enabled: bool,
    project_root: Path | None = None,
    *,
    config_name: str | None = None,
) -> Path:
    """Persist the keyboard-mode preference for this project.

    Writes ``keyboard_mode`` into the project-local ``attune.config.json``,
    preserving any other keys already in the file. A missing file is
    created; a malformed one raises rather than silently discarding the
    user's other settings.

    Args:
        enabled: The preference to store.
        project_root: Directory holding ``attune.config.json``. Defaults
            to the current working directory.

    Returns:
        The path written.

    Raises:
        ValueError: The existing config file is not valid JSON, or holds
            something other than a JSON object. Overwriting it would lose
            data, so the caller must fix it first.
    """
    base = Path(project_root) if project_root is not None else Path.cwd()
    if config_name is not None:
        path = base / config_name
    elif (base / _PROJECT_CONFIG_NEW).exists():
        path = base / _PROJECT_CONFIG_NEW
    else:
        path = base / _PROJECT_CONFIG_LEGACY

    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise ValueError(f"{path} is not valid JSON — fix it before setting keys") from exc
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} does not hold a JSON object")
        data = loaded

    data[_KEYBOARD_MODE_KEY] = bool(enabled)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def form_response_summary(form: FormSchema, response: FormResponse) -> str:
    """Render an answered form as a compact markdown summary.

    The collapse path (chair-ruled 2026-07-25, from the Antigravity
    seat's context-bloat objection): once a form is submitted, the
    multi-kB rendered HTML has done its job and only the question/answer
    pairs still carry meaning. Callers substitute this summary for the
    rendered form so a long session accumulates a few lines per ask
    instead of a screenful of markup.

    Unanswered questions are omitted — the summary reports what was
    decided, not what was displayed. List answers (multi-select) join
    with commas; booleans render Yes/No.

    Args:
        form: The form that was asked.
        response: The validated response to it.

    Returns:
        A markdown summary. Title line plus one bullet per answer.
    """
    lines = [f"**{form.title}** — answered ({response.response_id})"]
    for question in form.questions:
        if question.id not in response.responses:
            continue
        value = response.responses[question.id]
        if isinstance(value, bool):
            rendered = "Yes" if value else "No"
        elif isinstance(value, list):
            rendered = ", ".join(str(item) for item in value) or "(none)"
        elif isinstance(value, dict):
            # A triage board's / assumption review's mapping answer:
            # per-item rulings, never the raw dict repr (review finding,
            # 2026-08-14); an edit ruling shows its replacement text.
            rendered = (
                "; ".join(
                    f"{k}: edit → {v.get('edit', '')}" if isinstance(v, dict) else f"{k}: {v}"
                    for k, v in value.items()
                )
                or "(none)"
            )
        else:
            rendered = str(value)
        lines.append(f"- {question.text}: **{rendered}**")
    return "\n".join(lines)


def form_to_askuserquestion(form: FormSchema, batch_size: int = 4) -> list[list[dict[str, Any]]]:
    """Render a form to batched ``AskUserQuestion`` payloads.

    Thin reuse of the model's per-question conversion. Each inner list is
    one ``AskUserQuestion`` call (≤ ``batch_size`` questions, the tool's
    limit). A TRIAGE question expands to one single-select payload per
    item (``to_ask_user_formats``), so a board can span calls; the dotted
    ids fold back into the mapping answer in
    :func:`collect_form_response`.

    Args:
        form: The form to render.
        batch_size: Max questions per call (the tool caps at 4).

    Returns:
        A list of batches; each batch a list of question payload dicts.
    """
    payloads = [
        payload for question in form.questions for payload in question.to_ask_user_formats()
    ]
    return [payloads[i : i + batch_size] for i in range(0, len(payloads), batch_size)]


def _validate_multi_select(question: FormQuestion, value: Any) -> str | None:
    """MULTI_SELECT: value must be a list whose entries are all options."""
    if not isinstance(value, list):
        return f"{question.id!r} expects a list (multi-select)"
    bad = [v for v in value if v not in question.options]
    if bad:
        return f"{question.id!r} has out-of-option value(s): {bad}"
    return None


def _validate_membership(question: FormQuestion, value: Any) -> str | None:
    """SINGLE_SELECT / DECISION / PUSHBACK / PROGRESS: value in options.

    PROGRESS: a provided answer is one selected blocked item, validated
    by membership. When nothing is blocked the form is built display-
    only (required=False, empty options) and no answer is collected.
    """
    if value not in question.options:
        return f"{question.id!r} value {value!r} not in options"
    return None


def _validate_triage(question: FormQuestion, value: Any) -> str | None:
    """TRIAGE: value is {item label: disposition} — keys must be item
    labels, values dispositions; a required board needs EVERY item ruled
    (partial rulings are only legal on ``required=False``).
    """
    if not isinstance(value, dict):
        return f"{question.id!r} expects a mapping of item key -> disposition"
    keys = [k for k, _ in expansion_items(question)]
    unknown = [k for k in value if k not in keys]
    if unknown:
        return f"{question.id!r} has unknown item(s): {unknown}"
    vocabulary = question.dispositions or []
    bad = [f"{k}: {v!r}" for k, v in value.items() if v not in vocabulary]
    if bad:
        return f"{question.id!r} has out-of-disposition ruling(s): {bad}"
    if question.required:
        missing = [key for key in keys if key not in value]
        if missing:
            return f"{question.id!r} missing ruling(s) for: {missing}"
    return None


def _validate_ranking(question: FormQuestion, value: Any) -> str | None:
    """RANKING: value is an ordered list of option labels — every entry
    an option, no repeats, exactly ``top_n`` (or all) of them (spec R2).
    Each failure names the offending entries so the re-ask is precise.
    """
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        return f"{question.id!r} expects an ordered list of options (ranking)"
    unknown = [v for v in value if v not in question.options]
    if unknown:
        return f"{question.id!r} has out-of-option entr(y/ies): {unknown}"
    seen: set[str] = set()
    repeats: list[str] = []
    for entry in value:
        if entry in seen:
            repeats.append(entry)
        seen.add(entry)
    if repeats:
        return f"{question.id!r} ranks the same option more than once: {repeats}"
    expected = ranking_slot_count(question)
    if len(value) != expected:
        return f"{question.id!r} must rank exactly {expected} option(s) (got {len(value)})"
    return None


def _validate_assumption_review(question: FormQuestion, value: Any) -> str | None:
    """ASSUMPTION_REVIEW: value is {item key: ruling}, ruling one of
    ``"accept"`` / ``"reject"`` or ``{"edit": "<non-empty text>"}`` (spec
    R2). Keys must be assumption keys; a required review needs EVERY
    assumption ruled (partial rulings only on ``required=False``).
    Every failure names the offending items.
    """
    if not isinstance(value, dict):
        return f"{question.id!r} expects a mapping of assumption key -> ruling"
    keys = [k for k, _ in expansion_items(question)]
    unknown = [k for k in value if k not in keys]
    if unknown:
        return f"{question.id!r} has unknown assumption(s): {unknown}"
    bad: list[str] = []
    for key, ruling in value.items():
        if ruling in ("accept", "reject"):
            continue
        if isinstance(ruling, dict) and set(ruling) == {"edit"}:
            text = ruling["edit"]
            if isinstance(text, str) and text.strip():
                continue
            bad.append(f"{key}: edit needs replacement text")
            continue
        if ruling == "edit":
            bad.append(f'{key}: edit needs replacement text ({{"edit": "<text>"}})')
            continue
        bad.append(f"{key}: {ruling!r}")
    if bad:
        # The vocabulary hint is deliberately NOT single-quoted: the
        # markdown re-ask attributes problems by quoted field ids, and a
        # sibling field named edit / accept / reject must not be re-asked
        # for this board's problem (review finding, 2026-08-15).
        return (
            f"{question.id!r} has invalid ruling(s) — each must be "
            f'accept, reject, or {{"edit": "<text>"}}: {bad}'
        )
    if question.required:
        missing = [key for key in keys if key not in value]
        if missing:
            return f"{question.id!r} missing ruling(s) for: {missing}"
    return None


def _validate_boolean(question: FormQuestion, value: Any) -> str | None:
    """BOOLEAN: value must be exactly one of ``BOOLEAN_OPTIONS``."""
    if value not in BOOLEAN_OPTIONS:
        return f"{question.id!r} boolean value {value!r} must be 'Yes' or 'No'"
    return None


def _validate_number(question: FormQuestion, value: Any) -> str | None:
    """NUMBER: value must be FINITE numeric within [minimum, maximum].

    Non-finite floats defeat bounds checks (NaN compares False against
    everything; ±inf slips one-sided bounds) and ``json.loads`` accepts
    the ``NaN``/``Infinity`` extensions by default, so the guard lives
    here — once, for every surface (ultrareview finding).
    """
    if not _is_number(value):
        return f"{question.id!r} expects a number"
    if isinstance(value, float) and not math.isfinite(value):
        return f"{question.id!r} {value!r} is not a finite number"
    if question.minimum is not None and value < question.minimum:
        return f"{question.id!r} {value} is below minimum {question.minimum}"
    if question.maximum is not None and value > question.maximum:
        return f"{question.id!r} {value} is above maximum {question.maximum}"
    return None


def _validate_date(question: FormQuestion, value: Any) -> str | None:
    """DATE: value must parse as ``_DATE_FORMAT`` (YYYY-MM-DD)."""
    if not isinstance(value, str):
        return f"{question.id!r} expects an ISO date string (YYYY-MM-DD)"
    try:
        datetime.strptime(value, _DATE_FORMAT)
    except ValueError:
        return f"{question.id!r} {value!r} is not a valid YYYY-MM-DD date"
    return None


def _validate_text(question: FormQuestion, value: Any) -> str | None:
    """TEXT_INPUT / TEXTAREA (and the fallback for any other type): a
    string, optionally bounded by ``max_length``.
    """
    if not isinstance(value, str):
        return f"{question.id!r} expects a string"
    if question.max_length is not None and len(value) > question.max_length:
        return f"{question.id!r} exceeds max_length {question.max_length}"
    return None


#: Per-type answer validators; a type not present here (TEXT_INPUT,
#: TEXTAREA) falls back to ``_validate_text``, matching the original's
#: unconditional string-check tail.
_ANSWER_VALIDATORS: dict[QuestionType, Callable[[FormQuestion, Any], str | None]] = {
    QuestionType.MULTI_SELECT: _validate_multi_select,
    QuestionType.SINGLE_SELECT: _validate_membership,
    QuestionType.DECISION: _validate_membership,
    QuestionType.PUSHBACK: _validate_membership,
    QuestionType.PROGRESS: _validate_membership,
    QuestionType.DELIBERATION: _validate_membership,
    QuestionType.TRIAGE: _validate_triage,
    QuestionType.RANKING: _validate_ranking,
    QuestionType.ASSUMPTION_REVIEW: _validate_assumption_review,
    QuestionType.CONFIRM: _validate_membership,
    QuestionType.BOOLEAN: _validate_boolean,
    QuestionType.NUMBER: _validate_number,
    QuestionType.DATE: _validate_date,
}


def _validate_answer(question: FormQuestion, value: Any) -> str | None:
    """Return a problem string for one answer, or None if it is valid."""
    handler = _ANSWER_VALIDATORS.get(question.type, _validate_text)
    return handler(question, value)


def _fold_assumption_answers(
    folded: dict[str, Any], prefix: str
) -> tuple[dict[str, Any], list[str]]:
    """Fold one assumption review's dotted keys (mutating ``folded``).

    ``"<id>.<key>"`` carries the ruling and ``"<id>.<key>.text"`` the
    replacement text (spec R4). Text is kept only when the ruling is
    ``edit`` (``{"edit": text}``); an ``edit`` ruling with no text folds
    to ``{"edit": ""}`` so the validator names it rather than the fold
    guessing. A ruling already shaped as ``{"edit": ...}`` passes through.

    Returns ``(rulings, problems)``. A text lane whose item has NO
    ruling at all — a nonexistent item or a real one the answer never
    ruled — is a named problem: the text was typed input, and dropping
    it silently while naming the equivalent orphan RULING key violated
    the no-silent-drop rule (confirmation pass 1, 2026-08-20). Text
    beside a non-edit ruling stays a documented drop: it is only read
    on ``edit``.
    """
    rulings: dict[str, Any] = {}
    texts: dict[str, Any] = {}
    for key in list(folded):
        if not key.startswith(prefix):
            continue
        item = key[len(prefix) :]
        if item.endswith(ASSUMPTION_TEXT_SUFFIX):
            texts[item[: -len(ASSUMPTION_TEXT_SUFFIX)]] = folded.pop(key)
        else:
            rulings[item] = folded.pop(key)
    problems: list[str] = []
    orphans = sorted(set(texts) - set(rulings))
    if orphans:
        problems.append(
            f"{prefix[:-1]!r} has replacement text for item(s) with no "
            f"ruling: {orphans} — text is only read with an 'edit' ruling"
        )
    out: dict[str, Any] = {}
    for item, ruling in rulings.items():
        if ruling == "edit":
            out[item] = {"edit": texts.get(item, "")}
        elif (
            isinstance(ruling, dict)
            and set(ruling) == {"edit"}
            and not str(ruling.get("edit") or "").strip()
            and item in texts
        ):
            # An edit already shaped but empty (e.g. a typed bare "edit")
            # takes its paired text lane.
            out[item] = {"edit": texts[item]}
        else:
            out[item] = ruling
    return out, problems


def _fold_expanded_answers(
    form: FormSchema, raw_answers: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Fold dotted per-item / per-slot answers back into their canonical shape.

    The flat surfaces carry a TRIAGE answer as one key per item
    (``"<id>.<item key>"``, everywhere) and a RANKING answer as one key
    per rank slot (``"<id>.<k>"``, k 1-based — AskUserQuestion and
    markdown shorthand only; the MCP elicitation schema carries a
    ranking as ONE bounded array property, see ``_EXPANDING_TYPES``).
    This pre-pass rebuilds the canonical ``{key: disposition}`` mapping /
    ordered list so every surface funnels into the same validator. An
    answer already present under the question id makes any dotted
    sibling a named problem — the old canonical-wins rule silently
    discarded a contradicting dotted value, the same silent-drop class
    the slot-collision rule below names (confirmation-pass-1 finding,
    chair ruling 2026-08-20). The markdown surface merges its dotted
    rows into the canonical shape before handing off, so a mixed shape
    here means a confused caller, not a typed reply. The input dict is
    never mutated.

    Ranking slots fold in slot order. EVERY decimal slot suffix folds —
    including ``0`` and suffixes past the last slot — so an over-long
    ranking is named by the validator's length check exactly as the list
    shape is, never accepted by silently dropping the extra ranks
    (review finding, 2026-08-16). Gaps are simply absent, so the
    validator names the wrong length there too. A NON-decimal suffix
    (``"prio.²"``) is not a slot key at all: it stays in place and is
    ignored — it lives inside the question's declared dotted namespace,
    so the unknown-key check exempts it; the markdown surface, which is
    where a human types one, names it as an unknown rank slot at parse
    time.

    Returns ``(folded, problems)``. Fold-time problems are the mixed
    canonical/dotted shape above and two keys claiming the same rank
    slot (``"r.01"`` and ``"r.1"`` both fold to slot 1): the same
    silent-drop class as the over-long ranking above, so it is named
    instead of letting an arbitrary winner validate clean (pilot review
    finding, 2026-08-19).
    """
    expanding = [q for q in form.questions if q.type in _EXPANDING_TYPES]
    if not expanding:
        return raw_answers, []
    problems: list[str] = []
    folded = dict(raw_answers)
    for question in expanding:
        prefix = f"{question.id}."
        if question.id in folded:
            dotted = sorted(key for key in folded if key.startswith(prefix))
            if dotted:
                problems.append(
                    f"{question.id!r} is supplied both canonically and as "
                    f"dotted keys ({', '.join(map(repr, dotted))}); "
                    "supply one shape"
                )
            continue
        if question.type is QuestionType.TRIAGE:
            picks = {
                key[len(prefix) :]: folded.pop(key)
                for key in list(folded)
                if key.startswith(prefix)
            }
            if picks:
                folded[question.id] = picks
            continue
        if question.type is QuestionType.ASSUMPTION_REVIEW:
            folded_rulings, fold_problems = _fold_assumption_answers(folded, prefix)
            problems.extend(fold_problems)
            if folded_rulings:
                folded[question.id] = folded_rulings
            continue
        slots: dict[int, Any] = {}
        slot_sources: dict[int, str] = {}
        for key in list(folded):
            if not key.startswith(prefix):
                continue
            slot = decimal_key_number(key[len(prefix) :])
            if slot is None:
                continue
            if slot in slots:
                problems.append(
                    f"{question.id!r} rank slot {slot} is supplied more than "
                    f"once ({slot_sources[slot]!r} and {key!r})"
                )
                folded.pop(key)
                continue
            slot_sources[slot] = key
            slots[slot] = folded.pop(key)
        if slots:
            folded[question.id] = [slots[k] for k in sorted(slots)]
    return folded, problems


def collect_form_response(
    form: FormSchema,
    raw_answers: dict[str, Any],
    template_id: str = "",
) -> FormResponse:
    """Validate raw answers and map them into a :class:`FormResponse`.

    Implements R4 — no silent acceptance of malformed input. A missing
    required field with no default, or a value outside a select's
    options, raises :class:`FormValidationError` naming every problem so
    the caller can re-ask just those fields. Missing optional fields fall
    back to the question's ``default`` (omitted if none); an injected
    default passes the same per-type validator an answer would, so a
    directly-built form (bypassing ``form_from_dict``'s definition-time
    check) still cannot launder an invalid default into a validated
    response. A provided answer that is EMPTY (``""``, ``[]``, ``{}``)
    takes the same default path as an omitted key: empty is the
    accept-the-default gesture (enter through a prompt, an untouched
    widget), and this side of the wire cannot tell a deliberately
    cleared prefill from an untouched one — so a surface that needs a
    clearable field must not prefill it via ``default`` (chair ruling,
    2026-08-20). An answer key that matches no question id and no expanding
    question's dotted namespace (``"<id>.<key>"``) is named as unknown —
    a typo'd key against an optional-with-default field would otherwise
    silently collect the default (pilot review finding, 2026-08-19).

    Args:
        form: The form the answers are for.
        raw_answers: ``{question_id: value}`` as returned by the agent.
        template_id: Identifier stored on the response.

    Returns:
        A validated :class:`FormResponse`.

    Raises:
        FormValidationError: If any answer is missing-required or invalid.
    """
    responses: dict[str, Any] = {}
    raw_answers, problems = _fold_expanded_answers(form, raw_answers)

    known_ids = {question.id for question in form.questions}
    dotted_prefixes = tuple(
        f"{question.id}." for question in form.questions if question.type in _EXPANDING_TYPES
    )
    for key in raw_answers:
        if key not in known_ids and not key.startswith(dotted_prefixes):
            problems.append(f"unknown answer key {key!r}")

    for question in form.questions:
        # The D2 constructs forbid a `default` outright. `form_from_dict`
        # rejects it definition-side, but a `FormQuestion` built directly
        # (dataclass constructor) bypasses that check — so re-enforce here
        # on the inject path. Without this, an UNANSWERED confirm gate
        # (or ranking / assumption_review) carrying a default would be
        # collected as approved/ordered/ruled with no user act, defeating
        # the two-way gate (checkpoint-2 promoted item, 2026-08-20).
        if question.default is not None and question.type in _NO_DEFAULT_REASON:
            problems.append(
                f"'default' is not permitted on {question.type.value} "
                f"for {question.id!r} ({_NO_DEFAULT_REASON[question.type]})"
            )
            continue

        provided = question.id in raw_answers
        value = raw_answers.get(question.id)

        if not provided or value is None or value == "" or value == [] or value == {}:
            if question.required and question.default is None:
                problems.append(f"{question.id!r} is required")
            elif question.default is not None:
                default_problem = _validate_answer(question, question.default)
                if default_problem:
                    problems.append(f"invalid 'default' for {question.id!r}: {default_problem}")
                else:
                    responses[question.id] = question.default
            continue

        problem = _validate_answer(question, value)
        if problem:
            problems.append(problem)
        else:
            responses[question.id] = value

    if problems:
        raise FormValidationError(problems)

    return FormResponse(template_id=template_id, responses=responses)
