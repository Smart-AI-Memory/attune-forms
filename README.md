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

## What's new in 0.17.0

- **The `AskUserQuestion` profile declares the multi-select escaping it
  was measured to have, which is none.** It had claimed JSON-quoting the
  host does not perform: a live trial offering `red, green` and `blue`
  returned `red, green,blue` — a bare comma join indistinguishable from
  three atoms — and `say "hi"` / `back\slash` came back raw. Labels
  containing the delimiter or a quote were already refused and still
  are, but now **permanently** rather than pending evidence, and the
  refusal says which case it is. Evidence:
  `docs/probes/host-question-escaping-2026-09-08.md`.

  Consumers pinning the profile's facet digest should re-pin; a
  downstream that characterizes this host's codec should read the probe
  before writing its own receipt.

## What's new in 0.16.0

- **The host-question line is reachable end to end.**
  `attune_forms.host_question_adapter` decodes a raw reply from a host's
  own question control back to typed answers through the bindings AF-2
  retains, and `elicitation_render_form` / `elicitation_collect_response`
  now carry it: `host_question` out, `host_response` back, with a bounded
  re-ask (`next_host_question`, `next_attempt`, `answered_so_far`) and
  `cancelled: true` for a dismissed prompt. `batches` still ships and is
  deprecated.
- **The public surface is tiered.** 46 names are stable, 91 provisional,
  2 deprecated — a promise you can rely on instead of 139 names promised
  equally. `attune_forms.stability` records it and a test fails when a new
  export carries no tier. See [`docs/stability.md`](docs/stability.md).
- **Behavior changes to promised surface can't land silently.** A checked-in
  record pins what the stable surface *does*, so a change arrives as a
  readable diff rather than a flipped hash — and it digests the contract,
  not the paint: a CSS change provably does not move it.
- **First deprecations.** `form_to_askuserquestion` and `is_trivial_form`
  now warn, naming their replacements; removal no earlier than 0.18.0.
- **A running server can say which version it is.** The MCP handshake
  reported the SDK's version under this package's name; it now reports its
  own. Pinning is documented for every install path.

## What's new in 0.15.0

- **Host-question profile facet** — `InteractionProfile.host_question`
  describes a host's built-in question control as data: question, option
  and header limits, multi-select, the reserved Other label and where free
  text arrives, cancellation, validation feedback with a finite attempt cap
  and deadline, closed text normalizations, the raw multi-select response
  encoding, the recommended-label suffix and the host's unanswered marker.
  `CLAUDE_ASKUSERQUESTION` is the installed profile for Claude Code's
  `AskUserQuestion`, from a live desktop trial; `installed_profile(id)`
  looks profiles up.
- **Pure admissibility and renderer** — `host_question_admissibility(form,
  profile)` says before any render whether a form fits the control without
  truncation or ambiguity, naming every reason it does not;
  `form_to_host_question(form, profile)` returns a frozen
  `HostQuestionBatch`: the host-visible payload plus immutable
  `QuestionAnswerBinding`s a server adapter retains to map raw answers back
  to option ids. No raw-host decoder ships; the consuming adapter owns
  correlation, cancellation, feedback and receipts.
- **Route-active registry target** — `form.host_question` sits beside the
  unchanged compatibility-only `form.askuserquestion`; a route-active
  target must resolve to an installed profile carrying the facet;
  `render_fixture()` and `scripts/af2_clean_wheel_probe.py` execute the
  canonical host-question fixture from a wheel.
- **Host-native router default** — `select_form_surface` now returns
  `"ask"` for every form the installed host profile admits and `"widget"`
  only for forms it cannot carry (number/date/textarea, over-cap questions
  or options, a ranking, an uncorrelatable duplicate question).

This minor adds the host-question line (attune-ai host-surface-parity
AF-2, D15–D17); everything from 0.14 remains available unchanged.

## What's new in 0.14.0

- **Renderer registry and no-escape sweep** — `RENDERER_REGISTRY` is the
  public inventory of every production projection of a form or workspace
  view (RICH, PORTABLE, HEADLESS, and the legacy AskUserQuestion renderer as
  a compatibility-only host-native target with a pinned contract id and
  shape digest). `sweep_production_renderers()` proves no projection-shaped
  callable escapes it; unresolved annotations fail closed.
- **Production HEADLESS workspace projection** —
  `workspace_to_headless(view, binding)` returns one deterministic JSON-safe
  mapping: the complete view, the full form schema when present, the
  binding, and the response contract a host posts back through
  `collect_workspace_action`. Never an action-id list.
