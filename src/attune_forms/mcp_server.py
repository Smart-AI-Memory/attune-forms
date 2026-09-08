"""Standalone MCP server for the attune-forms substrate (spec Phase 2).

Mirrors attune-ai\'s elicitation tools — same names, same schemas,
same result shapes (chair-ruled D3: identical surface makes the later
convergence a pure swap and lets docs/skills transfer verbatim):

- ``elicitation_render_form``     — form dict -> AskUserQuestion batches
- ``elicitation_render_widget``   — form dict -> self-contained HTML
- ``elicitation_collect_response``— form + answers -> validated response
- ``elicitation_ask``             — native MCP elicitation round-trip
- ``elicitation_render_workspace``— workspace dict -> widget + markdown
- ``elicitation_collect_workspace_action`` — bound action validation

Every form-taking tool accepts the form EITHER as ``form`` (a declarative
dict composed by the agent) OR as ``template`` + ``slots`` (the fused
template path, spec R5.2): the server loads the stored template, casts
the slots, validates and renders in ONE call, so neither the form schema
nor the HTML transits the agent's context. Exactly one of the two must be
given; ``slots`` is only meaningful with ``template``.
Launch: ``attune-forms-mcp`` (console script) or
``uvx --from 'attune-forms[mcp]' attune-forms-mcp`` — the exact command
a plugin ``.mcp.json`` carries.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server

from attune_forms._version import __version__
from attune_forms.bridge import (
    FormValidationError,
    _form_to_askuserquestion,
    collect_form_response,
    form_from_dict,
    form_response_summary,  # noqa: F401  (re-exported convenience)
    keyboard_mode_enabled,
    select_form_surface,
)
from attune_forms.conformance import installed_profile
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.form_events import log_submission, maybe_keyboard_hint
from attune_forms.host_question import (
    form_to_host_question,
    host_question_admissibility,
)
from attune_forms.host_question_adapter import host_question_turn
from attune_forms.mcp_app import (
    MCP_APP_MIME_TYPE,
    MCP_APPS_EXTENSION,
    client_supports_mcp_apps,
    mcp_app_resource,
    mcp_app_result,
    mcp_app_tool_meta,
)
from attune_forms.renderer_registry import RENDERER_REGISTRY, iter_targets
from attune_forms.template_store import form_from_template
from attune_forms.widget import form_to_widget_html
from attune_forms.workspace import (
    WorkspaceActionBinding,
    WorkspaceValidationError,
    collect_workspace_action,
    workspace_from_dict,
    workspace_to_markdown,
    workspace_to_widget_html,
)

logger = logging.getLogger(__name__)

# The version is passed explicitly: with version=None the SDK
# reports ITS OWN version under this server's name, so a host
# asking which attune-forms it is talking to got "1.30.0".
_server: Server = Server("attune-forms", version=__version__)


def _field_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Stable field id"},
            "text": {"type": "string", "description": "The question text"},
            "type": {
                "type": "string",
                "enum": [
                    "text_input",
                    "textarea",
                    "single_select",
                    "multi_select",
                    "boolean",
                    "number",
                    "date",
                    "decision",
                    "pushback",
                    "progress",
                    "deliberation",
                    "triage",
                    "confirm",
                    "ranking",
                    "assumption_review",
                ],
                "description": (
                    "Control type. Core: text_input/single_select/"
                    "multi_select/boolean. Rich: textarea, number (min/max), "
                    "date (YYYY-MM-DD). Constructs: decision (recommended "
                    "single-select with rationale + per-option tradeoffs), "
                    "pushback (decision framed as dissent), progress "
                    "(done/in_flight/blocked report with a blocked-item "
                    "picker), deliberation (multi-voice endorsements per "
                    "option, chair picks one), triage (per-item rulings "
                    "over a reviewed list; answer = {item id: disposition}), "
                    "confirm (consequences preview + two-way approve/abort "
                    "gate; no default/recommended permitted), ranking (order "
                    "the options, optionally only the top_n; answer = ordered "
                    "list; a suggested order is a visible proposal, no default "
                    "permitted), assumption_review (the agent's inferred "
                    "assumptions, each ruled accept / edit / reject — fixed "
                    "vocabulary; answer = {item id: 'accept' | 'reject' | "
                    "{edit: text}}; suggested may pre-mark accept only)."
                ),
            },
            "options": {"type": "array", "items": {"type": "string"}},
            "default": {
                "type": ["string", "number", "boolean", "array", "object"],
                "description": (
                    "Pre-supplied answer; must be answer-shaped for the "
                    "field type (multi_select: LIST of options; number: "
                    "numeric; boolean: 'Yes'/'No'; triage: {item id: "
                    "disposition} OBJECT) — it is validated like an "
                    "answer at definition time"
                ),
            },
            "inferred_from": {
                "type": "string",
                "description": (
                    "Provenance note for a guessed default (requires "
                    "'default'); renders as a '(guessed)' badge"
                ),
            },
            "help_text": {"type": "string"},
            "required": {"type": "boolean", "description": "Defaults to true"},
            "minimum": {"type": "number"},
            "maximum": {"type": "number"},
            "max_length": {"type": "integer"},
            "path_kind": {
                "type": "string",
                "enum": ["file", "directory", "either"],
                "description": "Enable a project-relative path picker for this text field",
            },
            "path_options": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Host-validated project-relative paths offered by the picker",
            },
            "rationale": {"type": "string"},
            "recommended": {"type": "string"},
            "option_notes": {"type": "object"},
            "user_position": {"type": "string"},
            "progress_items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "progress: [{label, status, detail?}, ...]",
            },
            "progress_style": {"type": "string", "enum": ["report"]},
            "endorsements": {
                "type": "object",
                "description": "deliberation: {option: [voice, ...]}",
            },
            "triage_items": {
                "type": "array",
                "items": {"type": "object"},
                "description": "triage: [{label, id?, detail?, tag?}, ...]",
            },
            "dispositions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "triage: the shared per-item ruling vocabulary",
            },
            "suggested": {
                "type": ["object", "array"],
                "description": (
                    "triage: {item id: proposed disposition}; ranking: the "
                    "proposed order as [option, ...]; assumption_review: "
                    "{item id: 'accept'} only (rendered as a proposal, never "
                    "the answer)"
                ),
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "object"},
                "description": (
                    "assumption_review: [{label, id?, detail?, source?}, ...] — "
                    "the inferred assumptions; source = where it was inferred from"
                ),
            },
            "top_n": {
                "type": "integer",
                "description": "ranking: rank only the top N (1..len(options))",
            },
            "consequences": {
                "type": "array",
                "items": {"type": "object"},
                "description": "confirm: [{label, severity?, detail?}, ...]",
            },
            "list_style": {"type": "string", "enum": ["ordered", "unordered"]},
        },
        "required": ["id", "text", "type"],
        # Mirrors form_from_dict's strict definition contract: an
        # unknown field key is a typo ("maximun") that would silently
        # drop the constraint it meant to declare, so the SDK gate
        # rejects it rather than waving it through to a lax parse.
        "additionalProperties": False,
    }


def _form_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Declarative form artifact (data, not code).",
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "fields": {"type": "array", "items": _field_schema()},
        },
        "required": ["title", "fields"],
        "additionalProperties": False,
    }


def _template_props() -> dict[str, Any]:
    """The fused template-path arguments every form-taking tool accepts (R5.2).

    Advertised beside ``form``; the handler enforces "exactly one of
    ``form`` / ``template``" and lists every problem, so the schema does
    not need a ``oneOf`` (which not every MCP host renders).
    """
    return {
        "template": {
            "type": "string",
            "description": (
                "Name of a stored form template (e.g. 'session-contract'). "
                "The server loads, casts the slots, validates and renders it "
                "in this one call — pass this INSTEAD of 'form'. An unknown "
                "name returns problems listing the available templates."
            ),
        },
        "slots": {
            "type": "object",
            "description": (
                "Slot values for 'template' — one string per declared "
                "{slot_name} placeholder; missing or extra names are problems."
            ),
            "additionalProperties": {"type": "string"},
        },
    }


def _workspace_schema() -> dict[str, Any]:
    """Closed serializable workspace grammar mirrored by workspace_from_dict."""
    item = {
        "type": "object",
        "properties": {
            "label": {"type": "string"},
            "value": {"type": "string"},
            "detail": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["label"],
        "additionalProperties": False,
    }
    block = {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": [
                    "key_value",
                    "code",
                    "timeline",
                    "change_summary",
                    "evidence",
                    "disclosure",
                    "action_list",
                ],
            },
            "title": {"type": "string"},
            "body": {"type": "string"},
            "items": {"type": "array", "items": item},
            "language": {"type": "string"},
        },
        "required": ["kind"],
        "additionalProperties": False,
    }
    section = {
        "type": "object",
        "properties": {
            "heading": {"type": "string"},
            "tone": {
                "type": "string",
                "enum": [
                    "neutral",
                    "action",
                    "recommendation",
                    "success",
                    "warning",
                    "danger",
                ],
            },
            "blocks": {"type": "array", "items": block},
        },
        "required": ["blocks"],
        "additionalProperties": False,
    }
    action = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"},
            "label": {"type": "string"},
            "intent": {
                "type": "string",
                "enum": ["primary", "secondary", "danger"],
            },
            "consequence": {"type": "string"},
            "requires_explicit_choice": {"type": "boolean"},
            "response_fields": {"type": "array", "items": _field_schema()},
        },
        "required": ["id", "label"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "description": "Validated command-workspace view document.",
        "properties": {
            "id": {
                "type": "string",
                "enum": ["intake", "preview", "execution", "receipt"],
            },
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "sections": {"type": "array", "items": section},
            "actions": {"type": "array", "items": action},
            "form": _form_schema(),
        },
        "required": ["id", "title"],
        "additionalProperties": False,
    }


def _workspace_binding_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "workspace_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
            },
            "revision": {"type": "integer", "minimum": 0},
            "action_nonce": {
                "type": "string",
                "pattern": "^[A-Za-z0-9_-]{16,128}$",
            },
            "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        "required": ["workspace_id", "revision", "action_nonce", "contract_hash"],
        "additionalProperties": False,
    }


def _workspace_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "__elicitation_response__": {"type": "boolean", "const": True},
            "title": {"type": "string"},
            "workspace_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
            },
            "revision": {"type": "integer", "minimum": 0},
            "view": {
                "type": "string",
                "enum": ["intake", "preview", "execution", "receipt"],
            },
            "action": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_-]{0,63}$",
            },
            "action_nonce": {
                "type": "string",
                "pattern": "^[A-Za-z0-9_-]{16,128}$",
            },
            "contract_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "confirmed": {"type": "boolean"},
            "responses": {"type": "object"},
            "instance_id": {"type": "string", "pattern": "^(?:[a-f0-9]{32})?$"},
        },
        "required": ["__elicitation_response__", "title", "view", "action", "confirmed"],
        "additionalProperties": False,
    }


def tool_definitions(*, mcp_apps: bool = False) -> list[types.Tool]:
    """The mirrored tools (names/schemas match attune-ai\'s server)."""
    form = _form_schema()
    template_props = _template_props()
    workspace = _workspace_schema()
    binding = _workspace_binding_schema()
    app_meta = mcp_app_tool_meta() if mcp_apps else None
    return [
        types.Tool(
            name="elicitation_render_form",
            description=(
                "Validate a declarative form and return it projected onto "
                "the host's own question control. Returns {success, "
                "host_question, host_question_admissible, profile_id} when "
                "the installed profile can carry the form, and "
                "{host_question_admissible: false, host_question_problems} "
                "naming what it cannot carry — never a silent truncation. "
                "Send a raw reply back through elicitation_collect_response "
                "as 'host_response' and it is decoded through the retained "
                "bindings. 'batches' is still returned but DEPRECATED "
                "(removal no earlier than 0.18.0); prefer host_question. "
                "Returns {success: false, problems} so you re-fix the "
                "definition. Pass either 'form' or 'template' + 'slots' "
                "(a stored template, cast server-side)."
            ),
            inputSchema={
                "type": "object",
                "properties": {"form": form, **template_props},
            },
        ),
        types.Tool(
            name="elicitation_render_widget",
            description=(
                "Render a declarative form as inline HTML for a widget "
                "surface. Returns {success, html, title, field_ids} — the "
                "widget posts answers back as a sentinel-marked JSON block "
                "('__elicitation_response__'); validate it with "
                "elicitation_collect_response. Prefer 'template' + 'slots' "
                "over composing 'form': the server loads, casts, validates "
                "and renders in this one call, and the form never transits "
                "your context."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    **template_props,
                    "message": {"type": "string"},
                },
            },
            **({"_meta": app_meta} if app_meta else {}),
        ),
        types.Tool(
            name="elicitation_collect_response",
            description=(
                "Validate the user's answers against a declarative form. "
                "Enforces required fields and option membership — returns "
                "{success: false, problems} naming exactly which fields to "
                "re-ask; never silently accepts malformed input. Name the "
                "form the same way it was rendered: 'form', or 'template' + "
                "'slots' (responses then carry the template as template_id). "
                "Pass 'answers' for typed answers, or 'host_response' for a "
                "raw reply from the host's question control — that is "
                "decoded through bindings re-derived from the same form, so "
                "an unmappable reply is named, never guessed. A host "
                "response may also return 'next_host_question', 'next_attempt' and "
                "'answered_so_far': a bounded re-ask of just the offending "
                "questions. Send ALL THREE back — the same 'form', the "
                "re-ask reply as 'host_response', plus 'attempt' and "
                "'answered_so_far' verbatim — or the narrowed reply cannot "
                "decode against the full form. Pass cancelled=true for a "
                "prompt the user dismissed."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    **template_props,
                    "answers": {"type": "object"},
                    "host_response": {"type": "object"},
                    "answered_so_far": {"type": "object"},
                    "cancelled": {"type": "boolean"},
                    "freeform": {"type": "object"},
                    "attempt": {"type": "integer", "minimum": 1},
                    "instance_id": {"type": "string", "pattern": "^(?:[a-f0-9]{32})?$"},
                },
            },
        ),
        types.Tool(
            name="elicitation_ask",
            description=(
                "Render a declarative form as a NATIVE MCP elicitation "
                "dialog and return validated answers in one call. If the "
                "client can't elicit, returns {success: false, action: "
                "'unsupported'} — fall back to elicitation_render_form. "
                "Pass either 'form' or 'template' + 'slots'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    **template_props,
                    "message": {"type": "string"},
                },
            },
        ),
        types.Tool(
            name="elicitation_render_workspace",
            description=(
                "Validate one command-workspace view and render equivalent "
                "widget HTML and portable Markdown. An optional action binding "
                "is copied into display-action responses; it never grants "
                "execution authority."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": workspace,
                    "binding": binding,
                    "instance_id": {"type": "string"},
                },
                "required": ["workspace"],
                "additionalProperties": False,
            },
            **({"_meta": app_meta} if app_meta else {}),
        ),
        types.Tool(
            name="elicitation_collect_workspace_action",
            description=(
                "Validate a workspace action against the exact rendered view "
                "and optional revision/hash/nonce binding. Returns only a "
                "validated action envelope; the host still authorizes and "
                "dispatches it."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "workspace": workspace,
                    "response": _workspace_response_schema(),
                    "binding": binding,
                },
                "required": ["workspace", "response"],
                "additionalProperties": False,
            },
        ),
    ]


