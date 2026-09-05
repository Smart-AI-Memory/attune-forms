"""The fused template path on every form-taking MCP tool (spec R5.2).

``template`` + ``slots`` is loaded, cast, validated and rendered
server-side in ONE call through the one seam the handlers share, so the
form dict never transits the agent's context. In-process handler tests
here; the real-stdio round trip lives in ``test_mcp_server.py``.
"""

from __future__ import annotations

import asyncio

import jsonschema
import pytest

mcp = pytest.importorskip("mcp")

from attune_forms.mcp_server import (  # noqa: E402
    _template_props,
    handle_ask,
    handle_collect_response,
    handle_render_form,
    handle_render_widget,
    tool_definitions,
)

_TEMPLATE_ARGS = {"template": "session-contract", "slots": {"project": "attune-ai"}}
_FORM = {
    "title": "Audit scope",
    "fields": [{"id": "path", "type": "text_input", "text": "Which path?"}],
}
_ANSWERS = {
    "mode": "Executing a planned spec",
    "outcome": "R5.2 shipped",
    "done_when": "both PRs green",
}
_ONE_OF_PROBLEM = (
    "pass exactly one of 'form' (a declarative form dict) or "
    "'template' (a stored template name, with 'slots')"
)


def test_render_widget_casts_the_template_server_side():
    out = asyncio.run(handle_render_widget(_TEMPLATE_ARGS))
    assert out["success"] is True
    assert out["title"] == "Session contract — attune-ai"
    assert out["field_ids"] == ["mode", "outcome", "done_when", "effort_cap"]
    assert "Session contract — attune-ai" in out["html"]
    assert "{project}" not in out["html"]
    assert "form" not in out  # the definition never comes back to the agent


def test_render_form_batches_the_cast_template():
    out = asyncio.run(handle_render_form(_TEMPLATE_ARGS))
    assert out["success"] is True
    assert out["title"] == "Session contract — attune-ai"
    assert out["batches"]


def test_collect_from_template_validates_and_carries_template_id(monkeypatch):
    import attune_forms.mcp_server as server

    seen: dict = {}
    real = server.collect_form_response

    def spy(form, answers, template_id=""):
        seen["template_id"] = template_id
        return real(form, answers, template_id=template_id)

    monkeypatch.setattr(server, "collect_form_response", spy)
    out = asyncio.run(handle_collect_response({**_TEMPLATE_ARGS, "answers": _ANSWERS}))
    assert out["success"] is True
    assert out["responses"]["mode"] == "Executing a planned spec"
    assert seen["template_id"] == "session-contract"


def test_collect_from_template_still_lists_answer_problems():
    out = asyncio.run(handle_collect_response({**_TEMPLATE_ARGS, "answers": {}}))
    assert out["success"] is False
    assert any("mode" in p for p in out["problems"])


def test_slot_problems_are_listed_not_raised():
    out = asyncio.run(handle_render_widget({"template": "session-contract", "slots": {}}))
    assert out == {"success": False, "problems": ["missing value for slot 'project'"]}


def test_unknown_template_lists_the_available_ones():
    out = asyncio.run(handle_render_widget({"template": "no-such-template"}))
    assert out["success"] is False
    assert any("session-contract" in p for p in out["problems"])


@pytest.mark.parametrize(
    "args",
    [{}, {"message": "only a message"}, {"form": _FORM, "template": "session-contract"}],
)
def test_exactly_one_of_form_or_template(args):
    out = asyncio.run(handle_render_widget(args))
    assert out == {"success": False, "problems": [_ONE_OF_PROBLEM]}


def test_slots_without_template_is_a_problem():
    out = asyncio.run(handle_render_widget({"form": _FORM, "slots": {"project": "x"}}))
    assert out == {"success": False, "problems": ["'slots' requires 'template'"]}


def test_every_form_tool_shares_the_seam():
    both = {"form": _FORM, "template": "session-contract", "answers": {}}
    outs = [
        asyncio.run(h(both))
        for h in (handle_render_form, handle_render_widget, handle_collect_response, handle_ask)
    ]
    assert all(o == {"success": False, "problems": [_ONE_OF_PROBLEM]} for o in outs)


def test_form_path_is_unchanged():
    out = asyncio.run(handle_render_widget({"form": _FORM}))
    assert out["success"] is True
    assert out["field_ids"] == ["path"]


def test_schemas_advertise_the_template_path_without_requiring_form():
    tools = {t.name: t for t in tool_definitions()}
    for name in (
        "elicitation_render_form",
        "elicitation_render_widget",
        "elicitation_collect_response",
        "elicitation_ask",
    ):
        schema = tools[name].inputSchema
        assert schema["properties"]["template"] == _template_props()["template"], name
        assert schema["properties"]["slots"] == _template_props()["slots"], name
        assert "form" not in schema.get("required", []), name
        # Both shapes are legal at the schema layer; the handler decides.
        jsonschema.validate({**_TEMPLATE_ARGS, "answers": {}}, schema)
        jsonschema.validate({"form": _FORM, "answers": {}}, schema)
    assert tools["elicitation_collect_response"].inputSchema["required"] == ["answers"]


def test_slots_schema_rejects_non_string_values():
    schema = {t.name: t for t in tool_definitions()}["elicitation_render_widget"].inputSchema
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"template": "session-contract", "slots": {"project": 3}}, schema)
