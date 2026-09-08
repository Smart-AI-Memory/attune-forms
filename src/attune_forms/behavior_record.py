"""A reviewable record of what the stable surface actually does.

``stability.py`` says which names are promised. This says what they
*do* — so a behavior change to promised surface cannot land silently.

attune-forms ships default-on and unpinned: hosts launch it through
``uvx --from 'attune-forms[mcp]'`` with no version constraint, and the
package has no feature flags. That is deliberate, and it is worth
keeping — install-to-working in one step. But it means a behavior change
reaches every consumer at once, and a plugin user cannot pin their way
out of it. The protection therefore belongs on the maintainer's side of
the release, not the user's: this record fails CI before a change ships
rather than asking users to notice afterwards.

**Digest the contract, not the paint.** A golden test over rendered
bytes breaks on every CSS tweak, gets muted, and ends up worse than
nothing — and ``docs/stability.md`` already declines to guarantee HTML
and CSS bytes. So the record captures the semantic decisions a consumer
depends on (which fields exist, what validates, what each surface binds)
and deliberately excludes presentation, problem prose, timestamps and
identifiers. :func:`test_presentation_does_not_move_the_record` in the
test module proves that exclusion holds rather than asserting it.

The record is stored as JSON, not just hashed, because the point is
review: a routing or validation change should appear as a readable line
in a pull request diff. :func:`behavior_digest` is the receipt for
release notes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from attune_forms.bridge import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_response_summary,
    inferred_field_count,
    is_fully_inferred,
    select_form_surface,
)
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.markdown_ingestion import markdown_to_answers
from attune_forms.markdown_surface import form_to_markdown
from attune_forms.models import FormSchema
from attune_forms.reference_form import EXAMPLE_ANSWERS, REFERENCE_FORM
from attune_forms.widget import form_to_widget_html

#: Widget attributes that carry meaning rather than appearance. A
#: consumer or host reads these; nobody reads a class name.
_SEMANTIC_ATTRS = (
    "data-collect",
    "data-fid",
    "data-ftype",
    "data-opt",
    "data-item",
    "data-rank-n",
    "data-required",
    "data-assume",
)


def _reference() -> FormSchema:
    return form_from_dict(REFERENCE_FORM)


def _parse_record(form: FormSchema) -> list[dict[str, Any]]:
    """What the parser made of each field."""
    return [
        {
            "id": question.id,
            "type": question.type.value,
            "required": question.required,
            "options": list(question.options or []),
            "default": question.default,
            "recommended": question.recommended,
            "option_notes": dict(sorted((question.option_notes or {}).items())),
        }
        for question in form.questions
    ]


def _validation_record(form: FormSchema) -> dict[str, Any]:
    """What validates, and which field is blamed when it does not.

    Records attribution, never problem prose: ``docs/stability.md``
    declines to guarantee the wording, and a consumer needing structure
    reads ``FormValidationError.fields``.
    """

    def attempt(answers: dict[str, Any]) -> dict[str, Any]:
        try:
            response = collect_form_response(form, dict(answers))
        except FormValidationError as error:
            return {
                "accepted": False,
                "fields": list(error.fields),
                "fully_attributed": error.fully_attributed,
                "problem_count": len(error.problems),
            }
        return {"accepted": True, "responses": response.responses}

    cases: dict[str, Any] = {
        "complete": attempt(EXAMPLE_ANSWERS),
        "empty": attempt({}),
        "unknown_key": attempt({**EXAMPLE_ANSWERS, "no_such_field": "x"}),
    }
    # One corruption per field: does the validator still blame the right
    # question when a single answer goes bad?
    for question in form.questions:
        if question.id not in EXAMPLE_ANSWERS:
            continue
        corrupted = dict(EXAMPLE_ANSWERS)
        corrupted[question.id] = "not-a-valid-answer"
        cases[f"corrupt.{question.id}"] = attempt(corrupted)
    return cases


def _widget_record(form: FormSchema) -> dict[str, Any]:
    """The widget's bindings, with every appearance-bearing byte dropped."""
    html = form_to_widget_html(form, "record")
    found: dict[str, list[str]] = {}
    for attr in _SEMANTIC_ATTRS:
        found[attr] = sorted(set(re.findall(rf'{attr}="([^"]*)"', html)))
    return found


