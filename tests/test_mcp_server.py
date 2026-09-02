"""Non-mocked stdio round-trip for the standalone MCP server (R2.4).

Spawns the real server as a subprocess over stdio, performs the MCP
handshake, lists tools, and exercises every tool through the live
transport — no mocks anywhere on the boundary.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

mcp = pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp import types as mcp_types  # noqa: E402
from mcp.client.stdio import get_default_environment, stdio_client  # noqa: E402
from mcp.shared.version import LATEST_PROTOCOL_VERSION  # noqa: E402

from attune_forms.mcp_app import (  # noqa: E402
    MCP_APP_MIME_TYPE,
    MCP_APP_RESOURCE_URI,
    MCP_APPS_EXTENSION,
)

_SRC = str(Path(__file__).resolve().parents[1] / "src")

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

_WORKSPACE = {
    "id": "preview",
    "title": "Fix preview",
    "sections": [
        {
            "heading": "Contract",
            "blocks": [
                {
                    "kind": "key_value",
                    "items": [{"label": "Outcome", "value": "Repair parsing"}],
                }
            ],
        }
    ],
    "actions": [
        {
            "id": "run_fix",
            "label": "Run Fix",
            "intent": "primary",
            "consequence": "Execute the previewed contract.",
            "requires_explicit_choice": True,
        },
        {"id": "edit_contract", "label": "Back to edit"},
    ],
}
_ACTION_RESPONSE_WORKSPACE = {
    "id": "preview",
    "title": "Roundtable promotion review",
    "actions": [
        {
            "id": "apply_rulings",
            "label": "Apply rulings",
            "intent": "primary",
            "consequence": "Apply this complete ruling batch.",
            "requires_explicit_choice": True,
            "response_fields": [
                {
                    "id": "candidate_1",
                    "text": "Candidate one",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                },
                {
                    "id": "candidate_2",
                    "text": "Candidate two",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                },
            ],
        },
        {"id": "another_round", "label": "Another round"},
    ],
}
_BINDING = {
    "workspace_id": "fix-demo",
    "revision": 3,
    "action_nonce": "nonce_0123456789abcdef",
    "contract_hash": "a" * 64,
}


def _server_params(home: Path) -> StdioServerParameters:
    """Spawn params with an explicit env: stdio_client's default env strips
    ATTUNE_HOME (keeping the real HOME), so without this the server
    subprocess writes telemetry into the developer's live ~/.attune —
    and PYTHONPATH pins the server to THIS checkout's src (same hazard
    conftest.py documents for in-process imports)."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "attune_forms.mcp_server"],
        env={**get_default_environment(), "ATTUNE_HOME": str(home), "PYTHONPATH": _SRC},
    )


def _payload(result) -> dict:
    """Extract the tool's dict payload from a CallToolResult."""
    if getattr(result, "structuredContent", None):
        sc = result.structuredContent
        return sc.get("result", sc) if isinstance(sc, dict) else sc
    text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
    return json.loads(text)


class _McpAppsClientSession(ClientSession):
    """ClientSession that advertises the official MCP Apps extension."""

    async def initialize(self) -> mcp_types.InitializeResult:
        capabilities = mcp_types.ClientCapabilities.model_validate(
            {
                "extensions": {
                    MCP_APPS_EXTENSION: {
                        "mimeTypes": [MCP_APP_MIME_TYPE],
                    }
                }
            }
        )
        result = await self.send_request(
            mcp_types.ClientRequest(
                mcp_types.InitializeRequest(
                    params=mcp_types.InitializeRequestParams(
                        protocolVersion=LATEST_PROTOCOL_VERSION,
                        capabilities=capabilities,
                        clientInfo=self._client_info,
                    )
                )
            ),
            mcp_types.InitializeResult,
        )
        self._server_capabilities = result.capabilities
        await self.send_notification(
            mcp_types.ClientNotification(mcp_types.InitializedNotification())
        )
        return result


