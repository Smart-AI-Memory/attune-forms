"""Contract tests for the shared MCP Apps transport."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from attune_forms.mcp_app import (
    MCP_APP_MIME_TYPE,
    MCP_APP_PROTOCOL_VERSION,
    MCP_APP_RESOURCE_URI,
    MCP_APPS_EXTENSION,
    client_supports_mcp_apps,
    mcp_app_resource,
    mcp_app_result,
    mcp_app_tool_meta,
)


def test_capability_negotiation_is_exact_and_fail_closed() -> None:
    supported = {
        "extensions": {
            MCP_APPS_EXTENSION: {
                "mimeTypes": ["text/plain", MCP_APP_MIME_TYPE],
            }
        }
    }
    assert client_supports_mcp_apps(supported) is True
    assert client_supports_mcp_apps({}) is False
    assert client_supports_mcp_apps({"extensions": {MCP_APPS_EXTENSION: {}}}) is False
    assert (
        client_supports_mcp_apps(
            {"extensions": {MCP_APPS_EXTENSION: {"mimeTypes": MCP_APP_MIME_TYPE}}}
        )
        is False
    )


def test_tool_metadata_uses_the_standard_nested_ui_shape() -> None:
    assert mcp_app_tool_meta() == {
        "ui": {
            "resourceUri": MCP_APP_RESOURCE_URI,
            "visibility": ["model", "app"],
        }
    }
    assert mcp_app_tool_meta(visibility=("app",))["ui"]["visibility"] == ["app"]
    with pytest.raises(ValueError, match="visibility"):
        mcp_app_tool_meta(visibility=("browser",))


def test_collector_descriptor_supports_form_workspace_and_host_state() -> None:
    assert mcp_app_result(
        collect_tool="elicitation_collect_response",
        collect_mode="form",
    ) == {
        "resource_uri": MCP_APP_RESOURCE_URI,
        "collect_tool": "elicitation_collect_response",
        "collect_mode": "form",
    }
    assert mcp_app_result(collect_tool="collect_workspace", collect_mode="workspace")
    assert mcp_app_result(collect_tool="fix_workspace_collect_action", collect_mode="response")
    with pytest.raises(ValueError, match="stable MCP tool"):
        mcp_app_result(collect_tool="bad tool", collect_mode="form")
    with pytest.raises(ValueError, match="collect_mode"):
        mcp_app_result(collect_tool="collect", collect_mode="unknown")


def test_resource_is_self_contained_and_names_every_degraded_state() -> None:
    resource = mcp_app_resource()
    html = resource["text"]
    assert resource["uri"] == MCP_APP_RESOURCE_URI
    assert resource["mime_type"] == MCP_APP_MIME_TYPE
    assert html.startswith("<!doctype html>")
    assert "ui/initialize" in html
    assert f"protocolVersion: '{MCP_APP_PROTOCOL_VERSION}'" in html
    assert "ui/notifications/initialized" in html
    assert "ui/notifications/tool-input" in html
    assert "ui/notifications/tool-result" in html
    assert "tools/call" in html
    assert "ui/update-model-context" in html
    assert "ui/message" in html
    assert "hostCapabilities.updateModelContext" in html
    assert "hostCapabilities.message" in html
    assert html.index("validated.success !== true") < html.index(
        "var continued = await continueValidatedInteraction"
    )
    assert "event.source !== window.parent" in html
    assert "cannot submit MCP App tool calls" in html
    assert "cannot continue automatically; continue in chat" in html
    assert "native or text fallback" in html
    assert "https://" not in html and "http://" not in html
    assert "document.write" not in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_resource_script_parses_as_javascript() -> None:
    html = mcp_app_resource()["text"]
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script is not None
    result = subprocess.run(
        ["node", "--check"],
        input=script.group(1),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_validated_submission_reaches_host_context_and_conversation() -> None:
    html = mcp_app_resource()["text"]
    match = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert match is not None
    harness = f"""
