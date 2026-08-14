# attune-forms

Structured agent ↔ user communication for AI coding agents: typed,
validated forms instead of guessing or twenty questions.

Ask an agent for a security audit and it usually either guesses your
intent or interrogates you one question at a time. Both failures share a
root cause: free-form chat is the only channel most agents have. This
library gives agents the other channel — a **communication grammar** of
declarative, validated forms. Independent decisions batch into one
round-trip; malformed questions are refused at build time; malformed
answers are refused at collection time. Nothing is silently accepted in
either direction.

The full argument: ["A Communication Grammar for AI
Agents"](https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse).

## Install

**As a Claude Code plugin** (skill + MCP server, no Python setup):

```bash
claude plugin marketplace add Smart-AI-Memory/attune-forms
claude plugin install attune-forms@attune-forms
```

The plugin teaches the session the forms discipline (the `forms` skill)
and serves four MCP tools — `elicitation_render_form`,
`elicitation_render_widget`, `elicitation_collect_response`,
`elicitation_ask` — from this package via `uvx`. Decision cards,
pushback cards, and progress forms work out of the box; rich HTML
renders where the host supports widgets and degrades to plain questions
everywhere else.

**As a Python library:**

```bash
pip install attune-forms
```

Python 3.10+, one runtime dependency (structlog), 380+ tests, CI on
Linux/macOS/Windows. Apache 2.0.

## The grammar

Beyond the plain field types (text, single/multi select, boolean,
number, date, textarea), three constructs carry conversational meaning:

- **Decision** — the agent proposes: recommended option first, a "why"
  rationale, a one-line tradeoff under every alternative. Validates
  exactly like a single-select; the enrichment is presentation.
- **Pushback** — structured disagreement: your stated approach appears
  as an option tagged "your approach", the agent's alternative is
  badged and ordered first, and overruling the agent is a first-class
  outcome, not a failure.
- **Progress** — a status report (done / in-flight / blocked) whose
  blocked items become a picker: reading the status and unblocking the
  work are the same gesture.

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

## One schema, every surface

- **Renderers** — `form_to_widget_html` (self-contained interactive
  widget with postback), `form_to_askuserquestion` (batched payloads),
  `form_to_elicitation_schema` (native MCP elicitation).
- **Surface routing** — `select_form_surface` picks widget vs fallback;
  a keyboard-mode opt-out is persisted per project. The form degrades —
  it never breaks.
- **Validation** — `form_from_dict` refuses malformed definitions;
  `collect_form_response` refuses malformed answers (required fields,
  option membership) with field-level problems.
- **Intake templates** — `FormTemplate` + `FieldSlot` generate a
  workflow's intake form at ask-time from named candidate providers
  (`PROVIDERS`): tools describe what they need once, and the form
  exists for free.
- **Telemetry** — local-only surface-decision log, disabled via
  `DO_NOT_TRACK=1` or `ATTUNE_FORMS_TELEMETRY=0`. Nothing is ever
  phoned home.

## Host integration seams

Workflow-bound intake templates need two host hooks:

```python
import attune_forms.intake_template as it

it.WORKFLOW_SCHEMA_RESOLVER = my_schema_resolver   # name -> input schema
it.TEMPLATE_LOADERS.append(my_registration_loader)  # imports template modules
```

## Provenance

Extracted from [attune-ai](https://github.com/Smart-AI-Memory/attune-ai)'s
elicitation subsystem, where the grammar was designed and battle-tested;
attune-ai now consumes this package. The grammar's own design decisions
were made through its forms — including the review that killed one of
its proposed features. See
[docs/communication-grammar-article.md](docs/communication-grammar-article.md)
(the verified master of the article) and
[CHANGELOG.md](CHANGELOG.md).

## License

Apache 2.0. Copyright 2026 Smart AI Memory.