def _parse_form(args: dict[str, Any]) -> tuple[Any, dict[str, Any] | None]:
    """Resolve the form from ``form`` OR ``template`` + ``slots`` (R5.2).

    The one seam every form-taking tool shares, so the fused template
    path behaves identically across render_form / render_widget /
    collect_response / ask. Returns ``(form, None)`` or
    ``(None, problems_envelope)`` — every problem listed, never raises.
    """
    form_def, template = args.get("form"), args.get("template")
    if (form_def is None) == (template is None):
        return None, {
            "success": False,
            "problems": [
                "pass exactly one of 'form' (a declarative form dict) or "
                "'template' (a stored template name, with 'slots')"
            ],
        }
    if template is None and args.get("slots") is not None:
        return None, {"success": False, "problems": ["'slots' requires 'template'"]}
    try:
        if template is not None:
            return form_from_template(template, args.get("slots")), None
        return form_from_dict(form_def), None
    except FormValidationError as e:
        return None, {"success": False, "problems": e.problems}


def _record_surface_choice(form: Any, *, chosen: str) -> str | None:
    try:
        return select_form_surface(form, keyboard_mode=keyboard_mode_enabled(), chosen=chosen)
    except (OSError, ValueError) as exc:
        logger.debug("surface-choice telemetry skipped: %s", exc)
        return None


