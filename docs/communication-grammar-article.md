# A Communication Grammar for AI Agents

*Why an agent's question should be a typed, validated artifact — and when it shouldn't be one at all.*

Ask an AI coding agent to "do a security audit" and one of two things usually happens. Either it guesses or it interrogates you: one question, your answer, another question, your answer, a third. Five round-trips to establish what a decent intake form would have collected in one.

Both failure modes have the same root cause: free-form chat is the only channel most agents have. Chat is a beautiful instrument for ambiguity, and a terrible one for collecting three independent decisions. We solved this problem decades ago: it's called a form.

For the past few months I've been building that solution into my development workflow, and last week the machinery graduated into a standalone open-source library. This article is about the idea underneath it — what I've come to call a communication grammar — because the idea matters more than the code.

## A question is a data structure

The core move is unglamorous: treat an agent's question as a typed, validated artifact instead of a sentence.

A form is a small declarative schema — fields with types (single-select, multi-select, text, number, date), options, defaults, help text. The agent builds it from plain data; a validator refuses malformed definitions at build time; a second validator refuses malformed answers at collection time (a required field left empty, an answer that isn't one of the options). Nothing is silently accepted, in either direction.

That alone fixes the interrogation problem. Independent dimensions batch into *one* form: a security audit's path + focus + depth is one round-trip, not three. The agent stops guessing because asking got cheap.

## But forms are the boring half

The interesting half is what the grammar calls constructs — question types that carry conversational meaning, not just data shape:

**Decision.** The agent proposes: a recommended option ordered first, a "why" rationale, and a one-line tradeoff under every alternative. You pick. Underneath, it validates exactly like a single-select — the enrichment is presentation, not a new answer type. This is "lead with a recommendation" turned from a prompt-engineering aspiration into a rendered artifact.

**Pushback.** The agent disagrees with you — structurally. Your stated approach appears as an option tagged "your approach"; the agent's alternative is badged "I'd suggest instead" and ordered first; the rationale is headed "why I'd push back." You overrule with one click, and overruling is a first-class outcome, not a failure. An agent that can only agree is a liability; an agent that buries its disagreement in paragraph four isn't much better.

**Progress.** A status report — done, in-flight, blocked — where the blocked items become a picker: "which blocker should I tackle?" The report and the next decision are one artifact. The useful property is that the report can't go stale as prose: the blockers are answerable, so reading the status and unblocking the work are the same gesture.

The discipline that makes this work runs in both directions, and they are not symmetric. When the *agent* needs something settled, it builds a form. When *you* are closing a loop the agent opened, a bare "go" is the whole message — putting a form in front of a confirm is ceremony, and ceremony is how good ideas about structure die.

## The same form, three surfaces

A declarative artifact can render anywhere. The library ships three renderers off one schema: an interactive HTML widget (for hosts that render rich content — selection states, validation errors, a postback the agent parses), a batched plain-question fallback for terminal sessions, and native MCP (Model Context Protocol, the standard agent-host interface) elicitation for hosts that support it. A surface router picks; a keyboard-mode opt-out exists for people who'd rather type. The form degrades — it never breaks.

## A day in the life

Last Tuesday I opened a session with three words: "dynamic forms library."

The agent didn't guess and didn't interrogate. It came back with one scope form (four readings of what those words could mean), then one design form: how should the library be distributed (three options, tradeoffs on each, a recommendation with its rationale), what should it be named, what process tier fits. Two round-trips. By evening the library was extracted, tested, published, and consumed by the project it came from.

The same day, the pushback construct earned its keep in a way I didn't expect. I asked for a docs-regeneration policy change; the agent's pushback form opened with a premise check: the behavior I was objecting to didn't exist — a badly named hook made check-only behavior look like regeneration. It then offered only the genuinely open fork, my position and its alternative side by side. I picked its side. The misnamed hook was renamed within the hour. Without the construct, that exchange is three confused messages and a wrong config change.

And here's the part I keep coming back to: all of that happened in *one* day — and every scoping and design decision in the extraction ran through the grammar being extracted. Dogfooding isn't proof, but it's the most honest test I have.

## What this is, concretely

The library is called attune-forms — Apache 2.0, on PyPI, extracted from my attune-ai workflow harness where the grammar was born and battle-tested. Python 3.10+, one dependency (structlog), 384 tests, CI across three platforms. The template layer can generate a workflow's intake form at ask-time from declared input schemas — so tools describe what they need once, and the form exists for free.

```python
from attune_forms import form_from_dict, select_form_surface

form = form_from_dict({
    "title": "Security audit scope",
    "fields": [
        {"id": "path", "type": "text_input", "label": "Which path?"},
        {"id": "depth", "type": "single_select", "label": "How deep?",
         "options": ["quick", "standard", "thorough"]},
    ],
})
surface = select_form_surface(form)  # "widget" or "ask"
```

## What I'm not claiming

Forms are not conversation's replacement; they're its punctuation. Most agent turns should stay plain prose. The grammar fires when two or more independent decisions need settling, when alternatives carry real tradeoffs, or when the agent should disagree out loud — and it should stay silent for everything else. The failure mode on one side is an agent that guesses; on the other, an agent that bureaucratizes. The grammar is the narrow path between them, and the discipline of *when* is as load-bearing as the shapes themselves.

I also won't claim generality I haven't earned. This has one heavy production consumer today — my own stack. The shapes that survived are the ones that kept earning their place in daily use, and the design arms that didn't earn theirs died in review — my own proposal for a tenure-gated "keyboard mode unlock" among them, killed by the agent's pushback form and my one-click switch to its simpler alternative. The grammar's decision log is full of decisions made through the grammar. If you try it and a construct doesn't earn its place in your stack, that's signal, and I'd genuinely like to hear it.

## Try it today

This isn't a roadmap item — you can run it today. The library is on PyPI (`pip install attune-forms`), and the grammar installs into Claude Code as a plugin without adopting any of my other tooling:

```
claude plugin marketplace add Smart-AI-Memory/attune-forms
claude plugin install attune-forms@attune-forms
```

That gets you the skill and a four-tool MCP server; the first form rendered by a fresh install validated its answers over a cold start, on a machine with none of my stack present. If structured agent↔user communication is a problem you have, the engine is sitting there under an Apache license.

---

*Patrick Roebuck builds Smart AI Memory. The attune-forms library: https://github.com/Smart-AI-Memory/attune-forms — PyPI: https://pypi.org/project/attune-forms/*