async def _round_trip(home: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    async with stdio_client(_server_params(home)) as (read, write):
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

            r = await session.call_tool(
                "elicitation_render_workspace",
                {"workspace": _WORKSPACE, "binding": _BINDING},
            )
            out["render_workspace"] = _payload(r)

            r = await session.call_tool(
                "elicitation_render_workspace",
                {"workspace": _ACTION_RESPONSE_WORKSPACE, "binding": _BINDING},
            )
            out["render_workspace_responses"] = _payload(r)

            response = {
                "__elicitation_response__": True,
                "title": "Fix preview",
                "view": "preview",
                "action": "run_fix",
                "confirmed": True,
                **_BINDING,
            }
            r = await session.call_tool(
                "elicitation_collect_workspace_action",
                {
                    "workspace": _WORKSPACE,
                    "binding": _BINDING,
                    "response": response,
                },
            )
            out["collect_workspace"] = _payload(r)

            action_response = {
                "__elicitation_response__": True,
                "title": "Roundtable promotion review",
                "view": "preview",
                "action": "apply_rulings",
                "confirmed": True,
                "responses": {"candidate_1": "promote", "candidate_2": "decline"},
                **_BINDING,
            }
            r = await session.call_tool(
                "elicitation_collect_workspace_action",
                {
                    "workspace": _ACTION_RESPONSE_WORKSPACE,
                    "binding": _BINDING,
                    "response": action_response,
                },
            )
            out["collect_workspace_responses"] = _payload(r)

            response["revision"] = 2
            r = await session.call_tool(
                "elicitation_collect_workspace_action",
                {
                    "workspace": _WORKSPACE,
                    "binding": _BINDING,
                    "response": response,
                },
            )
            out["collect_workspace_stale"] = _payload(r)
    return out


async def _mcp_apps_round_trip(home: Path) -> dict[str, object]:
    out: dict[str, object] = {}
    async with stdio_client(_server_params(home)) as (read, write):
        async with _McpAppsClientSession(read, write) as session:
            initialized = await session.initialize()
            out["server_capabilities"] = initialized.capabilities.model_dump(
                by_alias=True, exclude_none=True
            )

            tools = await session.list_tools()
            out["tool_meta"] = {tool.name: tool.meta for tool in tools.tools}

            resources = await session.list_resources()
            out["resource_uris"] = [str(resource.uri) for resource in resources.resources]
            resource = await session.read_resource(resources.resources[0].uri)
            out["resource"] = resource.contents[0]

            rendered = await session.call_tool("elicitation_render_widget", {"form": _FORM})
            out["render_widget"] = _payload(rendered)
            workspace = await session.call_tool(
                "elicitation_render_workspace",
                {"workspace": _WORKSPACE, "binding": _BINDING},
            )
            out["render_workspace"] = _payload(workspace)
    return out


@pytest.fixture(scope="module")
def round_trip(tmp_path_factory):
    return asyncio.run(_round_trip(tmp_path_factory.mktemp("attune-home")))


@pytest.fixture(scope="module")
def mcp_apps_round_trip(tmp_path_factory):
    return asyncio.run(_mcp_apps_round_trip(tmp_path_factory.mktemp("attune-app-home")))


def test_all_six_tools_listed(round_trip):
    assert round_trip["tools"]["names"] == [
        "elicitation_ask",
        "elicitation_collect_response",
        "elicitation_collect_workspace_action",
        "elicitation_render_form",
        "elicitation_render_widget",
        "elicitation_render_workspace",
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


def test_workspace_tools_round_trip_over_real_stdio(round_trip):
    rendered = round_trip["render_workspace"]
    assert rendered["success"] is True
    assert rendered["bound"] is True
    assert rendered["action_ids"] == ["run_fix", "edit_contract"]
    assert '"workspace_id":"fix-demo"' in rendered["html"]
    assert '"workspace_id": "fix-demo"' in rendered["markdown"]

    rendered_responses = round_trip["render_workspace_responses"]
    assert rendered_responses["success"] is True
    assert rendered_responses["bound"] is True
    assert rendered_responses["action_ids"] == ["apply_rulings", "another_round"]
    assert 'payload["responses"] = answers' in rendered_responses["html"]
    assert '"candidate_1": null' in rendered_responses["markdown"]

    collected = round_trip["collect_workspace"]
    assert collected["success"] is True
    assert collected["action"] == "run_fix"
    assert collected["revision"] == 3
    assert collected["responses"] == {}

    action_responses = round_trip["collect_workspace_responses"]
    assert action_responses["success"] is True
    assert action_responses["responses"] == {
        "candidate_1": "promote",
        "candidate_2": "decline",
    }

    stale = round_trip["collect_workspace_stale"]
    assert stale["success"] is False
    assert any("revision does not match" in problem for problem in stale["problems"])


def test_mcp_apps_negotiates_resource_metadata_and_transport_over_real_stdio(
    mcp_apps_round_trip,
) -> None:
    extensions = mcp_apps_round_trip["server_capabilities"]["extensions"]
    assert extensions[MCP_APPS_EXTENSION]["mimeTypes"] == [MCP_APP_MIME_TYPE]

    tool_meta = mcp_apps_round_trip["tool_meta"]
    assert tool_meta["elicitation_render_widget"]["ui"]["resourceUri"] == MCP_APP_RESOURCE_URI
    assert tool_meta["elicitation_render_workspace"]["ui"]["resourceUri"] == MCP_APP_RESOURCE_URI
    assert tool_meta["elicitation_render_form"] is None

    assert mcp_apps_round_trip["resource_uris"] == [MCP_APP_RESOURCE_URI]
    resource = mcp_apps_round_trip["resource"]
    assert resource.mimeType == MCP_APP_MIME_TYPE
    assert "ui/notifications/tool-result" in resource.text

    form = mcp_apps_round_trip["render_widget"]
    assert form["mcp_app"]["collect_tool"] == "elicitation_collect_response"
    assert form["mcp_app"]["collect_mode"] == "form"
    workspace = mcp_apps_round_trip["render_workspace"]
    assert workspace["mcp_app"]["collect_tool"] == "elicitation_collect_workspace_action"
    assert workspace["mcp_app"]["collect_mode"] == "workspace"


def test_non_ui_client_gets_no_ui_metadata_but_keeps_meaningful_result(round_trip) -> None:
    from attune_forms.mcp_server import tool_definitions

    tools = {tool.name: tool for tool in tool_definitions()}
    assert tools["elicitation_render_widget"].meta is None
    rendered = round_trip["render_widget"]
    assert rendered["success"] is True
    assert rendered["html"]
    assert rendered["mcp_app"]["collect_mode"] == "form"


def test_workspace_handlers_preserve_the_problems_contract_on_import() -> None:
    from attune_forms.mcp_server import handle_render_workspace

    rendered = asyncio.run(
        handle_render_workspace(
            {"workspace": _WORKSPACE, "binding": _BINDING, "instance_id": "direct"}
        )
    )
    assert rendered["success"] is True
    assert rendered["bound"] is True

    bad_view = asyncio.run(handle_render_workspace({"workspace": {"id": "preview"}}))
    assert bad_view["success"] is False
    assert any("title" in problem for problem in bad_view["problems"])

    bad_binding = asyncio.run(handle_render_workspace({"workspace": _WORKSPACE, "binding": "bad"}))
    assert bad_binding == {"success": False, "problems": ["'binding' must be an object"]}

    missing_binding_key = asyncio.run(
        handle_render_workspace(
            {
                "workspace": _WORKSPACE,
                "binding": {"workspace_id": "fix-demo", "extra": "bad"},
            }
        )
    )
    assert missing_binding_key["success"] is False
    assert any("unknown key" in problem for problem in missing_binding_key["problems"])
    assert any("requires 'revision'" in problem for problem in missing_binding_key["problems"])

    malformed_binding = asyncio.run(
        handle_render_workspace(
            {"workspace": _WORKSPACE, "binding": {**_BINDING, "revision": True}}
        )
    )
    assert malformed_binding["success"] is False
    assert any("revision" in problem for problem in malformed_binding["problems"])

    bad_instance = asyncio.run(handle_render_workspace({"workspace": _WORKSPACE, "instance_id": 7}))
    assert bad_instance == {
        "success": False,
        "problems": ["'instance_id' must be a string"],
    }

    form_workspace = {
        "id": "intake",
        "title": "Fix intake",
        "form": _FORM,
        "actions": [{"id": "preview_fix", "label": "Preview fix"}],
    }
    bound_form = asyncio.run(
        handle_render_workspace({"workspace": form_workspace, "binding": _BINDING})
    )
    assert bound_form["success"] is False
    assert any("not valid on a form view" in problem for problem in bound_form["problems"])


def test_workspace_collect_handler_rejects_invalid_view_binding_and_response() -> None:
    from attune_forms.mcp_server import handle_collect_workspace_action

    bad_view = asyncio.run(handle_collect_workspace_action({"workspace": {}}))
    assert bad_view["success"] is False

    bad_binding = asyncio.run(
        handle_collect_workspace_action(
            {"workspace": _WORKSPACE, "binding": {**_BINDING, "revision": True}}
        )
    )
    assert bad_binding["success"] is False

    bad_response = asyncio.run(
        handle_collect_workspace_action(
            {
                "workspace": _WORKSPACE,
                "binding": _BINDING,
                "response": {"action": "delete_repo"},
            }
        )
    )
    assert bad_response["success"] is False
    assert any("not allowed" in problem for problem in bad_response["problems"])


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


@pytest.mark.parametrize("bad", ["src/", None, ["src/"], 7], ids=lambda v: type(v).__name__)
def test_collect_response_import_path_guards_non_dict_answers(bad):
    """Confirmation pass 1 needs-a-look (2026-08-20): a non-dict
    ``answers`` raised a raw AttributeError/TypeError when the handler
    is called as an import — the SDK's jsonschema gate only covers the
    stdio path, and the attune-ai mirror convergence plan makes import
    reach real. The module's own contract shape must hold instead."""
    from attune_forms.mcp_server import handle_collect_response

    result = asyncio.run(handle_collect_response({"form": _FORM, "answers": bad}))
    assert result["success"] is False
    assert any("answers" in p for p in result["problems"])


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


def test_schemas_close_unknown_keys():
    """Confirmation-pass-1 chair ruling (2026-08-20): unknown definition
    keys are strictly rejected at BOTH layers — the advertised schema
    must not wave through what form_from_dict names as a problem."""
    from attune_forms.mcp_server import _field_schema, _form_schema

    assert _field_schema()["additionalProperties"] is False
    assert _form_schema()["additionalProperties"] is False


def test_field_schema_matches_parser_key_set():
    """Ratchet: the mirrored _field_schema and form_from_dict's strict
    key set may not drift apart. 'label' is the parser-side alias for
    'text' — never advertised (the schema requires 'text', so the alias
    was never usable over stdio)."""
    from attune_forms.bridge import _DEFINITION_FIELD_KEYS
    from attune_forms.mcp_server import _field_schema

    advertised = set(_field_schema()["properties"])
    assert advertised | {"label"} == set(_DEFINITION_FIELD_KEYS)


def test_field_schema_covers_the_whole_grammar():
    """Drift catcher (architecture review F5, 2026-08-20): the
    hand-maintained tool schema must keep up with the grammar — every
    QuestionType value in its type enum, every FormQuestion field
    (except the internal timestamp-free ones the schema derives) in its
    properties. The prose description stays hand-written on purpose; do
    NOT generate this schema from models."""
    from dataclasses import fields as dc_fields

    from attune_forms.mcp_server import _field_schema
    from attune_forms.models import FormQuestion, QuestionType

    schema = _field_schema()
    assert set(schema["properties"]["type"]["enum"]) == {t.value for t in QuestionType}
    schema_props = set(schema["properties"])
    question_fields = {f.name for f in dc_fields(FormQuestion)}
    missing = question_fields - schema_props
    assert not missing, f"FormQuestion field(s) absent from _field_schema: {sorted(missing)}"


def test_workspace_schemas_match_the_strict_parser_key_sets():
    """The MCP gate and import-path parser must reject the same extra keys."""
    from attune_forms.mcp_server import _workspace_response_schema, _workspace_schema
    from attune_forms.workspace import (
        _ACTION_KEYS,
        _ACTION_RESPONSE_KEYS,
        _BLOCK_KEYS,
        _ITEM_KEYS,
        _SECTION_KEYS,
        _WORKSPACE_KEYS,
    )

    workspace = _workspace_schema()
    assert set(workspace["properties"]) == set(_WORKSPACE_KEYS)
    section = workspace["properties"]["sections"]["items"]
    assert set(section["properties"]) == set(_SECTION_KEYS)
    block = section["properties"]["blocks"]["items"]
    assert set(block["properties"]) == set(_BLOCK_KEYS)
    item = block["properties"]["items"]["items"]
    assert set(item["properties"]) == set(_ITEM_KEYS)
    action = workspace["properties"]["actions"]["items"]
    assert set(action["properties"]) == set(_ACTION_KEYS)
    assert set(_workspace_response_schema()["properties"]) == set(_ACTION_RESPONSE_KEYS)