- **Digests and shipped fixtures** — `record_digest`, `registry_digest`,
  `implementation_digest` and `canonical_fixtures` let a consuming gate lock
  a released artifact and re-execute every record's fixture from the wheel.

This minor adds the registry line (attune-ai host-surface-parity AF-1);
everything from 0.13 remains available unchanged.

## What's new in 0.13.0

- **Templates cast server-side** — every form-taking MCP tool
  (`elicitation_render_form`, `elicitation_render_widget`,
  `elicitation_collect_response`, `elicitation_ask`) takes `template` +
  `slots` in place of `form`. The server loads the stored template, fills the
  slots, validates, and renders in one call, so the form definition never
  transits the agent's context. Template-cast collections carry the template
  name as `template_id`.
- **Authoring preview** — `python -m attune_forms.preview --open` (or
  `attune-forms-preview`) renders every stored template through the
  production widget renderer into one standalone page, light and dark, with
  the posted payload shown on submit. Edit a template, reload, see what users
  see. Preview casts never count toward form telemetry.
- **Cast-every-template gate** — stored templates carry `example_slots`, and
  a drift test casts each one and validates the result, so no template ships
  uncastable.

- **Correlated display and workspace acceptance telemetry** (0.12.3) — each
  display carries its own instance token through submission; separate
  render/acceptance events let hosts measure validated transitions.
- **Visible consequential submits and action-scoped workspace responses**
  (0.12.x) — inline two-click confirmation, one action collecting a validated
  response mapping across widget, Markdown, headless, and MCP stdio surfaces.
- **Interaction conformance evidence** — the packaged harness checks structural
  DOM, keyboard traversal, constrained viewports, projection parity, submitted
  state, and separately attributed cold/warm latency phases.

This minor adds the template-bound form path; everything from the 0.12 line
remains available unchanged.

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
`elicitation_collect_workspace_action` — from this package via `uvx`. Every
form-taking tool also takes `template` + `slots`: a stored template is cast,
validated, and rendered server-side in one call, so the form never transits
the agent's context. Decision cards,
pushback cards, progress forms, deliberation cards, triage boards,
confirm gates, ranking lists, and assumption reviews work out of the
box. MCP Apps hosts discover one shared `ui://` resource, render the
rich surface inline, send user actions through the same server-side
validator, and return the validated result to the conversation. Other
hosts degrade to plain questions where possible and render as portable
markdown on text-only hosts — with typed replies
parsed back into the same validator.

**In Codex** (CLI or the desktop app) — register the same MCP server,
then install the skill so the session learns the forms discipline:

```bash
codex mcp add attune-forms -- uvx --from 'attune-forms[mcp]' attune-forms-mcp
mkdir -p ~/.codex/skills/forms && curl -fsSL https://raw.githubusercontent.com/Smart-AI-Memory/attune-forms/main/plugin/skills/forms/SKILL.md -o ~/.codex/skills/forms/SKILL.md
```

**In any other MCP client** (Antigravity, Gemini CLI, Cursor, …) — add
the server to the client's MCP config. This JSON is the plugin's own
`.mcp.json`, verbatim:

```json
{"mcpServers": {"attune-forms": {"command": "uvx", "args": ["--from", "attune-forms[mcp]", "attune-forms-mcp"]}}}
```

Agents that read the `.agents/skills/` convention (Antigravity, Codex
inside a checkout) find the same skill at `.agents/skills/forms/SKILL.md`
— a byte-for-byte mirror of the plugin skill, drift-guarded. Every host
gets the same six tools and the same validator; only the surface tier
differs (rich `ui://` where the host renders MCP Apps, plain questions or
portable markdown elsewhere).

**As a Python library:**

```bash
pip install attune-forms
```

Python 3.10+, one runtime dependency (structlog), 1,400+ tests, CI on
Linux/macOS/Windows. Apache 2.0.

### Pinning a version

Every install line above resolves the **newest** release, and the package
has no feature flags, so a new version takes effect as soon as it is
resolved. That is deliberate — one step from install to working — but it
means a behavior change reaches every host at once. Pin when you need a
version to hold still.

The constraint goes inside the `--from` spec, not after the entry point:

```bash
pip install 'attune-forms==0.17.0'
uvx --from 'attune-forms[mcp]==0.17.0' attune-forms-mcp
codex mcp add attune-forms -- uvx --from 'attune-forms[mcp]==0.17.0' attune-forms-mcp
```

