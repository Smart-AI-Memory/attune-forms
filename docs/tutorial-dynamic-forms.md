<!--
  This repo copy is the verified MASTER of this tutorial: every code
  block — §7 included — was executed against attune-forms 0.6.0 from
  PyPI in a fresh virtualenv on 2026-08-16 (originally verified against
  0.5.0 with §7 against main, 2026-08-16 pre-release). External
  publications (LinkedIn, blog, dev.to) are projections of it — fix
  divergences here first, re-run the blocks, then re-project. Companion
  to communication-grammar-article.md (the concept, published
  2026-08-13) and six-speech-acts-article.md (the 0.5.0 delta).
-->

# Six Constructs, Four Hosts, One Validator: Building a Dynamic Form with attune-forms

*A hands-on walk from an empty dict to a validated round trip — the six constructs the library documents, the surface each one degrades to, and the return path that never guesses.*

Two earlier pieces argued that an AI agent's question should be a typed, validated artifact — a form — and named the constructs that carry conversational meaning on top of one. This one types it in.

The fastest way in is two commands in Claude Code's terminal. The plugin gives you the engine as a skill plus four MCP tools — no Python setup — and the next thing you ask for can arrive as a form:

```
claude plugin marketplace add Smart-AI-Memory/attune-forms
claude plugin install attune-forms@attune-forms
```

This tutorial takes the library path instead, because the point is to show the machinery. By the end you will have built a form that uses every construct in attune-forms — the six those pieces named and the two that 0.6.0 added (§7) — rendered it four ways from the same dict, collected a typed reply from a text-only host, watched the validator refuse a bad answer, and re-asked exactly the field that failed. Everything below runs as written against the published package:

```
pip install attune-forms==0.6.0
```

The library is stdlib plus one runtime dependency; the snippets need nothing else. Where I state a number — bytes, payload counts, line counts — it is the number the code printed when I ran it for this piece.

## 1. The base form in one breath

A form is a plain dict: a title and a list of fields, each with an `id`, a `text` (the question), a `type`, and per-type extras. `form_from_dict` validates the *definition* and refuses a malformed one at build time.

```python
from attune_forms import form_from_dict, FormValidationError

form = form_from_dict({
    "title": "Security audit scope",
    "fields": [
        {"id": "path", "type": "text_input", "text": "Which path?"},
        {"id": "focus", "type": "multi_select", "text": "Focus on?",
         "options": ["secrets", "injection", "deps"]},
        {"id": "depth", "type": "single_select", "text": "How deep?",
         "options": ["quick", "standard", "thorough"], "default": "standard"},
    ],
})

try:
    form_from_dict({"title": "x", "fields": [
        {"id": "depth", "type": "single_select", "text": "How deep?"}]})
except FormValidationError as e:
    print(e.problems)
# ["field[0] type single_select requires non-empty 'options'"]
```

Three independent dimensions of one decision — path, focus, depth — batched into one round trip. That is the whole "batching rule" from the skill text: batch when the fields are independent dimensions of one decision, don't branch on each other, and are genuinely open. A single simple unknown stays a sentence; a user's bare "go" is never a form.

The plain field types are `text_input`, `textarea`, `single_select`, `multi_select`, `boolean`, `number` (with `minimum`/`maximum`), and `date`. They are the substrate. The constructs sit on top.

## 2. The six constructs, one at a time

Each construct is a field type with extra keys and a *conversational move*. The snippets are lifted verbatim from the library's own reference form — `attune_forms.REFERENCE_FORM`, a CI-guarded form with one field per control type — so you can also just import it. I show the answer each field validates to.

**Decision — recommend.** A single-select the agent leads: `recommended` is badged and ordered first, `rationale` says why, `option_notes` puts one tradeoff under every alternative.

```python
{
    "id": "rollout",
    "type": "decision",
    "text": "How should we roll it out?",
    "options": [
        "Ship behind a feature flag",
        "Ship to everyone at once",
        "Hold for the next release",
    ],
    "recommended": "Ship behind a feature flag",
    "rationale": "A flag lets us dark-launch and roll back without a redeploy.",
    "option_notes": {
        "Ship behind a feature flag": "Safest — gated exposure, instant rollback.",
        "Ship to everyone at once": "Fastest, but no kill switch if it regresses.",
        "Hold for the next release": "Zero risk now, but delays the value.",
    },
}
# answer: "Ship behind a feature flag"
```