def _host_question_profile() -> Any | None:
    """The installed profile of the route-active host-question target.

    Read from the registry rather than hardcoded, so the profile the
    server renders against is the same one the registry ratifies and
    the clean-wheel probe executes.
    """
    for target in iter_targets(RENDERER_REGISTRY):
        if target.target_id == "form.host_question" and target.status == "route_active":
            return installed_profile(target.profile_id)
    return None


async def handle_render_form(args: dict[str, Any]) -> dict[str, Any]:
    form, problems = _parse_form(args)
    if problems:
        return problems
    recommended = _record_surface_choice(form, chosen="ask")
    result: dict[str, Any] = {
        "success": True,
        "title": form.title,
        "description": form.description,
        # DEPRECATED alongside form_to_askuserquestion itself (removal no
        # earlier than 0.18.0). Kept because the tool description and the
        # skill both promise this key; retiring a documented contract
        # needs its own cycle. The private alias keeps the server from
        # warning users about its own internal choice.
        "batches": _form_to_askuserquestion(form),
    }
    profile = _host_question_profile()
    if profile is not None:
        verdict = host_question_admissibility(form, profile)
        result["profile_id"] = profile.id
        result["host_question_admissible"] = verdict.admissible
        if verdict.admissible:
            batch = form_to_host_question(form, profile)
            if batch is not None:
                # The route-active projection. Answer bindings stay
                # server-side; elicitation_collect_response re-derives
                # them from the same form to decode a raw host reply,
                # which is why they need not cross the wire.
                result["host_question"] = batch.payload
                result["response_correlation"] = batch.response_correlation
        else:
            result["host_question_problems"] = list(verdict.problems)
    if recommended == "widget":
        result["surface_note"] = (
            "The router recommends the widget for this form. "
            "AskUserQuestion will flatten it — use "
            "elicitation_render_widget unless the client cannot render "
            "widgets or the user is in keyboard mode."
        )
    return result


