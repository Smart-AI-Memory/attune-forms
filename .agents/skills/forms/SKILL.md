---
name: forms
description: "Structured agent-user communication: batch independent questions into ONE validated form, offer recommendations as decision cards, disagree via a pushback card, report progress with a blocked-item picker, present multi-voice positions as a deliberation card, collect per-item rulings with a triage board, gate consequential actions with a confirm card, order options with a ranking list, surface inferred assumptions for accept/edit/reject with an assumption review. Triggers on: use a form, ask as a form, form question, structured ask, decision card, pushback card, progress form, deliberation card, triage board, confirm card, approval gate, ranking, rank these, prioritize, assumption review, check my assumptions, here's what I'm assuming."
argument-hint: "<what needs deciding, e.g. 'deployment options' or 'this refactor'>"
---

# Forms — structured agent↔user communication

**IMPORTANT: Start your response by telling the user:**

> **Forms** — Gathering the independent dimensions of this decision as
> one validated form instead of asking one question at a time.

This skill drives the six `attune-forms` MCP tools:

- `elicitation_render_widget` — form dict → interactive HTML (rich surface).
- `elicitation_render_form` — form dict → batched plain-question payloads.
- `elicitation_collect_response` — form + answers → validated response.
- `elicitation_ask` — native MCP elicitation dialog, where supported.
- `elicitation_render_workspace` — validated workspace view → widget + markdown.
- `elicitation_collect_workspace_action` — view + action envelope → validated action.

Command workspaces compose forms with typed evidence, progress, receipt,
and action blocks. For consequential actions, render a host-generated
revision/hash/nonce binding and validate the returned envelope before
the host authorizes anything. A successful collection proves only that
the action belongs to that rendered view; it never executes the action.

## When to use a multi-field form (the batching rule)

Batch 2–4 fields into **one** form only when ALL hold:

- the fields are **independent dimensions of one decision** the user
  makes together (e.g. scope + depth + output format), AND
- answers **don't branch** on each other (if a field's relevance
  depends on another's answer, stay sequential), AND
- each field is **genuinely open** — a dimension the user already
  specified is omitted, not asked.

**Stay conversational** when only one simple thing is unknown, or when
a form would feel like a bureaucratic intake for a casual ask. And a
user's bare confirmation ("go", "yes") is never a form — don't put a
form in front of a confirm.

## Infer first — the highest-value thing you can do

Before building any form, mine the conversation and context for
answers that already exist. A dimension the user already settled is
omitted or prefilled with `default` — never re-asked cold. A form
where every field was genuinely open beats five fields of which three
were already answered.

## Building the form (data, not code)

A form is a plain dict: `title`, optional `description`, and `fields`.
Each field: `id`, `text` (the question), `type`, and per-type extras.

Types: `text_input`, `textarea`, `single_select`, `multi_select`,
`boolean`, `number` (with `minimum`/`maximum`), `date`, plus the
constructs below. Optional keys: `options`, `default`, `help_text`,
`required` (default true), `max_length`.

```json
{
  "title": "Deployment scope",
  "fields": [
    {"id": "env", "type": "single_select", "text": "Which environment?",
     "options": ["staging", "production"]},
    {"id": "strategy", "type": "single_select", "text": "Rollout strategy?",
     "options": ["all at once", "canary", "blue-green"]},
    {"id": "notes", "type": "textarea", "text": "Anything to watch for?",
     "required": false}
  ]
}
```

## The decision card

A `decision` offers a **recommended** option with a **rationale** and
per-option **tradeoffs**; the user picks one. Use it whenever you hold
a real recommendation — lead with it instead of listing neutral
options.

Extra keys: `recommended` (badged and ordered first; must be in
`options`), `rationale` (the "why"), `option_notes`
(`{option: one-line tradeoff}`).

## The pushback card

A `pushback` is a decision framed as **dissent**: the user's stated
approach is tagged "your approach", your alternative is badged "I'd
suggest instead", and the rationale renders under "Why I'd push back".
Use it when the user's named approach looks weaker than an alternative
you can state concretely. Overruling you is a first-class outcome.

