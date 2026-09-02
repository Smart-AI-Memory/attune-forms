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

## What's new in 0.11.0

- **Project path fields** — text fields can opt into a Browse button with
  host-supplied, project-relative file and folder choices.
- **Searchable, accessible picker** — the widget modal filters paths, supports
  Escape/backdrop closing and focus return, and avoids native-dialog browser
  inconsistencies.
- **Portable fallback** — native and text-only hosts keep ordinary manual path
  entry while server-side validation remains authoritative.

This is the provider-neutral transport layer. Individual agent products still
choose whether to render it inline, open it as a browser artifact, or use the
fallback that matches their advertised capabilities.

## Install

**As a Claude Code plugin** (skill + MCP server, no Python setup):

```bash
claude plugin marketplace add Smart-AI-Memory/attune-forms
claude plugin install attune-forms@attune-forms
```

The plugin teaches the session the forms discipline (the `forms` skill)
and serves six MCP tools — `elicitation_render_form`,
`elicitation_render_widget`, `elicitation_collect_response`,
`elicitation_ask`, `elicitation_render_workspace`, and
`elicitation_collect_workspace_action` — from this package via `uvx`. Decision cards,
pushback cards, progress forms, deliberation cards, triage boards,
confirm gates, ranking lists, and assumption reviews work out of the
box. MCP Apps hosts discover one shared `ui://` resource, render the
rich surface inline, send user actions through the same server-side
validator, and return the validated result to the conversation. Other
hosts degrade to plain questions where possible and render as portable
markdown on text-only hosts — with typed replies
parsed back into the same validator.

**As a Python library:**

```bash
pip install attune-forms
```

Python 3.10+, one runtime dependency (structlog), 880+ tests, CI on
Linux/macOS/Windows. Apache 2.0.

## The grammar

Beyond the plain field types (text, single/multi select, boolean,
number, date, textarea), eight constructs carry conversational meaning:

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
- **Deliberation** — several named voices (reviewers, models,
  teammates) endorse candidate positions; the endorsements render as
  chips so a 2-1 split is visible at a glance, the synthesis pick is a
  badge — never the answer — and the user chairs the choice.
- **Triage** — a ruling per item over a reviewed list (audit findings,
  review comments): a shared disposition vocabulary, stable item ids,
  and an answer that is the full `{item: disposition}` mapping.
- **Confirm** — an approval gate for consequential actions: the
  consequences are enumerated with severity tags, the answer is one of
  exactly two options, and nothing is ever pre-selected — a
  pre-checked approval would defeat the gate, so the validator forbids
  it.
- **Ranking** — the user orders the options, all of them or only the
  top N: the answer is the ordered list itself, a proposed order
  renders visibly as a proposal (never as the answer), and flat
  surfaces expand it to one pick per rank slot that folds back on
  collection.
- **Assumption review** — the agent lists the assumptions it inferred
  from context (each with its source) and the user rules every one
  `accept` / `edit` / `reject`, typing replacement text for an edit;
  the vocabulary is fixed, `suggested` may pre-mark accept only, and
  "infer first" stops being a discipline and becomes an artifact.

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

- **MCP Apps transport** — capable hosts advertise
  `io.modelcontextprotocol/ui`, receive UI metadata only after that
  negotiation, and render the shared `ui://attune-forms/dynamic-surface/v1`
  resource. App submissions call the existing collector tools; only a
  successful validated result is offered back to model context. Hosts
  missing app-to-server or app-to-chat capabilities show an explicit
  manual-continuation state rather than a dead control.
- **Renderers** — `form_to_widget_html` (self-contained interactive
  widget with postback), `form_to_askuserquestion` (batched payloads),
  `form_to_elicitation_schema` (native MCP elicitation), and
  `form_to_markdown` (portable markdown for text-only hosts, with a
  JSON answer skeleton as the reply format).
- **Typed-reply ingestion** — `markdown_to_answers` parses a pasted
  skeleton or line shorthand deterministically (unknown ids and stray
  lines become named problems, never guesses);
  `problems_to_markdown` re-asks exactly the fields that failed.
- **Surface routing** — `select_form_surface` picks widget vs fallback;
  a keyboard-mode opt-out is persisted per project. The form degrades —
  it never breaks. Authority note: in the shipped plugin the router is
  *advisory* — the agent's choice of MCP tool IS the surface decision,
  guided by the skill's prose ladder, and the router runs after the
  fact so telemetry can record agreement. Library consumers routing
  their own calls (as above) are the path where its answer is binding.
- **Validation** — `form_from_dict` refuses malformed definitions;
  `collect_form_response` refuses malformed answers (required fields,
  option membership) with field-level problems.
- **Command workspaces** — `workspace_from_dict` validates a closed,
  non-executable document grammar for intake, preview, execution, and
  receipt views. `workspace_to_widget_html` and
  `workspace_to_markdown` render the same action contract;
  `collect_workspace_action` rejects unknown, stale, or mismatched
  action envelopes. An action may declare `response_fields` from the
  existing form grammar; only the selected action's fields are accepted,
  and every surface returns the same normalized `responses` mapping.
  `workspace_action_contract` provides the immutable projection hosts bind
  into their contract digest. Optional revision/hash/nonce bindings are
  echoed for the host to authorize and consume — the UI never grants
  authority.
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

## Interaction conformance

`run_workspace_conformance` evaluates a command-neutral `WorkspaceFixture`
against one of four capability profiles: `RICH_WIDGET_STANDARD`,
`NATIVE_DIALOG_CONSTRAINED`, `PORTABLE_MARKDOWN`, or `HEADLESS_JSON`.
The report checks the rendered structure and complete action set rather than
screenshots or label substrings:

```python
from attune_forms import (
    RICH_WIDGET_STANDARD,
    ProjectionRenderers,
    WorkspaceFixture,
    run_workspace_conformance,
)

fixture = WorkspaceFixture(
    owner="my-workflow",
    pages=(workspace_view,),
    expected_action_ids=tuple(action.id for action in workspace_view.actions),
    submitted_summary="The review is complete.",
)
report = run_workspace_conformance(
    fixture,
    RICH_WIDGET_STANDARD,
    renderers=ProjectionRenderers(retained=capture_submitted_projection),
    latency_samples=observed_phase_samples,
)
```

The `retained` callback captures the host's actual compacted submitted
projection. The fixture's expected summary alone cannot pass retention.
Latency samples name the cold/warm mode and the exact phase they measure.
`measure_latency` can capture local operations; transport, acknowledgement,
progress, and terminal phases must come from those real boundaries. A missing
phase or an explicitly unavailable receipt remains non-passing. Profiles and
reports describe evidence only—they cannot authorize a workspace action.

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
