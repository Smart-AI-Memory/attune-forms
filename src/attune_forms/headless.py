"""Production HEADLESS projection of a workspace view (host-surface-parity AF-1).

``workspace_to_headless`` is the third leg of the workspace renderer
family beside ``workspace_to_widget_html`` (RICH) and
``workspace_to_markdown`` (PORTABLE). It returns one deterministic,
JSON-safe mapping that preserves the complete view, the full form schema
when the view carries one, the optional state binding, and the response
contract a host must post back through ``collect_workspace_action``.

It deliberately does NOT collapse to action ids: the test-only
conformance stub that lists action ids is a comparison aid, not a twin
a headless host could act on.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.models import FormQuestion, FormSchema
from attune_forms.widget import WIDGET_RESPONSE_MARKER
from attune_forms.workspace import (
    WorkspaceAction,
    WorkspaceActionBinding,
    WorkspaceView,
)

#: Bumped whenever the mapping's shape changes; consumers pin it.
HEADLESS_SCHEMA_VERSION = "attune-forms.workspace-headless/1"

#: Every key ``collect_workspace_action`` accepts, in a stable order.
RESPONSE_CONTRACT_KEYS: tuple[str, ...] = (
    WIDGET_RESPONSE_MARKER,
    "title",
    "view",
    "action",
    "confirmed",
    "responses",
    "workspace_id",
    "revision",
    "action_nonce",
    "contract_hash",
    "instance_id",
)

BINDING_KEYS: tuple[str, ...] = ("workspace_id", "revision", "action_nonce", "contract_hash")


def _json_safe(value: Any) -> Any:
    """Project dataclass/enum/frozen-container values onto plain JSON types."""
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _json_safe(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _question_payload(question: FormQuestion) -> dict[str, Any]:
    payload = _json_safe(question)
    payload["type"] = question.type.value
    return payload


def _form_payload(form: FormSchema) -> dict[str, Any]:
    return {
        "title": form.title,
        "description": form.description,
        "form_id": form.form_id,
        "questions": [_question_payload(q) for q in form.questions],
        "elicitation_schema": form_to_elicitation_schema(form),
    }


def _action_payload(action: WorkspaceAction) -> dict[str, Any]:
    return {
        "id": action.id,
        "label": action.label,
        "intent": action.intent.value,
        "consequence": action.consequence,
        "requires_explicit_choice": action.requires_explicit_choice,
        "response_fields": [_question_payload(q) for q in action.response_fields],
    }


def _response_contract(
    view: WorkspaceView, binding: WorkspaceActionBinding | None
) -> dict[str, Any]:
    return {
        "marker": WIDGET_RESPONSE_MARKER,
        "keys": list(RESPONSE_CONTRACT_KEYS),
        "title": view.title,
        "view": view.id.value,
        "actions": {
            action.id: {
                "confirmed": action.requires_explicit_choice,
                "responses": [q.id for q in action.response_fields],
            }
            for action in view.actions
        },
        "binding_fields": list(BINDING_KEYS) if binding is not None else [],
        "collector": "attune_forms.workspace.collect_workspace_action",
    }


def workspace_to_headless(
    view: WorkspaceView, binding: WorkspaceActionBinding | None = None
) -> dict[str, Any]:
    """Serialize a workspace view for a host with no rendering surface.

    Args:
        view: The rendered view, exactly as RICH/PORTABLE would show it.
        binding: The host's state binding for this revision; forbidden on
            form views, mirroring the widget and Markdown renderers.

    Returns:
        A JSON-safe mapping: ``schema_version``, the complete ``view``
        (sections, actions with their response fields, the full form
        schema when present), the ``binding`` payload or ``None``, and
        the ``response_contract`` the host posts back.

    Raises:
        ValueError: A binding was supplied for a form view.
    """
    if view.form is not None and binding is not None:
        raise ValueError("workspace action binding is not valid on a form view")
    return {
        "schema_version": HEADLESS_SCHEMA_VERSION,
        "view": {
            "id": view.id.value,
            "title": view.title,
            "summary": view.summary,
            "sections": _json_safe(view.sections),
            "actions": [_action_payload(a) for a in view.actions],
            "form": _form_payload(view.form) if view.form is not None else None,
        },
        "binding": binding.to_payload() if binding is not None else None,
        "response_contract": _response_contract(view, binding),
    }


__all__ = [
    "BINDING_KEYS",
    "HEADLESS_SCHEMA_VERSION",
    "RESPONSE_CONTRACT_KEYS",
    "workspace_to_headless",
]
