"""Portable MCP Apps transport for Attune forms and workspaces.

The form and workspace renderers remain the presentation source of truth.
This module supplies the host adapter around their trusted HTML output:

* capability negotiation for ``io.modelcontextprotocol/ui``;
* one predeclared ``ui://`` resource shared by every Attune surface;
* a JSON-RPC ``postMessage`` bridge that sends widget submissions back
  through the existing server-side collector tools.

Hosts without MCP Apps ignore the tool metadata and keep receiving the same
meaningful text/structured tool result.  The app also names partial host
support visibly instead of silently degrading a submission path.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MCP_APPS_EXTENSION = "io.modelcontextprotocol/ui"
MCP_APP_MIME_TYPE = "text/html;profile=mcp-app"
MCP_APP_RESOURCE_URI = "ui://attune-forms/dynamic-surface/v1"
MCP_APP_PROTOCOL_VERSION = "2026-01-26"

_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
_COLLECT_MODES = frozenset({"form", "workspace", "response"})


def _as_mapping(value: Any) -> Mapping[str, Any]:
    """Return a mapping view for plain dictionaries or Pydantic models."""
    if isinstance(value, Mapping):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        serialized = dump(by_alias=True)
        if isinstance(serialized, Mapping):
            return serialized
    return {}


def client_supports_mcp_apps(capabilities: Any) -> bool:
    """Whether client capabilities advertise the MCP Apps HTML profile."""
    cap_map = _as_mapping(capabilities)
    extensions = _as_mapping(cap_map.get("extensions"))
    ui = _as_mapping(extensions.get(MCP_APPS_EXTENSION))
    mime_types = ui.get("mimeTypes")
    return isinstance(mime_types, list) and MCP_APP_MIME_TYPE in mime_types


def mcp_app_tool_meta(*, visibility: tuple[str, ...] = ("model", "app")) -> dict[str, Any]:
    """Return standard tool metadata linking to Attune's shared UI resource."""
    if not visibility or any(item not in {"model", "app"} for item in visibility):
        raise ValueError("MCP App visibility must contain only 'model' and/or 'app'")
    return {
        "ui": {
            "resourceUri": MCP_APP_RESOURCE_URI,
            "visibility": list(visibility),
        }
    }


def mcp_app_result(
    *,
    collect_tool: str,
    collect_mode: str,
) -> dict[str, Any]:
    """Describe how the shared app must validate one rendered submission.

    ``form`` collectors receive the original form plus the submitted answers.
    ``workspace`` collectors also receive the original workspace and optional
    binding. ``response`` collectors receive only the full authority-bound
    response, for hosts such as attune-ai that retain canonical state
    server-side. The renderer never authorizes any path; the named server tool
    remains the validation and dispatch boundary.
    """
    if not _TOOL_NAME_RE.fullmatch(collect_tool):
        raise ValueError("MCP App collector must be a stable MCP tool name")
    if collect_mode not in _COLLECT_MODES:
        raise ValueError("MCP App collect_mode must be 'form', 'workspace', or 'response'")
    return {
        "resource_uri": MCP_APP_RESOURCE_URI,
        "collect_tool": collect_tool,
        "collect_mode": collect_mode,
    }


def mcp_app_resource() -> dict[str, Any]:
    """Return the predeclared MCP Apps resource definition and HTML content."""
    return {
        "uri": MCP_APP_RESOURCE_URI,
        "name": "attune_dynamic_surface",
        "description": "Interactive Attune form or command workspace",
        "mime_type": MCP_APP_MIME_TYPE,
        "text": _MCP_APP_HTML,
        "meta": {"ui": {"prefersBorder": True}},
    }


