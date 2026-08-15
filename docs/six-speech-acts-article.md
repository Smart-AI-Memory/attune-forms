<!--
  This repo copy is the verified MASTER of this article: its claims are
  checked against the code in this repository (attune-forms 0.5.0).
  External publications (LinkedIn, blog) are projections of it — fix
  divergences here first. Companion to communication-grammar-article.md
  (published 2026-08-13); this piece carries the delta since.
-->

# Six Speech Acts: What a Communication Grammar Adds to Agent Chat

*Recommend, dissent, report, deliberate, adjudicate, consent — the half of the conversation chat can't carry, and what changed when the grammar grew.*

Earlier this month I published [an argument](https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse) that an AI agent's question should be a typed, validated artifact rather than a sentence: independent decisions batch into one form, malformed questions are refused at build time, malformed answers at collection time, and forms are conversation's punctuation, not its replacement. That article described three constructs — decision, pushback, progress — on three rendering surfaces. It was accurate the day it went out.

It's now out of date, and I'd rather say what changed than quietly edit it. The library underneath, attune-forms, shipped 0.5.0 on August 14th. The changelog's own summary: the grammar grew *from three constructs on three surfaces to six constructs on four*, every one with a validated round trip. This piece is about the three new constructs, the fourth surface, and the part I under-weighted the first time — the return path.

## Six moves, not six widgets

The framing that clarified the design for me: each construct is a *speech act* — a move an agent makes when it needs something settled — and the point of typing it is that the move's guarantees stop depending on how the prose came out.

**Recommend (decision).** The agent proposes: recommended option first, a rationale, a one-line tradeoff under every alternative. Validates as a single-select. Unchanged since the first article.

**Dissent (pushback).** The agent disagrees, structurally: your approach appears as an option tagged as yours, the agent's alternative is badged and ordered first, the rationale is headed "why I'd push back," and overruling is a first-class outcome. Unchanged — and still the construct that has earned its keep most often. The most recent case: the agent recommended a React-based rendering lane for the library; I overruled it from the pushback card and deferred React until a real React host exists. One click, on the record.

**Report (progress).** Done / in-flight / blocked, where the blocked items are a picker. Unchanged.

