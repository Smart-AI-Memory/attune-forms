"""Canonical package-local fixtures for the renderer registry (AF-1).

Every registry record names one fixture here. The fixtures ship in the
wheel — test modules are not the fixture distribution boundary — so a
clean-wheel probe can import and execute each one without the test
suite present.

Normalization is closed and rationale-bearing: ``NORMALIZATION_RULES``
lists every nonsemantic volatile path a projection may contain — today
exactly one, the widget's per-render telemetry token. A renderer that
starts emitting another random token must add a rule here WITH its
rationale, which the fixture digest then binds.
Revision, event sequence, contract hash and every subject/schema/action
id are semantic and may never be normalized away.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from attune_forms.bridge import form_from_dict
from attune_forms.headless import workspace_to_headless
from attune_forms.models import FormSchema
from attune_forms.widget import WIDGET_RESPONSE_MARKER
from attune_forms.workspace import (
    WorkspaceAction,
    WorkspaceActionBinding,
    WorkspaceActionIntent,
    WorkspaceBlock,
    WorkspaceBlockKind,
    WorkspaceItem,
    WorkspaceSection,
    WorkspaceView,
    WorkspaceViewId,
)

CANONICAL_INSTANCE_ID = "canonical"


@dataclass(frozen=True)
class NormalizationRule:
    """One closed volatile-path substitution applied to text projections."""

    name: str
    pattern: str
    replacement: str
    rationale: str


#: Closed. One rule: the widget renderers mint a fresh telemetry join
#: token per render (``instance_id`` in the post-back script) so the
#: ``form_rendered`` → ``form_submitted`` pair can be joined; it carries
#: no projection semantics. Nothing else in these projections is
#: volatile under ``CANONICAL_INSTANCE_ID``.
NORMALIZATION_RULES: tuple[NormalizationRule, ...] = (
    NormalizationRule(
        name="widget-telemetry-instance",
        pattern=r'instance_id: "[0-9a-f]{32}"',
        replacement='instance_id: "<telemetry-instance>"',
        rationale=(
            "per-render telemetry join token minted by form_to_widget_html / "
            "workspace_to_widget_html; identifies the render, not the projection"
        ),
    ),
)


def normalize(text: str) -> str:
    """Apply every closed normalization rule to a text projection."""
    for rule in NORMALIZATION_RULES:
        text = re.sub(rule.pattern, rule.replacement, text)
    return text


CANONICAL_FORM_DEFINITION: dict[str, Any] = {
    "title": "Canonical form",
    "description": "Registry fixture: one construct, one select, one free text.",
    "form_id": "canonical-form",
    "fields": [
        {
            "id": "approach",
            "type": "decision",
            "text": "Which approach?",
            "recommended": "Verify first",
            "rationale": "The receipt beats the promise.",
            "options": ["Verify first", "Build first"],
            "option_notes": {"Verify first": "cheap", "Build first": "fast"},
        },
        {
            "id": "scope",
            "type": "single_select",
            "text": "Which scope?",
            "options": ["file", "package"],
        },
        {
            "id": "notes",
            "type": "text_input",
            "text": "Anything else?",
            "required": False,
        },
    ],
}

CANONICAL_FORM_ANSWERS: dict[str, Any] = {
    "approach": "Verify first",
    "scope": "package",
    "notes": "none",
}


def canonical_form() -> FormSchema:
    """The standalone-form record's fixture."""
    return form_from_dict(CANONICAL_FORM_DEFINITION)


def canonical_form_answers() -> dict[str, Any]:
    """A raw answer set every form renderer's collector accepts."""
    return dict(CANONICAL_FORM_ANSWERS)


def canonical_workspace_view() -> WorkspaceView:
    """The workspace record's fixture: a preview with a bound explicit action."""
    ruling = form_from_dict(
        {
            "title": "ruling",
            "fields": [
                {
                    "id": "ruling",
                    "type": "single_select",
                    "text": "Ruling?",
                    "options": ["apply", "defer"],
                }
            ],
        }
    ).questions[0]
    return WorkspaceView(
        id=WorkspaceViewId.PREVIEW,
        title="Canonical workspace",
        summary="Registry fixture: two sections, two actions.",
        sections=(
            WorkspaceSection(
                heading="Evidence",
                blocks=(
                    WorkspaceBlock(
                        kind=WorkspaceBlockKind.KEY_VALUE,
                        items=(WorkspaceItem(label="files", value="2", status="ok"),),
                    ),
                ),
            ),
            WorkspaceSection(
                blocks=(
                    WorkspaceBlock(
                        kind=WorkspaceBlockKind.CODE, body="print(1)", language="python"
                    ),
                ),
            ),
        ),
        actions=(
            WorkspaceAction(
                id="apply",
                label="Apply",
                intent=WorkspaceActionIntent.PRIMARY,
                consequence="Writes two files.",
                requires_explicit_choice=True,
                response_fields=(ruling,),
            ),
            WorkspaceAction(id="dismiss", label="Dismiss"),
        ),
    )


def canonical_binding() -> WorkspaceActionBinding:
    """A deterministic host binding for the canonical view."""
    return WorkspaceActionBinding(
        workspace_id="canonical-workspace",
        revision=3,
        action_nonce="canonical-nonce-0123456789abcdef",
        contract_hash=hashlib.sha256(b"canonical-contract").hexdigest(),
    )


def canonical_workspace_response(
    view: WorkspaceView,
    action_id: str,
    binding: WorkspaceActionBinding | None = None,
    responses: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the response-shaped mapping a headless host posts back.

    Constructed from the headless projection's own ``response_contract``
    so the fixture proves the contract is sufficient to act on.
    """
    contract = workspace_to_headless(view, binding)["response_contract"]
    action = contract["actions"][action_id]
    payload: dict[str, Any] = {
        WIDGET_RESPONSE_MARKER: True,
        "title": contract["title"],
        "view": contract["view"],
        "action": action_id,
        "confirmed": action["confirmed"],
    }
    if action["responses"] or responses:
        # An action with no declared response fields posts no ``responses``
        # key, exactly as the widget does; the collector rejects one.
        payload["responses"] = dict(responses or {})
    if binding is not None:
        payload.update(binding.to_payload())
    return payload


def canonical_json(value: Any) -> str:
    """Deterministic JSON used by every digest in the registry."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(value: Any) -> str:
    """SHA-256 of :func:`canonical_json`."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def fixture_digest() -> str:
    """Digest of every canonical input the registry's fixtures execute."""
    return digest(
        {
            "form": CANONICAL_FORM_DEFINITION,
            "answers": CANONICAL_FORM_ANSWERS,
            "workspace": workspace_to_headless(canonical_workspace_view()),
            "binding": canonical_binding().to_payload(),
            "normalization": [rule.__dict__ for rule in NORMALIZATION_RULES],
        }
    )


__all__ = [
    "CANONICAL_FORM_ANSWERS",
    "CANONICAL_FORM_DEFINITION",
    "CANONICAL_INSTANCE_ID",
    "NORMALIZATION_RULES",
    "NormalizationRule",
    "canonical_binding",
    "canonical_form",
    "canonical_form_answers",
    "canonical_json",
    "canonical_workspace_response",
    "canonical_workspace_view",
    "digest",
    "fixture_digest",
    "normalize",
]