const assert = require('node:assert/strict');
const source = {json.dumps(match.group(1))};
const posted = [];
const listeners = {{}};
const status = {{
  textContent: '',
  tone: '',
  setAttribute: function (name, value) {{ if (name === 'data-tone') this.tone = value; }}
}};
const surface = {{
  innerHTML: '',
  querySelectorAll: function () {{ return []; }}
}};
const parent = {{
  postMessage: function (message) {{
    posted.push(message);
    if (!Object.prototype.hasOwnProperty.call(message, 'id')) return;
    let result = {{}};
    if (message.method === 'ui/initialize') {{
      result = {{
        hostCapabilities: {{
          serverTools: {{}},
          updateModelContext: {{ structuredContent: {{}} }},
          message: {{ text: {{}} }}
        }},
        hostContext: {{ theme: 'light' }}
      }};
    }} else if (message.method === 'tools/call') {{
      result = {{ content: [{{ type: 'text', text: JSON.stringify({{
          success: true,
          responses: {{ choice: 'repair' }},
          response_id: 'receipt-123'
        }}) }}] }};
    }}
    queueMicrotask(function () {{
      listeners.message({{
        source: parent,
        data: {{ jsonrpc: '2.0', id: message.id, result: result }}
      }});
    }});
  }}
}};
global.document = {{
  getElementById: function (id) {{ return id === 'attune-app-status' ? status : surface; }},
  documentElement: {{
    scrollWidth: 640,
    scrollHeight: 480,
    style: {{ colorScheme: '', setProperty: function () {{}} }}
  }},
  createElement: function () {{ return {{ textContent: '', replaceWith: function () {{}} }}; }}
}};
global.window = {{
  parent: parent,
  setTimeout: setTimeout,
  clearTimeout: clearTimeout,
  requestAnimationFrame: function (callback) {{ callback(); }},
  addEventListener: function (name, callback) {{ listeners[name] = callback; }},
  ResizeObserver: null
}};
eval(source);

(async function () {{
  await new Promise(function (resolve) {{ setTimeout(resolve, 0); }});
  listeners.message({{
    source: parent,
    data: {{
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-input',
      params: {{ arguments: {{ form: {{ title: 'Repair' }} }} }}
    }}
  }});
  listeners.message({{
    source: parent,
    data: {{
      jsonrpc: '2.0',
      method: 'ui/notifications/tool-result',
      params: {{
        content: [{{ type: 'text', text: JSON.stringify({{
          success: true,
          html: '',
          mcp_app: {{
            collect_tool: 'elicitation_collect_response',
            collect_mode: 'form'
          }}
        }}) }}]
      }}
    }}
  }});
  await window.sendPrompt(
    'Submitted\\n```json\\n' + JSON.stringify({{
      __elicitation_response__: true,
      answers: {{ choice: 'repair' }},
      instance_id: 'a'.repeat(32)
    }}) + '\\n```'
  );
  const calls = posted.filter(function (item) {{ return item.id; }});
  assert.deepEqual(calls.map(function (item) {{ return item.method; }}), [
    'ui/initialize',
    'tools/call',
    'ui/update-model-context',
    'ui/message'
  ]);
  assert.equal(calls[1].params.arguments.form.title, 'Repair');
  assert.equal(calls[1].params.arguments.instance_id, 'a'.repeat(32));
  assert.equal(
    calls[2].params.structuredContent.attune_submission.result.response_id,
    'receipt-123'
  );
  assert.equal(calls[2].params.content, undefined);
  assert.equal(calls[3].params.role, 'user');
  assert.match(status.textContent, /conversation was notified/);
}})().catch(function (error) {{
  console.error(error.stack || error.message);
  process.exitCode = 1;
}});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_collector_javascript_preserves_the_display_token() -> None:
    """Run the shipped JS argument mapper, not a Python reimplementation."""
    html = mcp_app_resource()["text"]
    start = html.index("    function collectorArguments(")
    end = html.index("\n    async function continueValidatedInteraction", start + 1)
    script = (
        "const assert = require('node:assert/strict');\n"
        'const toolInput = {form: {title: "Repeated"}};\n'
        + html[start:end]
        + '\nconst token = "a".repeat(32);\n'
        + 'const args = collectorArguments({collect_mode: "form"}, {answers: {x: "yes"}, instance_id: token});\n'
        + "assert.equal(args.instance_id, token);\n"
        + 'assert.deepEqual(args.answers, {x: "yes"});\n'
        + 'assert.equal(collectorArguments({collect_mode: "form"}, {}).instance_id, "");\n'
    )
    result = subprocess.run(["node"], input=script, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
