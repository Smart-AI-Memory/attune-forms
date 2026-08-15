"""Standalone MCP server for the attune-forms substrate (spec Phase 2).

Mirrors attune-ai\'s four elicitation tools — same names, same schemas,
same result shapes (chair-ruled D3: identical surface makes the later
convergence a pure swap and lets docs/skills transfer verbatim):

- ``elicitation_render_form``     — form dict -> AskUserQuestion batches
- ``elicitation_render_widget``   — form dict -> self-contained HTML
- ``elicitation_collect_response``— form + answers -> validated response
- ``elicitation_ask``             — native MCP elicitation round-trip

Launch: ``attune-forms-mcp`` (console script) or
``uvx --from 'attune-forms[mcp]' attune-forms-mcp`` — the exact command
a plugin ``.mcp.json`` carries.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from attune_forms.bridge import (
    FormValidationError,
    collect_form_response,
    form_from_dict,
    form_response_summary,  # noqa: F401  (re-exported convenience)
    form_to_askuserquestion,
    keyboard_mode_enabled,
    select_form_surface,
)
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.form_events import log_submission, maybe_keyboard_hint
from attune_forms.widget import form_to_widget_html

logger = logging.getLogger(__name__)

_server: Server = Server("attune-forms")


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
                    "over a reviewed list; answer = {item id: disposition})."
                ),
            },
            "options": {"type": "array", "items": {"type": "string"}},
            "default": {"type": "string"},
            "help_text": {"type": "string"},
            "required": {"type": "boolean", "description": "Defaults to true"},
            "minimum": {"type": "number"},
            "maximum": {"type": "number"},
            "max_length": {"type": "integer"},
            "rationale": {"type": "string"},
            "recommended": {"type": "string"},
            "option_notes": {"type": "object"},
            "user_position": {"type": "string"},
            "progress_items": {"type": "array"},
            "progress_style": {"type": "string", "enum": ["report"]},
            "endorsements": {
                "type": "object",
                "description": "deliberation: {option: [voice, ...]}",
            },
            "triage_items": {
                "type": "array",
                "description": "triage: [{label, id?, detail?, tag?}, ...]",
            },
            "dispositions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "triage: the shared per-item ruling vocabulary",
            },
            "suggested": {
                "type": "object",
                "description": "triage: {item id: proposed disposition}",
            },
            "list_style": {"type": "string", "enum": ["ordered", "unordered"]},
        },
        "required": ["id", "text", "type"],
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
    }


def tool_definitions() -> list[types.Tool]:
    """The four mirrored tools (names/schemas match attune-ai\'s server)."""
    form = _form_schema()
    return [
        types.Tool(
            name="elicitation_render_form",
            description=(
                "Validate a declarative form and return batched question "
                "payloads (<=4 per batch) ready for the AskUserQuestion "
                "tool. Returns {success, batches} or {success: false, "
                "problems} so you re-fix the definition."
            ),
            inputSchema={
                "type": "object",
                "properties": {"form": form},
                "required": ["form"],
            },
        ),
        types.Tool(
            name="elicitation_render_widget",
            description=(
                "Render a declarative form as inline HTML for a widget "
                "surface. Returns {success, html, title, field_ids} — the "
                "widget posts answers back as a sentinel-marked JSON block "
                "('__elicitation_response__'); validate it with "
                "elicitation_collect_response."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    "message": {"type": "string"},
                },
                "required": ["form"],
            },
        ),
        types.Tool(
            name="elicitation_collect_response",
            description=(
                "Validate the user's answers against a declarative form. "
                "Enforces required fields and option membership — returns "
                "{success: false, problems} naming exactly which fields to "
                "re-ask; never silently accepts malformed input."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    "answers": {"type": "object"},
                },
                "required": ["form", "answers"],
            },
        ),
        types.Tool(
            name="elicitation_ask",
            description=(
                "Render a declarative form as a NATIVE MCP elicitation "
                "dialog and return validated answers in one call. If the "
                "client can't elicit, returns {success: false, action: "
                "'unsupported'} — fall back to elicitation_render_form."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "form": form,
                    "message": {"type": "string"},
                },
                "required": ["form"],
            },
        ),
    ]


def _parse_form(args: dict[str, Any]) -> tuple[Any, dict[str, Any] | None]:
    try:
        return form_from_dict(args.get("form", {})), None
    except FormValidationError as e:
        return None, {"success": False, "problems": e.problems}


def _record_surface_choice(form: Any, *, chosen: str) -> str | None:
    try:
        return select_form_surface(form, keyboard_mode=keyboard_mode_enabled(), chosen=chosen)
    except (OSError, ValueError) as exc:
        logger.debug("surface-choice telemetry skipped: %s", exc)
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
        "batches": form_to_askuserquestion(form),
    }
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
    }


async def handle_collect_response(args: dict[str, Any]) -> dict[str, Any]:
    try:
        form = form_from_dict(args.get("form", {}))
        response = collect_form_response(form, args.get("answers", {}))
    except FormValidationError as e:
        return {"success": False, "problems": e.problems}
    result: dict[str, Any] = {
        "success": True,
        "responses": response.responses,
        "response_id": response.response_id,
    }
    try:
        log_submission()
        hint = maybe_keyboard_hint(keyboard_mode=keyboard_mode_enabled())
    except (OSError, ValueError) as exc:
        logger.debug("keyboard-mode hint skipped: %s", exc)
        hint = None
    if hint:
        result["hint"] = hint
    return result


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
        response = collect_form_response(form, getattr(result, "content", None) or {})
    except FormValidationError as e:
        return {"success": False, "action": "accept", "problems": e.problems}
    return {
        "success": True,
        "action": "accept",
        "responses": response.responses,
        "response_id": response.response_id,
    }


_HANDLERS = {
    "elicitation_render_form": handle_render_form,
    "elicitation_render_widget": handle_render_widget,
    "elicitation_collect_response": handle_collect_response,
    "elicitation_ask": handle_ask,
}


@_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    return tool_definitions()


@_server.call_tool()
async def _call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    handler = _HANDLERS.get(name)
    if handler is None:
        return {"success": False, "error": f"Unknown tool: {name}"}
    return await handler(arguments or {})


async def _run() -> None:
    async with stdio_server() as (read, write):
        await _server.run(read, write, _server.create_initialization_options())


def main() -> None:
    """Console-script entry point (``attune-forms-mcp``)."""
    asyncio.run(_run())


if __name__ == "__main__":
    main()