**Deliberate (deliberation) — new.** Several named voices — reviewers, models, teammates — endorse candidate positions. The endorsements render as chips per option, so a 2-1 split and its minority are visible at a glance; a synthesis pick is a badge, never the answer; the human chairs. Two rules live in the validator, not in a style guide: every endorsement list must be non-empty (an option can't be "endorsed by nobody"), and the endorsements must map onto the actual options. The skill text carries the third rule, which no validator can enforce: never dress one opinion as many. The construct exists to make disagreement legible, not to manufacture it.

**Adjudicate (triage) — new.** A ruling per item over a reviewed list — audit findings, review comments, backlog candidates. Items carry stable ids; the ruling vocabulary is shared across the board (`fix now` / `ticket` / `dismiss`, or whatever the author names); the answer is the whole `{item: disposition}` mapping, not a summary of it. The validator refuses a one-word vocabulary — a board where the only ruling is "accept" is a rubber stamp, and the code comment says so — and it refuses duplicate item keys, because a ruling that can't be attributed to exactly one item is not a ruling. On flat surfaces the board expands to one question per item and folds back into the mapping on collection; the caller never sees the expansion.

**Consent (confirm) — new.** An approval gate for a consequential action: the question names the action, a `consequences` list enumerates exactly what will happen, each line optionally tagged with a severity (low / medium / high / irreversible), and the answer is one of exactly two options. Here the validator is the whole idea. A confirm with no consequences is rejected — if there's nothing worth listing, ask plainly. A confirm with three options is rejected — it's a gate, not a menu. And a confirm with a `default` or a `recommended` is rejected outright, because a pre-selected approval defeats the gate. That last rule was ratified in the design review with the tradeoff stated out loud: a grammar built around leading with a recommendation was deliberately shipping one construct that refuses to carry one. It was, and it should.

The confirm construct's own pull request was gated by a live confirm card — consequences enumerated, two options, nothing pre-selected — the same afternoon it was built. I mention it because "the grammar's decisions are made through the grammar" was a claim in the first article, and this is the smallest concrete instance of it since.

## Both directions, still not symmetric

The first article drew a line I still hold: when the *agent* needs something settled, it builds a form; when *you* are closing a loop the agent opened, a bare "go" is the whole message, and putting a form in front of a confirm is ceremony.

The confirm construct looks like it crosses that line. It doesn't, and the boundary is worth stating precisely because it's easy to get wrong. A bare re-confirmation of something already decided — "go", "yes", "proceed as planned" — stays a word. The confirm card is reserved for actions whose consequences *deserve enumeration*: a release, a deletion, a spend, a public post — steps where "here is exactly what will happen" is the point of the exchange. If the agent has no consequences worth listing, it doesn't have a confirm; it has a question, and it should ask it plainly. The skill text says this in almost those words, because an agent that gates every "yes" behind a card is the bureaucratizing failure mode the first article warned about, wearing a new construct.

## The fourth surface, and why the return path is half the grammar

The first article said "three surfaces": an interactive widget, batched plain questions, native MCP elicitation. There is now a fourth: portable markdown, for hosts that render neither widgets nor question dialogs — text-only agent CLIs. Any form renders to it, and it ends with a JSON answer skeleton in exactly the shape the widget would post back. One postback grammar across all four surfaces.

That surface forced the design question I'd been deferring: what happens when the answer comes back as *text*? A widget posts structured JSON. A person typing into a terminal posts whatever they type.

The answer in 0.5.0 is a parser that never guesses. `markdown_to_answers` reads a pasted skeleton or line shorthand (`priority: high`, `2: high`, `rulings.retry-loop: fix now`) deterministically. Every line it can't place and every field id it doesn't recognize comes back as a *named problem* — not a best-effort mapping. Free-text answers ("yeah the second one, and ship it") are explicitly the agent's lane: the agent maps them into the skeleton, but as a proposal, and the validator — the same `collect_form_response` that judges widget postbacks — is the only truth. On failure, `problems_to_markdown` re-asks exactly the fields that failed, never the whole form.

The acceptance test for that loop was small and instructive. I typed `approve` — one bare word, no field id, not the skeleton. The parser refused it: `unparseable line: 'approve'`. The agent then proposed the obvious mapping into the skeleton, the validator accepted it, and the gate passed. (Had I typed the field id with a lowercase `approve`, the parser would have passed it through and the validator would have refused it — `not in options` — because the options were `Approve` and `Abort` and nobody case-folds on your behalf.) Three steps where a friendlier parser would have taken one — and the friendlier parser is exactly the thing that, one day, maps "abort" to "Approve" because it was being helpful. Trust in the rendering is cheap. Trust in the return path is the whole product.

## What I'm not claiming, updated

The first article promised that constructs which don't earn their place should die. Two amendments from the review that shaped 0.5.0, for the record: triage rulings key on stable item *ids* rather than labels (labels change between renders; rulings shouldn't — the label is only the fallback), and flat-surface degradation was made strict, so a construct that can't render faithfully on a surface fails loudly rather than approximately. Both came out of a three-seat model round table that ruled 3/3 for a markdown-surface-first expansion with a mandatory return path, and 3/3 that triage was the strongest of the proposed constructs. I chaired those rulings through the deliberation card they were partly about, which is either dogfooding or circular reasoning; I've decided it's the former, and I've written down enough that you can decide otherwise.

Still one heavy production consumer — my own stack. 514 tests, CI on three platforms, one runtime dependency. Four items I proposed are on the backlog and unbuilt — three candidate constructs (ranking, hunk review, assumption review) and a surface-capability contract; if you'd want one of them before the others, that's the most useful thing you could tell me.

## Try it

The Claude Code plugin gives you the skill and the four MCP tools without adopting anything else of mine:

```
claude plugin marketplace add Smart-AI-Memory/attune-forms
claude plugin install attune-forms@attune-forms
```

Or as a library: `pip install attune-forms` — Python 3.10+, Apache 2.0. Text-only hosts get the markdown surface and the parser above.

Six speech acts is not a claim that six is the right number. It's the number that survived. Which one is missing from your agent's conversations — the recommendation it doesn't position, the disagreement it buries, the approval it pre-checks?

---

*Patrick Roebuck builds Smart AI Memory. attune-forms: https://github.com/Smart-AI-Memory/attune-forms — PyPI: https://pypi.org/project/attune-forms/ — the first article: https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse*