Extra keys: `user_position` (the user's approach; must be in
`options`) plus the decision keys.

## The progress form

A `progress` reports items by status — `done` / `in_flight` /
`blocked` — and offers the **blocked** items as a picker ("which
blocker should we tackle?"). `progress_items` is a list of
`{label, status, detail?}`; the blocked labels must equal `options`.
With nothing blocked, set `options: []` and `required: false` — it
degrades to a pure status display.

## The deliberation card

A `deliberation` presents several **voices'** positions on one choice —
reviewers, models, teammates — and lets the user chair the pick. Each
option carries `endorsements` (`{option: [voice, ...]}`) rendered as
chips, so a 2-1 split and its minority are visible at a glance;
`recommended` badges the **synthesis pick** (a recommendation, never
the answer) and `rationale` renders under "Synthesis". Use it when
distinct sources genuinely disagree — never to dress one opinion as
many.

Extra keys: `endorsements` (required; keys must be in `options`, values
non-empty name lists) plus the decision keys.

## The triage board

A `triage` collects a **ruling per item** over a reviewed list — audit
findings, review comments, backlog candidates. `triage_items` is a list
of `{label, id?, detail?, tag?}`; `dispositions` is the shared ruling
vocabulary (e.g. `["fix now", "ticket", "dismiss"]`); optional
`suggested` (`{item id: disposition}`) pre-selects your proposal,
visibly marked. The answer is `{item id: disposition}` (label is the
fallback key when an item has no `id` — give items stable ids). A
required board needs every item ruled; set `required: false` to allow
partial rulings. On flat surfaces each item becomes its own
single-select (`"<field id>.<item id>"`); pass those answers straight
to `elicitation_collect_response` — they fold back automatically.

## The confirm card

A `confirm` is an approval gate for a **consequential action**: the
question names the action, `consequences` (a non-empty list of
`{label, severity?, detail?}`; conventional severities `low` /
`medium` / `high` / `irreversible`) enumerates exactly what will
happen, and the user answers one of exactly two options (default
`["Approve", "Abort"]`, renameable — always two). **No `default` and
no `recommended` are allowed** — a pre-selected approval defeats the
gate, and the library rejects both.

**The boundary with the "never form a confirm" rule above:** a bare
re-confirmation of something already decided ("go", "yes", "proceed
as planned") stays conversational — that rule stands. The confirm
card is reserved for actions whose consequences *deserve enumeration*
— destructive, costly, or outward-facing steps (a release, a deletion,
a spend, a public post) where "here is exactly what will happen" is
the point. If you have no consequences worth listing, you don't have
a confirm — ask plainly.

## The ranking list

A `ranking` asks the user to **order** the options — all of them, or
only the top N. Use it when the order itself is the decision (what
ships first, which risks matter most); when any subset would do, that
is a `multi_select`, and when one pick would do, a `single_select`.

Extra keys: `top_n` (rank only the top N; omit for a full ordering),
`suggested` (your proposed order as a list — rendered visibly as a
proposal, never taken as the answer). **No `default`** — the library
rejects it; a pre-filled order is `suggested`. The answer is an ordered
list of options: distinct, exactly `top_n` (or all) long. On flat
surfaces the list expands to one single-select per rank slot
(`"<field id>.1"`, `"<field id>.2"`, … each offering every option — a
host question tool can't remove already-picked ones); pass those
answers straight to `elicitation_collect_response`, they fold back and
a repeated option is a named problem. On markdown hosts the reply is a
comma list in order (`field_id: b, a, c`) or one slot per line.

## The assumption review

An `assumption_review` shows the assumptions you **inferred** from
context and lets the user rule each one `accept` / `edit` / `reject`,
typing replacement text for an edit. It is "Infer first" made into an
artifact: instead of silently acting on an inference or re-asking it
cold, you show it, say where it came from, and act on the ruling.

Extra keys: `assumptions` (a list of `{label, id?, detail?, source?}` —
`source` is where you inferred it from: "README §Install", "your
message at 10:02"; give items stable ids), optional `suggested`
(`{item id: "accept"}` — pre-marks accept visibly as your proposal;
**accept only**, never edit or reject on the user's behalf). The
vocabulary is fixed — there is no `dispositions` key, and **no
`default`**; the library rejects both. The answer is `{item id:
"accept" | "reject" | {"edit": "<replacement text>"}}`; an edit
without text is a named problem. On flat surfaces each item becomes a
single-select over the three rulings **paired with** an optional text
question `"<field id>.<item id>.text"` (a host question tool can't
branch); pass everything to `elicitation_collect_response` — the text
is kept only when the ruling is edit, and required then. On markdown
hosts a row is `field_id.item_id: accept`, `…: reject`, or
`…: edit: <replacement text>`.

**The boundary with "Infer first":** a dimension the user already
*settled* is omitted or prefilled — never re-asked, and never put in a
review. The review is for dimensions you *inferred* and are about to
act on. Use it when **two or more** inferences carry real consequences
if wrong; a single safe inference is stated in prose ("assuming Python
3.10+, since pyproject says so") and acted on. An agent that turns
every inference into a review row is the bureaucratizing failure mode
wearing a new construct.

## Choosing a surface

1. **MCP Apps host**: call `elicitation_render_widget` (or
   `elicitation_render_workspace`). After capability negotiation the host
   discovers the linked `ui://attune-forms/dynamic-surface/v1` resource and
   renders it inline. Its actions call the named server-side collector; only
   a validated result is offered back to model context. If the embedded view
   names a missing submission or continuation capability, continue with the
   native or text path below — do not treat the rendered click as authority.
2. **Legacy widget host** (the client renders returned HTML): show the
   returned `html`. The form posts answers back as a JSON block marked
   `__elicitation_response__` — parse it and validate with
   `elicitation_collect_response`.
3. **Native elicitation host**: call `elicitation_ask`; on
   `action: "unsupported"`, fall back to (4).
4. **Plain conversation**: call `elicitation_render_form` and map each
   batched payload to your host's question tool (or plain prose):
   recommendation-first ordering, `multi_select` → multi-select,
   constructs → single-select with the recommended option first and
   tradeoffs folded into option descriptions (a triage board arrives
   pre-expanded as one single-select per item; a ranking as one
   single-select per rank slot; an assumption review as one
   single-select per assumption plus its paired text question).
5. **No widget, no question tool** (text-only hosts): render the form
   with `form_to_markdown` (library) and relay the markdown verbatim.
   It ends with a JSON answer skeleton — the widget's exact postback
   shape — and documents the line shorthand (`field_id: value`,
   `N: value`, `field_id.item_id: disposition` for triage rows,
   `field_id: b, a, c` or `field_id.1: b` for a ranking,
   `field_id.item_id: edit: <text>` for an assumption edit).
   Collect the reply in this order:
   - **Parse first**: run `markdown_to_answers(form, reply)` — it
     deterministically handles a pasted JSON block or shorthand lines
     and returns `(answers, problems)`; it never guesses, so every
     stray line comes back as a named problem.
   - **Free text is YOUR lane**: when the user answered in prose,
     map their words into the skeleton yourself — but treat your
     mapping as a proposal, never a fact. If a value is uncertain,
     re-ask that field instead of guessing.
   - **Validate everything** through `elicitation_collect_response` —
     parser output and your own mappings alike; the validator is the
     only truth. On problems, relay `problems_to_markdown(form,
     problems)` — it re-renders exactly the offending fields as a
     markdown re-ask, never the whole form.

Respect the user's keyboard preference: if they've opted into terse
mode (`ATTUNE_FORMS_KEYBOARD_MODE=1` or `keyboard_mode` in
`attune-forms.config.json`), prefer compact plain questions over rich
widgets.

## Always validate the answers

Every submission — widget postback, elicitation response, or typed
reply — goes through `elicitation_collect_response`. On
`{"success": false, "problems": [...]}`, re-ask ONLY the offending
fields; never silently accept malformed input, and never re-ask what
already validated.
