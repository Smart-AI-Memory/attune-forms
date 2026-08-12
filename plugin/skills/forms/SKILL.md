---
name: forms
description: "Structured agent-user communication: batch independent questions into ONE validated form, offer recommendations as decision cards, disagree via a pushback card, report progress with a blocked-item picker. Triggers on: use a form, ask as a form, form question, structured ask, decision card, pushback card, progress form."
argument-hint: "<what needs deciding, e.g. 'deployment options' or 'this refactor'>"
---

# Forms — structured agent↔user communication

**IMPORTANT: Start your response by telling the user:**

> **Forms** — Gathering the independent dimensions of this decision as
> one validated form instead of asking one question at a time.

This skill drives the four `attune-forms` MCP tools:

- `elicitation_render_widget` — form dict → interactive HTML (rich surface).
- `elicitation_render_form` — form dict → batched plain-question payloads.
- `elicitation_collect_response` — form + answers → validated response.
- `elicitation_ask` — native MCP elicitation dialog, where supported.

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
`boolean`, `number` (with `minimum`/`maximum`), `date`, plus the three
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

## Choosing a surface

1. **Widget host** (the client renders HTML): call
   `elicitation_render_widget` and show the returned `html`. The form
   posts answers back as a JSON block marked
   `__elicitation_response__` — parse it and validate with
   `elicitation_collect_response`.
2. **Native elicitation host**: call `elicitation_ask`; on
   `action: "unsupported"`, fall back to (3).
3. **Plain conversation**: call `elicitation_render_form` and map each
   batched payload to your host's question tool (or plain prose):
   recommendation-first ordering, `multi_select` → multi-select,
   constructs → single-select with the recommended option first and
   tradeoffs folded into option descriptions.

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