_MCP_APP_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Attune dynamic surface</title>
  <style>
    :root { color-scheme: light dark; }
    html, body { margin: 0; padding: 0; }
    body {
      background: var(--color-background-primary, transparent);
      color: var(--color-text-primary, CanvasText);
      font-family: var(--font-sans, ui-sans-serif, system-ui, sans-serif);
    }
    #attune-app-status {
      border: 1px solid var(--color-border-secondary, #9ca3af);
      border-radius: var(--border-radius-md, 8px);
      color: var(--color-text-secondary, inherit);
      font-size: var(--font-text-sm-size, 0.875rem);
      margin: 8px;
      padding: 8px 10px;
    }
    #attune-app-status[data-tone="success"] {
      border-color: var(--color-border-success, #16a34a);
      color: var(--color-text-success, #166534);
    }
    #attune-app-status[data-tone="warning"] {
      border-color: var(--color-border-warning, #d97706);
      color: var(--color-text-warning, #92400e);
    }
    #attune-app-status[data-tone="danger"] {
      border-color: var(--color-border-danger, #dc2626);
      color: var(--color-text-danger, #991b1b);
    }
    #attune-app-surface { min-height: 48px; }
  </style>
</head>
<body>
  <div id="attune-app-status" role="status" aria-live="polite">
    Connecting the interactive surface…
  </div>
  <main id="attune-app-surface" aria-live="polite"></main>
  <script>
  (function () {
    'use strict';
    var nextId = 1;
    var pending = new Map();
    var toolInput = null;
    var toolResult = null;
    var hostCapabilities = {};
    var status = document.getElementById('attune-app-status');
    var surface = document.getElementById('attune-app-surface');

    function setStatus(text, tone) {
      status.textContent = text;
      status.setAttribute('data-tone', tone || 'neutral');
      notifySize();
    }

    function post(message) {
      window.parent.postMessage(message, '*');
    }

    function request(method, params) {
      var id = nextId++;
      post({ jsonrpc: '2.0', id: id, method: method, params: params || {} });
      return new Promise(function (resolve, reject) {
        var timer = window.setTimeout(function () {
          pending.delete(id);
          reject(new Error(method + ' timed out'));
        }, 30000);
        pending.set(id, { resolve: resolve, reject: reject, timer: timer });
      });
    }

    function notify(method, params) {
      post({ jsonrpc: '2.0', method: method, params: params || {} });
    }

    function respond(id, result) {
      post({ jsonrpc: '2.0', id: id, result: result || {} });
    }

    function notifySize() {
      window.requestAnimationFrame(function () {
        notify('ui/notifications/size-changed', {
          width: document.documentElement.scrollWidth,
          height: document.documentElement.scrollHeight
        });
      });
    }

    function applyHostContext(context) {
      if (!context || typeof context !== 'object') return;
      if (context.theme === 'dark' || context.theme === 'light') {
        document.documentElement.style.colorScheme = context.theme;
      }
      var variables = context.styles && context.styles.variables;
      if (variables && typeof variables === 'object') {
        Object.keys(variables).forEach(function (name) {
          if (name.indexOf('--') === 0 && typeof variables[name] === 'string') {
            document.documentElement.style.setProperty(name, variables[name]);
          }
        });
      }
    }

    function structured(result) {
      var value = result && result.structuredContent;
      if (value && typeof value.result === 'object') value = value.result;
      if (value && typeof value === 'object') return value;
      var blocks = result && result.content;
      if (!Array.isArray(blocks)) return null;
      for (var i = 0; i < blocks.length; i += 1) {
        if (!blocks[i] || blocks[i].type !== 'text' || typeof blocks[i].text !== 'string') {
          continue;
        }
        try {
          value = JSON.parse(blocks[i].text);
          if (value && typeof value.result === 'object') value = value.result;
          if (value && typeof value === 'object') return value;
        } catch (error) {
          // Human-readable text remains the host/model fallback; only exact
          // JSON can become interactive state.
        }
      }
      return null;
    }

    function rememberButtonLabels() {
      surface.querySelectorAll('button').forEach(function (button) {
        button.setAttribute('data-attune-original-label', button.textContent || 'Submit');
      });
    }

    function unlockButtons() {
      surface.querySelectorAll('button[data-attune-original-label]').forEach(function (button) {
        button.disabled = false;
        button.textContent = button.getAttribute('data-attune-original-label');
      });
    }

    function installTrustedHtml(html) {
      surface.innerHTML = html;
      rememberButtonLabels();
      surface.querySelectorAll('script').forEach(function (oldScript) {
        var script = document.createElement('script');
        script.textContent = oldScript.textContent;
        oldScript.replaceWith(script);
      });
      notifySize();
    }

    function parseSubmission(text) {
      if (typeof text !== 'string') throw new Error('Widget submission was not text');
      var match = text.match(/```json\s*([\s\S]*?)\s*```/);
      if (!match) throw new Error('Widget submission omitted its JSON envelope');
      var payload = JSON.parse(match[1]);
      if (!payload || payload.__elicitation_response__ !== true) {
        throw new Error('Widget submission omitted the response marker');
      }
      return payload;
    }

    function collectorArguments(descriptor, payload) {
      if (descriptor.collect_mode === 'form') {
        if (!toolInput || !toolInput.form) {
          throw new Error('Host did not provide the original form input');
        }
        return { form: toolInput.form, answers: payload.answers || {},
          instance_id: payload.instance_id || "" };
      }
      if (descriptor.collect_mode === 'workspace') {
        if (!toolInput || !toolInput.workspace) {
          throw new Error('Host did not provide the original workspace input');
        }
        var args = { workspace: toolInput.workspace, response: payload };
        if (toolInput.binding) args.binding = toolInput.binding;
        return args;
      }
      if (descriptor.collect_mode === 'response') return { response: payload };
      throw new Error('Unknown MCP App collector mode');
    }

    async function continueValidatedInteraction(descriptor, validated) {
      var receipt = validated.response_id ? ' Receipt: ' + validated.response_id + '.' : '';
      var summary = 'Attune interaction validated by ' + descriptor.collect_tool + '.' +
        receipt + ' Continue from the validated server result.';
      var contextUpdated = false;
      var messageSent = false;
      var updateCapabilities = hostCapabilities.updateModelContext || {};
      var messageCapabilities = hostCapabilities.message || {};
      var canSendMessage = Boolean(messageCapabilities.text);
      var canSendStructuredContext = Boolean(updateCapabilities.structuredContent);
      var canSendTextContext = Boolean(updateCapabilities.text) && !canSendMessage;

      if (canSendStructuredContext || canSendTextContext) {
        try {
          var context = {};
          if (canSendTextContext) {
            context.content = [{ type: 'text', text: summary }];
          }
          if (canSendStructuredContext) {
            context.structuredContent = {
              attune_submission: {
                collector: descriptor.collect_tool,
                result: validated
              }
            };
          }
          await request('ui/update-model-context', context);
          contextUpdated = true;
        } catch (error) {
          // Validation already succeeded. A denied context update must not
          // rewrite that authority decision or hide the manual continuation.
        }
      }

      if (canSendMessage) {
        try {
          await request('ui/message', {
            role: 'user',
            content: [{ type: 'text', text: summary }]
          });
          messageSent = true;
        } catch (error) {
          // Some hosts require separate consent for app-originated messages.
        }
      }
      return { contextUpdated: contextUpdated, messageSent: messageSent };
    }

    async function submitThroughCollector(text) {
      var rendered = structured(toolResult);
      var descriptor = rendered && rendered.mcp_app;
      if (!descriptor || typeof descriptor.collect_tool !== 'string') {
        setStatus('This result has no validated interactive reply path. Use the text fallback.', 'warning');
        unlockButtons();
        return;
      }
      if (!hostCapabilities.serverTools) {
        setStatus('Interactive view rendered, but this host cannot submit MCP App tool calls. Use the native or text fallback.', 'warning');
        unlockButtons();
        return;
      }
      try {
        var payload = parseSubmission(text);
        var result = await request('tools/call', {
          name: descriptor.collect_tool,
          arguments: collectorArguments(descriptor, payload)
        });
        var validated = structured(result);
        if (!validated || validated.success !== true) {
          var problems = validated && Array.isArray(validated.problems)
            ? validated.problems.join('; ') : 'The collector rejected the submission.';
          setStatus(problems, 'danger');
          unlockButtons();
          return;
        }
        var receipt = validated.response_id ? ' Receipt: ' + validated.response_id + '.' : '';
        setStatus('Submitted and validated through ' + descriptor.collect_tool + '.' + receipt +
          ' Connecting the validated result to the conversation…', 'success');
        var continued = await continueValidatedInteraction(descriptor, validated);
        if (continued.messageSent) {
          setStatus('Submitted and validated through ' + descriptor.collect_tool + '.' + receipt +
            ' The conversation was notified.', 'success');
        } else if (continued.contextUpdated) {
          setStatus('Submitted and validated through ' + descriptor.collect_tool + '.' + receipt +
            ' Context is ready; continue in chat.', 'success');
        } else {
          setStatus('Submitted and validated through ' + descriptor.collect_tool + '.' + receipt +
            ' This host cannot continue automatically; continue in chat.', 'warning');
        }
      } catch (error) {
        setStatus('Submission failed validation: ' + error.message, 'danger');
        unlockButtons();
      }
    }

    window.sendPrompt = submitThroughCollector;

    function renderToolResult(params) {
      toolResult = params;
      var rendered = structured(params);
      if (!rendered || rendered.success !== true || typeof rendered.html !== 'string') {
        setStatus('The interactive result was unavailable. The tool\'s text result remains usable.', 'warning');
        return;
      }
      installTrustedHtml(rendered.html);
      if (hostCapabilities.serverTools) {
        setStatus('Interactive surface connected. Submissions are validated by the server.', 'success');
      } else {
        setStatus('Interactive surface is read-only in this host; use the native or text fallback to submit.', 'warning');
      }
    }

    window.addEventListener('message', function (event) {
      if (event.source !== window.parent) return;
      var message = event.data;
      if (!message || message.jsonrpc !== '2.0') return;
      if (Object.prototype.hasOwnProperty.call(message, 'id') && !message.method) {
        var wait = pending.get(message.id);
        if (!wait) return;
        window.clearTimeout(wait.timer);
        pending.delete(message.id);
        if (message.error) wait.reject(new Error(message.error.message || 'Host request failed'));
        else wait.resolve(message.result || {});
        return;
      }
      if (message.method === 'ui/notifications/tool-input') {
        toolInput = message.params && message.params.arguments || {};
      } else if (message.method === 'ui/notifications/tool-result') {
        renderToolResult(message.params || {});
      } else if (message.method === 'ui/notifications/host-context-changed') {
        applyHostContext(message.params || {});
      } else if (message.method === 'ui/notifications/tool-cancelled') {
        setStatus('The tool call was cancelled. No submission was accepted.', 'warning');
      } else if (message.method === 'ui/resource-teardown' && message.id !== undefined) {
        respond(message.id, {});
      }
    });

    async function initialize() {
      try {
        var result = await request('ui/initialize', {
          protocolVersion: '2026-01-26',
          appInfo: { name: 'attune-forms', version: '1.0.0' },
          appCapabilities: { availableDisplayModes: ['inline', 'fullscreen'] }
        });
        hostCapabilities = result.hostCapabilities || {};
        applyHostContext(result.hostContext || {});
        notify('ui/notifications/initialized', {});
        setStatus('Connected. Waiting for the tool result…', 'neutral');
      } catch (error) {
        setStatus('Embedded UI initialization failed. Use the tool\'s native or text fallback.', 'danger');
      }
    }

    initialize();
    if (window.ResizeObserver) new ResizeObserver(notifySize).observe(document.body);
  }());
  </script>
</body>
</html>"""


__all__ = [
    "MCP_APPS_EXTENSION",
    "MCP_APP_MIME_TYPE",
    "MCP_APP_PROTOCOL_VERSION",
    "MCP_APP_RESOURCE_URI",
    "client_supports_mcp_apps",
    "mcp_app_resource",
    "mcp_app_result",
    "mcp_app_tool_meta",
]