**Pushback — dissent.** The same shape framed as disagreement: `user_position` is tagged "your approach", `recommended` is the agent's alternative, and overruling it is a first-class outcome.

```python
{
    "id": "branch_strategy",
    "type": "pushback",
    "text": "You proposed a long-lived feature branch.",
    "options": ["Long-lived feature branch", "Short stacked PRs off main"],
    "user_position": "Long-lived feature branch",
    "recommended": "Short stacked PRs off main",
    "rationale": "Long-lived branches drift from main and make review a "
    "big-bang; small stacked PRs stay mergeable and reviewable.",
}
# answer: "Short stacked PRs off main"
```

**Progress — report and unblock.** `progress_items` carry a status each; the blocked ones must equal `options`, because they are the picker.

```python
{
    "id": "blockers",
    "type": "progress",
    "text": "Which blocker should we tackle first?",
    "options": ["Design sign-off", "Staging environment"],
    "progress_items": [
        {"label": "Requirements", "status": "done", "detail": "approved"},
        {"label": "Prototype", "status": "in_flight", "detail": "in review"},
        {"label": "Design sign-off", "status": "blocked", "detail": "awaiting design"},
        {"label": "Staging environment", "status": "blocked", "detail": "infra ticket open"},
    ],
}
# answer: "Design sign-off"
```

The next three landed in 0.5.0.

**Deliberation — chair a split.** Named voices endorse options; `endorsements` maps each option to a non-empty list of names, `recommended` is the synthesis pick (a badge, never the answer), and the user chairs.

```python
{
    "id": "cache_strategy",
    "type": "deliberation",
    "text": "Where should the response cache live?",
    "options": ["In-process LRU", "Redis sidecar", "No cache yet"],
    "endorsements": {
        "In-process LRU": ["claude", "codex"],
        "Redis sidecar": ["antigravity"],
    },
    "recommended": "In-process LRU",
    "rationale": "Two of three seats favor starting in-process; "
    "revisit the sidecar when a second consumer appears.",
}
# answer: "In-process LRU"
```

**Triage — rule per item.** A reviewed list with stable ids, a shared `dispositions` vocabulary (at least two — one word is a rubber stamp, and the validator says so), and an optional `suggested` ruling shown as a proposal. The answer is the whole mapping.

```python
{
    "id": "finding_rulings",
    "type": "triage",
    "text": "Rule each review finding.",
    "triage_items": [
        {"id": "retry-loop", "label": "Unbounded retry loop",
         "tag": "high", "detail": "worker.py:88"},
        {"id": "stale-doc", "label": "Stale docstring", "tag": "low"},
    ],
    "dispositions": ["fix now", "ticket", "dismiss"],
    "suggested": {"retry-loop": "fix now"},
}
# answer: {"retry-loop": "fix now", "stale-doc": "ticket"}
```

**Confirm — consent.** An approval gate: `consequences` are enumerated with an optional severity each, the options default to exactly `["Approve", "Abort"]`, and — this is the construct's whole point — a `default` or a `recommended` is refused at build time, because a pre-selected approval is not a gate.

```python
{
    "id": "flag_flip_gate",
    "type": "confirm",
    "text": "Enable the feature flag for all users now?",
    "consequences": [
        {"label": "Flag flips to 100% rollout", "severity": "high",
         "detail": "reversible via the same flag"},
        {"label": "Announcement email sends", "severity": "irreversible"},
    ],
}
# answer: "Approve"
```

Prove the last claim rather than take it from me:

```python
from attune_forms import form_from_dict, FormValidationError

gate = {"id": "gate", "type": "confirm", "text": "Ship?",
        "consequences": [{"label": "Tag is pushed", "severity": "irreversible"}]}
try:
    form_from_dict({"title": "Release", "fields": [dict(gate, default="Approve")]})
except FormValidationError as e:
    print(e.problems)
# ["field[0] 'default' is not permitted on confirm (D2: no pre-selected approval)"]
```

## 3. Assemble it — or import it

Put the base fields and the constructs in one `fields` list and you have the reference form. The library ships it as data, with a matching set of valid answers, so the rest of this tutorial uses the import. At 0.6.0 it also carries the two §7 constructs, so the count is fifteen:

```python
from attune_forms import REFERENCE_FORM, EXAMPLE_ANSWERS, form_from_dict

form = form_from_dict(REFERENCE_FORM)
print(len(form.questions))                     # 15 — seven plain fields + eight constructs
print([q.type.value for q in form.questions][7:])
# ['decision', 'pushback', 'deliberation', 'triage', 'confirm',
#  'ranking', 'assumption_review', 'progress']
```

## 4. One dict, four hosts

The same `FormSchema` renders on four surfaces. A router picks; you don't hard-code one.

```python
from attune_forms import (
    select_form_surface, form_to_widget_html, form_to_askuserquestion,
    form_to_elicitation_schema, form_to_markdown,
)

print(select_form_surface(form))               # 'widget' — or 'ask' where no widget can render
```

**Widget** — a self-contained interactive HTML form (scoped CSS, a submit script, no external assets) for hosts that render rich content. It posts a sentinel-marked JSON payload back through the host's prompt channel; the agent parses it and validates.

```python
html = form_to_widget_html(form, instance_id="tutorial")   # fixed id → reproducible size
print(len(html))                               # 34574 bytes for the full reference form
```

**Batched plain questions** — for hosts with a question tool but no widget. Constructs degrade to a recommendation-first single-select with tradeoffs folded into the descriptions; a triage board arrives pre-expanded as one single-select per item, keyed `"<board id>.<item id>"`, and folds back on collection.

```python
batches = form_to_askuserquestion(form)        # ≤ 4 questions per call
payloads = [p for batch in batches for p in batch]
print(len(batches), len(payloads))             # 6 23 — the ranking adds one
                                               # pick per rank slot, the
                                               # assumption review one per item
print([p["question_id"] for p in payloads if p["question_id"].startswith("finding_rulings")])
# ['finding_rulings.retry-loop', 'finding_rulings.stale-doc']
```

**Native MCP elicitation** — a flat JSON-Schema object of primitives for hosts that support `elicitation/create`. The confirm becomes a two-value string enum with the consequences folded into its description; nothing carries a default.

```python
schema = form_to_elicitation_schema(form)
print(len(schema["properties"]))               # 21 — triage and assumption review
                                               # flatten to one primitive per item;
                                               # the ranking stays one bounded array
print(schema["properties"]["flag_flip_gate"]["enum"])   # ['Approve', 'Abort']
```

**Portable markdown** — for hosts with neither: a text-only agent CLI, plain chat. Any form renders to markdown, and the render ends with a JSON answer skeleton in exactly the shape the widget would post back — one postback grammar across all four surfaces.

```python
md = form_to_markdown(form)
print(md.count("\n"))                          # 122 lines
print(md[md.rindex("---"):])                   # the reply instructions + the JSON skeleton
```

The tail is the skeleton. Note the confirm is `null` — never prefilled — while the constructs that carry a recommendation or a proposal show it as a visible starting value, the ranking's proposed order included:

```json
{
  "__elicitation_response__": true,
  "title": "Reference form — every control type",
  "answers": {
    "feature_name": null,
    "priority": null,
    "concerns": [],
    "rollout": "Ship behind a feature flag",
    "finding_rulings": {"retry-loop": "fix now", "stale-doc": null},
    "flag_flip_gate": null,
    "rollout_order": ["staging", "canary", "eu-prod"],
    "inferred_scope": {"py-floor": "accept", "host": null,
                       "Tests run in CI on every push": null},
    "blockers": null
  }
}
```

(Abridged: the real skeleton lists every field.)

## 5. The return path

A widget posts structured JSON. A person typing into a terminal posts whatever they type. `markdown_to_answers` reads a reply *deterministically*: a pasted skeleton, or shorthand lines — `field_id: value`, `N: value` by field number, `board.item: disposition` for a triage row, comma lists for a multi-select. It never guesses; every line it cannot place comes back as a named problem.

```python
from attune_forms import markdown_to_answers, collect_form_response, FormValidationError

reply = """2: high
concerns: impl, docs
finding_rulings.retry-loop: fix now
flag_flip_gate: Approve
sounds good to me"""

answers, problems = markdown_to_answers(form, reply)
print(answers)
# {'priority': 'high', 'concerns': ['impl', 'docs'],
#  'finding_rulings.retry-loop': 'fix now', 'flag_flip_gate': 'Approve'}
print(problems)
# ["unparseable line: 'sounds good to me'"]
```