async def handle_render_widget(args: dict[str, Any]) -> dict[str, Any]:
    form, problems = _parse_form(args)
    if problems:
        return problems
    _record_surface_choice(form, chosen="widget")
    return {
        "success": True,
        "html": form_to_widget_html(form, args.get("message") or ""),
        "title": form.title,
        "field_ids": [q.id for q in form.questions],
        "mcp_app": mcp_app_result(
            collect_tool="elicitation_collect_response",
            collect_mode="form",
        ),
    }


async def handle_collect_response(args: dict[str, Any]) -> dict[str, Any]:
    # Exactly one source of answers. The schema cannot express "one of"
    # here without fighting the shared form/template properties, so the
    # handler names it: passing both would silently prefer one, and
    # passing neither would surface as every field being required.
    typed, raw = args.get("answers"), args.get("host_response")
    if typed is not None and raw is not None:
        return {
            "success": False,
            "problems": ["pass 'answers' (typed) or 'host_response' (a raw host reply), not both"],
        }
    if typed is None and raw is None:
        return {
            "success": False,
            "problems": ["provide 'answers' (typed) or 'host_response' (a raw host reply)"],
        }
    if raw is not None:
        return await _collect_host_response(args)
    answers = typed
    if not isinstance(answers, dict):
        # The SDK's jsonschema gate covers the stdio path, but the
        # handler is also a real import surface (attune-ai mirror), so
        # the module's own problems contract must hold here too.
        return {
            "success": False,
            "problems": [
                "'answers' must be an object mapping field ids to "
                f"answers, got {type(answers).__name__}"
            ],
        }
    form, problems = _parse_form(args)
    if problems:
        return problems
    try:
        response = collect_form_response(form, answers, template_id=args.get("template") or "")
    except FormValidationError as e:
        return {"success": False, "problems": e.problems}
    result: dict[str, Any] = {
        "success": True,
        "responses": response.responses,
        "response_id": response.response_id,
    }
    if args.get("template"):
        result["template_id"] = response.template_id
    try:
        log_submission(form_id=form.form_id, instance_id=args.get("instance_id", ""))
        hint = maybe_keyboard_hint(keyboard_mode=keyboard_mode_enabled())
    except (OSError, ValueError) as exc:
        logger.debug("keyboard-mode hint skipped: %s", exc)
        hint = None
    if hint:
        result["hint"] = hint
    return result


