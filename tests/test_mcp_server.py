"""Non-mocked stdio round-trip for the standalone MCP server (R2.4).

Spawns the real server as a subprocess over stdio, performs the MCP
handshake, lists tools, and exercises every tool through the live
transport — no mocks anywhere on the boundary.
"""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

mcp = pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

_FORM = {
    "title": "Audit scope",
    "fields": [
        {"id": "path", "type": "text_input", "text": "Which path?"},
        {
            "id": "depth",
            "type": "single_select",
            "text": "How deep?",
            "options": ["quick", "thorough"],
        },
    ],
}


def _server_params() -> StdioServerParameters:
    return StdioServerParameters(command=sys.executable, args=["-m", "attune_forms.mcp_server"])


def _payload(result) -> dict:
    """Extract the tool's dict payload from a CallToolResult."""
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    return json.loads(text)


async def _round_trip() -> dict[str, dict]:
    out: dict[str, dict] = {}
    async with stdio_client(_server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            out["tools"] = {"names": sorted(t.name for t in tools.tools)}

            r = await session.call_tool("elicitation_render_form", {"form": _FORM})
            out["render_form"] = _payload(r)

            r = await session.call_tool("elicitation_render_widget", {"form": _FORM})
            out["render_widget"] = _payload(r)

            r = await session.call_tool(
                "elicitation_collect_response",
                {"form": _FORM, "answers": {"path": "src/", "depth": "quick"}},
            )
            out["collect_ok"] = _payload(r)

            r = await session.call_tool(
                "elicitation_collect_response",
                {"form": _FORM, "answers": {"depth": "nonsense"}},
            )
            out["collect_bad"] = _payload(r)

            r = await session.call_tool("elicitation_ask", {"form": _FORM})
            out["ask"] = _payload(r)
    return out


@pytest.fixture(scope="module")
def round_trip():
    return asyncio.run(_round_trip())


def test_all_four_tools_listed(round_trip):
    assert round_trip["tools"]["names"] == [
        "elicitation_ask",
        "elicitation_collect_response",
        "elicitation_render_form",
        "elicitation_render_widget",
    ]


def test_render_form_batches(round_trip):
    p = round_trip["render_form"]
    assert p["success"] is True
    assert p["title"] == "Audit scope"
    assert p["batches"] and len(p["batches"][0]) == 2


def test_render_widget_html(round_trip):
    p = round_trip["render_widget"]
    assert p["success"] is True
    assert "__elicitation_response__" in p["html"]
    assert p["field_ids"] == ["path", "depth"]


def test_collect_validates_good_answers(round_trip):
    p = round_trip["collect_ok"]
    assert p["success"] is True
    assert p["responses"] == {"path": "src/", "depth": "quick"}


def test_collect_rejects_bad_answers_with_problems(round_trip):
    p = round_trip["collect_bad"]
    assert p["success"] is False
    assert any("path" in prob for prob in p["problems"])
    assert any("nonsense" in prob for prob in p["problems"])


def test_ask_degrades_without_elicitation_capability(round_trip):
    p = round_trip["ask"]
    assert p["success"] is False
    assert p["action"] in ("unsupported", "error", "cancel", "decline")


def test_field_schema_default_is_answer_shaped_and_inferred_from_declared():
    """Verify-pass finding (2026-08-20): the advertised inputSchema typed
    `default` as string — wrong since defaults validate like answers
    (multi_select: list; number: numeric; boolean: Yes/No) — and omitted
    inferred_from entirely. Confirmation pass 1 added "object": a triage
    default is a legal {item id: disposition} dict, and the SDK's
    jsonschema gate rejected it at the front door before the tool's
    problems contract could run."""
    from attune_forms.mcp_server import _field_schema

    props = _field_schema()["properties"]
    assert set(props["default"]["type"]) == {"string", "number", "boolean", "array", "object"}
    assert "inferred_from" in props


def test_schema_accepts_legal_triage_object_default():
    """The exact confirmation-pass-1 repro: a form form_from_dict accepts
    must pass the advertised inputSchema (the SDK validates against it
    before the tool runs)."""
    jsonschema = pytest.importorskip("jsonschema")
    from attune_forms import form_from_dict
    from attune_forms.mcp_server import tool_definitions

    form = {
        "title": "t",
        "fields": [
            {
                "id": "tri",
                "type": "triage",
                "text": "Rule.",
                "triage_items": [{"id": "t1", "label": "A"}],
                "dispositions": ["keep", "drop"],
                "required": False,
                "default": {"t1": "keep"},
            }
        ],
    }
    form_from_dict(form)  # legal by the library's own validator
    tools = {t.name: t for t in tool_definitions()}
    jsonschema.validate({"form": form}, tools["elicitation_render_form"].inputSchema)
