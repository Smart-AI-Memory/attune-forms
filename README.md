# attune-forms

Dynamic forms library for AI-agent <-> user communication: a declarative,
surface-agnostic `FormSchema` artifact, renderers for every surface the
agent might be on, and template-driven intake generation.

Extracted from [attune-ai](https://github.com/Smart-AI-Memory/attune-ai)'s
elicitation subsystem (the `elicitation-form-surface` and
`workflow-intake-forms` specs); attune-ai consumes this package.

## What it does

- **One artifact** — `FormSchema` / `FormQuestion` built from plain data
  via `form_from_dict`, with build-time validation.
- **Question types** — text, single/multi select, boolean, number, date,
  textarea, plus the communication-grammar constructs: `decision`
  (recommended option + rationale + per-option tradeoffs), `pushback`
  (structured disagreement), `progress` (status report with a
  blocked-item picker).
- **Renderers** — `form_to_widget_html` (self-contained interactive
  widget with postback), `form_to_askuserquestion` (batched payloads),
  `form_to_elicitation_schema` (native MCP elicitation).
- **Surface routing** — `select_form_surface` picks widget vs fallback;
  keyboard-mode opt-out persisted per project.
- **Validation** — `collect_form_response` validates answers (required +
  option membership) and never silently accepts malformed input.
- **Intake templates** — `FormTemplate` + `FieldSlot` generate a
  workflow's intake form at ask-time from named candidate providers
  (`PROVIDERS`); build-time boundary rules reject invalid templates.
- **Telemetry** — local-only surface-decision log (`form_events`),
  disabled via `DO_NOT_TRACK` or `ATTUNE_FORM_TELEMETRY=0`.

## Install

```bash
pip install attune-forms
```

## Quick start

```python
from attune_forms import form_from_dict, select_form_surface, form_to_widget_html

form = form_from_dict({
    "title": "Security audit scope",
    "fields": [
        {"id": "path", "type": "text_input", "label": "Which path?"},
        {"id": "depth", "type": "single_select", "label": "How deep?",
         "options": ["quick", "standard", "thorough"]},
    ],
})
if select_form_surface(form) == "widget":
    html = form_to_widget_html(form)  # render on your widget surface
```

## Host integration seams

Workflow-bound intake templates need two host hooks:

```python
import attune_forms.intake_template as it

it.WORKFLOW_SCHEMA_RESOLVER = my_schema_resolver   # name -> input schema
it.TEMPLATE_LOADERS.append(my_registration_loader)  # imports template modules
```

## License

Apache 2.0. Copyright 2026 Smart AI Memory.