async def _collect_host_response(args: dict[str, Any]) -> dict[str, Any]:
    """Decode a raw host-question reply, validate it, and license a re-ask.

    The answer bindings are re-derived by rendering the same form again
    rather than round-tripping through the host: the renderer is pure,
    so the bindings are identical, and a binding the host could edit
    would not be a binding. The caller carries ``attempt`` so the
    profile's validation budget stays auditable across stateless calls.
    """
    form, problems = _parse_form(args)
    if problems:
        return problems
    profile = _host_question_profile()
    if profile is None:
        return {
            "success": False,
            "action": "unsupported",
            "problems": ["no route-active host-question profile is installed"],
        }
    batch = form_to_host_question(form, profile)
    if batch is None:
        verdict = host_question_admissibility(form, profile)
        return {
            "success": False,
            "action": "inadmissible",
            "problems": list(verdict.problems),
        }

    raw = args.get("host_response")
    # A wrong SHAPE is not a cancellation. Coercing it to None reported
    # `outcome: "cancelled"` with an empty problems list and a receipt
    # asserting the user cancelled a prompt they never saw a cancel on.
    # The stdio path is covered by the SDK's schema gate, but this
    # handler is also a direct import surface (the attune-ai mirror), so
    # it holds the problems contract itself.
    if args.get("cancelled") is True:
        raw = None
    elif not isinstance(raw, Mapping):
        return {
            "success": False,
            "problems": [
                "'host_response' must be an object mapping the host's question "
                f"keys to its replies, got {type(raw).__name__}; pass "
                "cancelled=true for a prompt the user dismissed"
            ],
        }
    prior = args.get("answered_so_far")
    if prior is not None and not isinstance(prior, Mapping):
        return {
            "success": False,
            "problems": [
                "'answered_so_far' must be the object a previous call returned, "
                f"got {type(prior).__name__}"
            ],
        }
    if raw is not None and prior:
        # A re-ask covers only the offending questions, but decoding is
        # fail-closed: every binding in the full batch needs a key. So
        # the reply so far is carried forward and the new answers
        # override it — rather than asking the caller to merge raw host
        # payloads, or weakening the missing-key rule that makes an
        # uncorrelatable reply a named problem.
        raw = {**prior, **raw}

    freeform = args.get("freeform") or None
    attempt = args.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        return {"success": False, "problems": ["'attempt' must be an integer >= 1"]}

    turn = host_question_turn(
        form,
        batch,
        profile,
        raw,
        freeform=freeform,
        attempt=attempt,
        template_id=args.get("template") or "",
    )
    result: dict[str, Any] = {
        "success": turn.outcome == "accepted",
        "outcome": turn.outcome,
        "attempt": turn.attempt,
        "problems": list(turn.problems),
        "unanswered": list(turn.decoding.unanswered),
        "other_selected": list(turn.decoding.other_selected),
        "receipt": turn.receipt.serialize(),
    }
    if turn.decoding.freeform:
        result["freeform"] = dict(turn.decoding.freeform)
    if turn.response is not None:
        result["responses"] = turn.response.responses
        result["response_id"] = turn.response.response_id
        if args.get("template"):
            result["template_id"] = turn.response.template_id
    if turn.next_batch is not None:
        # A bounded re-ask the profile still allows. All THREE go back on
        # the next call: without `answered_so_far` the narrowed reply
        # cannot decode against the full form, every question that was
        # not re-asked reads as a missing key, and the exchange
        # dead-ends as `undecodable` with the user's answer discarded.
        result["next_host_question"] = turn.next_batch.payload
        result["next_attempt"] = turn.attempt + 1
        result["answered_so_far"] = dict(raw) if raw else {}
    return result