That last line is the design in one row: prose is not silently dropped and not silently mapped. Free-text answers are the *agent's* lane — it may propose a mapping into the skeleton — but the mapping is a proposal, and the validator is the only truth. Which is the next call.

`collect_form_response` is the same validator behind every surface. It refuses malformed answers with a `FormValidationError` whose `.problems` name every failing field, and it applies defaults for missing optional fields:

```python
bad = dict(EXAMPLE_ANSWERS)
bad["priority"] = "urgent"                     # not one of low / medium / high
try:
    collect_form_response(form, bad)
except FormValidationError as e:
    print(e.problems)
# ["'priority' value 'urgent' not in options"]
```

And `problems_to_markdown` closes the loop by re-rendering *only* the fields that failed, with their original numbers so shorthand keeps working:

```python
from attune_forms import problems_to_markdown

try:
    collect_form_response(form, bad)
except FormValidationError as e:
    print(problems_to_markdown(form, e.problems))
```

```
Some answers need another pass:
- 'priority' value 'urgent' not in options

2. **How urgent is it?**
- low
- medium
- high

Reply for just these fields — shorthand works (`field_id: value` or `N: value`).
```

Render → reply → parse → validate → re-ask. On the widget the reply is JSON and the parse step is trivial; on markdown the parse step is the deterministic reader above; on every surface the validate step is the same function. That symmetry is what "one schema, every surface" actually buys you.

## 6. When not to build any of this

The library will happily render a three-field form for a one-word question, and that is the failure mode to watch. The skill text draws two lines worth repeating: stay conversational when only one simple thing is unknown, and never put a form in front of a bare confirmation ("go", "yes"). The confirm construct doesn't cross that line — it is reserved for actions whose consequences deserve enumeration (a release, a deletion, a spend, a public post). If you have no consequences worth listing, you don't have a confirm; ask plainly.

## 7. Two more constructs (0.6.0)

These shipped in 0.6.0 on August 16th — like everything above, the snippets run as written against the released package, and both fields are already in the reference form you imported in §3.

**Ranking — order the options,** all of them or only the top `top_n`. The answer is the ordered list; a `suggested` order renders visibly as a proposal, never as the answer, and `default` is refused. On flat surfaces it expands to one single-select per rank slot (`"<id>.1"`, `"<id>.2"`, …) that folds back; the markdown reply is a comma list in order.

```python
{
    "id": "rollout_order",
    "type": "ranking",
    "text": "Which environments ship first?",
    "options": ["staging", "canary", "eu-prod", "us-prod"],
    "top_n": 3,
    "suggested": ["staging", "canary", "eu-prod"],
}
# answer: ["staging", "canary", "us-prod"]
```

**Assumption review — check what I inferred.** The agent lists the assumptions it drew from context, each with its `source`, and the user rules every one from a fixed vocabulary: `accept`, `reject`, or `{"edit": "<replacement text>"}`. `suggested` may pre-mark accept only; an edit without text is a named problem; on flat surfaces each item pairs with an optional text question for the edit lane.

```python
{
    "id": "inferred_scope",
    "type": "assumption_review",
    "text": "I inferred these from context — rule each one.",
    "assumptions": [
        {"id": "py-floor", "label": "Python 3.10 is the floor",
         "source": "pyproject.toml requires-python"},
        {"id": "host", "label": "Claude Code is the only host",
         "detail": "the plugin manifest names it",
         "source": "plugin/.claude-plugin/marketplace.json"},
        {"label": "Tests run in CI on every push"},
    ],
    "suggested": {"py-floor": "accept"},
}
# answer: {"py-floor": "accept",
#          "host": {"edit": "Claude Code plus any text-only host via markdown"},
#          "Tests run in CI on every push": "reject"}
```

Everything else in this tutorial — the four renderers, the reader, the validator, the re-ask — takes these two without change; that is the point of building constructs as data on one schema.

## Where it runs today

The Claude Code plugin exposes the engine as four MCP tools — render widget, render batched questions, collect and validate, native elicitation — plus the skill that teaches an agent *when* to reach for a form. Text-only hosts get the markdown surface and the reader through the library. Apache 2.0; repo and PyPI links below.

Which host would you want it rendered on next?

---

*Patrick Roebuck builds Smart AI Memory. attune-forms: https://github.com/Smart-AI-Memory/attune-forms — PyPI: https://pypi.org/project/attune-forms/ — the concept: https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse*