```json
{"mcpServers": {"attune-forms": {"command": "uvx", "args": ["--from", "attune-forms[mcp]==0.17.0", "attune-forms-mcp"]}}}
```

**The Claude Code plugin cannot be pinned durably.** Its `.mcp.json`
lives in a version-keyed cache directory —
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/.mcp.json` — and
an update installs a *new* version alongside the old one, with its own
pristine file. An edit you made is not overwritten; it is **orphaned** in
the previous version's directory, which nothing reads any more. You would
have to redo it after every update, and the stale file left behind looks
live. To hold a version, take the server and the skill separately instead
of installing the plugin — register the pinned server yourself and copy
the skill from the repository, exactly as the Codex path above does:

```bash
claude mcp add attune-forms -- uvx --from 'attune-forms[mcp]==0.17.0' attune-forms-mcp
```

Pinning is the supported way to hold behavior still. `attune-forms`
follows SemVer and tiers its public surface (see
[`docs/stability.md`](docs/stability.md)): stable names change only
through a deprecation cycle, while provisional names may change in any
minor release.

### Which version am I running?

```bash
python -c "import attune_forms; print(attune_forms.__version__)"
```

Over MCP, the server reports it in the `initialize` handshake as
`serverInfo.version`. **Before 0.16.0 that field carried the MCP SDK's
version rather than this package's** — so a host showing something like
`1.30.0` under the `attune-forms` name is running a release older than
0.16.0, and cannot tell you which one. Several versions can sit on one
machine at once (a `pip` install, a `uvx` cache entry per resolved
version), so check the one your host actually launched rather than the
one on your `PATH`.

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
    html = form_to_widget_html(form)  # the host control cannot carry this form
```

The host's own question control is the default: `select_form_surface`
returns `"ask"` for every form the installed host-question profile
admits (`host_question_admissibility`), and `form_to_host_question`
renders that batch for a server adapter with the answer bindings it needs
to map raw host answers back to option ids.

## One schema, every surface

- **MCP Apps transport** — capable hosts advertise
  `io.modelcontextprotocol/ui`, receive UI metadata only after that
  negotiation, and render the shared `ui://attune-forms/dynamic-surface/v1`
  resource. App submissions call the existing collector tools; only a
  successful validated result is offered back to model context. Hosts
  missing app-to-server or app-to-chat capabilities show an explicit
  manual-continuation state rather than a dead control.
- **Renderers** — `form_to_widget_html` (self-contained interactive
  widget with postback), `form_to_host_question` (one host question
  batch with retained answer bindings, for the installed host profile),
  `form_to_askuserquestion` (legacy batched payloads),
  `form_to_elicitation_schema` (native MCP elicitation), and
  `form_to_markdown` (portable markdown for text-only hosts, with a
  JSON answer skeleton as the reply format).
- **Typed-reply ingestion** — `markdown_to_answers` parses a pasted
  skeleton or line shorthand deterministically (unknown ids and stray
  lines become named problems, never guesses);
  `problems_to_markdown` re-asks exactly the fields that failed.
- **Surface routing** — `select_form_surface` picks the host's native
  control for every form its profile admits and the widget only for
  forms it cannot carry (number/date/textarea, over-cap questions or
  options, a ranking); a keyboard-mode opt-out is persisted per project.
  The form degrades — it never breaks. Authority note: in the shipped plugin the router is
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
- **Authoring preview** — `python -m attune_forms.preview --open` renders
  every stored template (cast with its `example_slots`) through the
  production widget renderer into one standalone page, light and dark,
  with the posted payload shown on submit. Edit a template, reload, see
  what users see.
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

## Renderer registry

`RENDERER_REGISTRY` names every production projection of a form or a
workspace view — RICH, PORTABLE, HEADLESS, and any host-native target —
and `sweep_production_renderers()` proves nothing escapes it: every
callable that takes a `FormSchema` or `WorkspaceView` and returns one of
the closed `projection_output_types` must be exactly one registry
target, exported, or on the small rationale-bearing allowlist.
`workspace_to_headless(view, binding)` is the workspace family's
production HEADLESS projection: the complete view plus the response
contract a host posts back through `collect_workspace_action`.
`record_digest`, `registry_digest` and `implementation_digest` let a
consuming gate lock a released artifact; `canonical_fixtures` ships the
fixtures every record executes.

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