def _parse_workspace_binding(
    raw: Any,
) -> tuple[WorkspaceActionBinding | None, dict[str, Any] | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, {"success": False, "problems": ["'binding' must be an object"]}
    expected = {"workspace_id", "revision", "action_nonce", "contract_hash"}
    problems = [f"binding has unknown key {key!r}" for key in raw if key not in expected]
    problems.extend(f"binding requires {key!r}" for key in sorted(expected - set(raw)))
    if problems:
        return None, {"success": False, "problems": problems}
    try:
        return WorkspaceActionBinding(**raw), None
    except (TypeError, ValueError) as exc:
        return None, {"success": False, "problems": [str(exc)]}


async def handle_render_workspace(args: dict[str, Any]) -> dict[str, Any]:
    """Render a strict workspace document through both portable surfaces."""
    try:
        view = workspace_from_dict(args.get("workspace", {}))
    except WorkspaceValidationError as exc:
        return {"success": False, "problems": exc.problems}
    binding, failure = _parse_workspace_binding(args.get("binding"))
    if failure:
        return failure
    instance_id = args.get("instance_id")
    if instance_id is not None and not isinstance(instance_id, str):
        return {"success": False, "problems": ["'instance_id' must be a string"]}
    try:
        html = workspace_to_widget_html(view, instance_id, binding=binding)
        markdown = workspace_to_markdown(view, binding=binding)
    except ValueError as exc:
        return {"success": False, "problems": [str(exc)]}
    return {
        "success": True,
        "html": html,
        "markdown": markdown,
        "title": view.title,
        "view": view.id.value,
        "action_ids": [action.id for action in view.actions],
        "bound": binding is not None,
        "mcp_app": mcp_app_result(
            collect_tool="elicitation_collect_workspace_action",
            collect_mode="workspace",
        ),
    }


async def handle_collect_workspace_action(args: dict[str, Any]) -> dict[str, Any]:
    """Validate one returned action without authorizing or executing it."""
    try:
        view = workspace_from_dict(args.get("workspace", {}))
    except WorkspaceValidationError as exc:
        return {"success": False, "problems": exc.problems}
    binding, failure = _parse_workspace_binding(args.get("binding"))
    if failure:
        return failure
    try:
        response = collect_workspace_action(view, args.get("response", {}), binding)
    except WorkspaceValidationError as exc:
        return {"success": False, "problems": exc.problems}
    return {
        "success": True,
        "view": response.view.value,
        "action": response.action,
        "confirmed": response.confirmed,
        "responses": response.responses_payload(),
        "workspace_id": response.workspace_id,
        "revision": response.revision,
        "action_nonce": response.action_nonce,
        "contract_hash": response.contract_hash,
    }


async def handle_ask(args: dict[str, Any]) -> dict[str, Any]:
    form, problems = _parse_form(args)
    if problems:
        return problems
    schema = form_to_elicitation_schema(form)
    message = args.get("message") or form.title or "Please complete this form."

    try:
        ctx = _server.request_context
        session = getattr(ctx, "session", None)
        request_id = getattr(ctx, "request_id", None)
    except (LookupError, RuntimeError):
        session, request_id = None, None
    if session is None or not hasattr(session, "elicit_form"):
        return {
            "success": False,
            "action": "unsupported",
            "error": "No MCP elicitation session available (client cannot elicit).",
        }
    try:
        result = await session.elicit_form(message, schema, request_id)
    except Exception as e:  # noqa: BLE001
        # INTENTIONAL: any elicit failure (unsupported capability,
        # transport) degrades to a fallback signal, never crashes.
        logger.exception("Elicitation request failed")
        return {
            "success": False,
            "action": "error",
            "error": f"Elicitation failed: {type(e).__name__}",
        }
    action = getattr(result, "action", None)
    if action != "accept":
        return {"success": False, "action": action or "cancel", "responses": {}}
    try:
        response = collect_form_response(
            form, getattr(result, "content", None) or {}, template_id=args.get("template") or ""
        )
    except FormValidationError as e:
        return {"success": False, "action": "accept", "problems": e.problems}
    accepted: dict[str, Any] = {
        "success": True,
        "action": "accept",
        "responses": response.responses,
        "response_id": response.response_id,
    }
    if args.get("template"):
        accepted["template_id"] = response.template_id
    return accepted


_HANDLERS = {
    "elicitation_render_form": handle_render_form,
    "elicitation_render_widget": handle_render_widget,
    "elicitation_collect_response": handle_collect_response,
    "elicitation_ask": handle_ask,
    "elicitation_render_workspace": handle_render_workspace,
    "elicitation_collect_workspace_action": handle_collect_workspace_action,
}


@_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    try:
        capabilities = _server.request_context.session.client_params.capabilities
    except (AttributeError, LookupError, RuntimeError):
        capabilities = None
    return tool_definitions(mcp_apps=client_supports_mcp_apps(capabilities))


@_server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"success": False, "error": f"Unknown tool: {name}"}
    return await handler(arguments or {})