def _markdown_record(form: FormSchema) -> dict[str, Any]:
    """The portable surface's field order and its own round trip."""
    markdown = form_to_markdown(form)
    ids = [q.id for q in form.questions]
    order = [fid for fid in ids if re.search(rf"\b{re.escape(fid)}\b", markdown)]
    reparsed = markdown_to_answers(form, markdown)
    parsed_answers = reparsed[0] if isinstance(reparsed, tuple) else reparsed
    return {
        "field_order": order,
        "round_trip_keys": sorted(parsed_answers) if isinstance(parsed_answers, dict) else None,
    }


def _routing_record(form: FormSchema) -> dict[str, Any]:
    """The router's decisions.

    ``select_form_surface`` is PROVISIONAL — this is recorded so a flip
    is visible in a diff, not because the value is promised. Its default
    changed in 0.15.0 with nothing to catch it.
    """

    def only(field_id: str) -> FormSchema:
        field = next(f for f in REFERENCE_FORM["fields"] if f["id"] == field_id)
        return form_from_dict({"title": "t", "description": "d", "fields": [field]})

    # 'priority' is a single_select the host-question profile admits, so
    # it is the case that exercises the 0.15.0 host-native default. A
    # flip back to the widget shows up here and nowhere else.
    admissible = only("priority")
    return {
        "reference_widget_capable": select_form_surface(form, widget_capable=True),
        "reference_not_widget_capable": select_form_surface(form, widget_capable=False),
        "reference_keyboard_mode": select_form_surface(form, keyboard_mode=True),
        "host_admissible_single_select": select_form_surface(admissible),
        "host_admissible_keyboard_mode": select_form_surface(admissible, keyboard_mode=True),
        "no_portable_control": select_form_surface(only("estimated_days")),
    }


def _summary_record(form: FormSchema) -> dict[str, Any]:
    """The summary's shape, with its prose and its response id excluded.

    ``form_response_summary`` renders prose, and prose is not guaranteed.
    What is guaranteed is that it accounts for every answer: one line per
    answered field, under a heading. The response id carries a uuid and a
    timestamp, so only the line count survives.
    """
    try:
        response = collect_form_response(form, dict(EXAMPLE_ANSWERS))
    except FormValidationError as error:
        # The corpus and the answer vector are shipped together, so this
        # means one of them moved. Record that rather than aborting the
        # whole record — a caller comparing records should see which
        # section changed, not a traceback.
        return {"summarized": False, "fields": list(error.fields)}
    lines = form_response_summary(form, response).splitlines()
    return {
        "summarized": True,
        "line_count": len(lines),
        "answer_lines": sum(1 for line in lines if line.startswith("- ")),
        "answered_fields": len(response.responses),
    }


def behavior_record() -> dict[str, Any]:
    """The full semantic record of the stable surface, JSON-safe.

    ``stable`` is the promised behavior; ``provisional`` is recorded for
    visibility only and carries no guarantee.
    """
    form = _reference()
    return {
        "stable": {
            "parse": _parse_record(form),
            "validate": _validation_record(form),
            "headless_schema": form_to_elicitation_schema(form),
            "widget_bindings": _widget_record(form),
            "markdown": _markdown_record(form),
            "inference": {
                "inferred_field_count": inferred_field_count(form),
                "is_fully_inferred": is_fully_inferred(form),
            },
            "summary": _summary_record(form),
        },
        "provisional": {
            "routing": _routing_record(form),
        },
    }


def canonical_record_json(record: dict[str, Any] | None = None) -> str:
    """The record as deterministic JSON — the digest input and the stored file."""
    return json.dumps(
        record if record is not None else behavior_record(),
        indent=1,
        sort_keys=True,
        ensure_ascii=True,
    )


def behavior_digest(record: dict[str, Any] | None = None) -> str:
    """SHA-256 over the STABLE half of the record only.

    Provisional behavior is expected to move; folding it into the digest
    would make the receipt meaningless.
    """
    source = record if record is not None else behavior_record()
    payload = json.dumps(source["stable"], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "behavior_digest",
    "behavior_record",
    "canonical_record_json",
]