@_server.list_resources()
async def _list_resources() -> list[types.Resource]:
    resource = mcp_app_resource()
    return [
        types.Resource(
            uri=resource["uri"],
            name=resource["name"],
            description=resource["description"],
            mimeType=resource["mime_type"],
            **{"_meta": resource["meta"]},
        )
    ]


@_server.read_resource()
async def _read_resource(uri: Any) -> list[ReadResourceContents]:
    resource = mcp_app_resource()
    if str(uri) != resource["uri"]:
        raise ValueError(f"Unknown resource: {uri}")
    return [
        ReadResourceContents(
            content=resource["text"],
            mime_type=resource["mime_type"],
        )
    ]


def _initialization_options() -> Any:
    """Advertise the stable MCP Apps extension alongside core MCP."""
    options = _server.create_initialization_options()
    extensions = {
        MCP_APPS_EXTENSION: {
            "mimeTypes": [MCP_APP_MIME_TYPE],
        }
    }
    capabilities = options.capabilities.model_copy(update={"extensions": extensions})
    return options.model_copy(update={"capabilities": capabilities})


async def _run() -> None:
    async with stdio_server() as (read, write):
        await _server.run(read, write, _initialization_options())


def main() -> None:
    """Console-script entry point (``attune-forms-mcp``)."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
