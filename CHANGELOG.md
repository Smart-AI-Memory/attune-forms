# Changelog

All notable changes to attune-forms are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- Docs state the construct count as six (decision, pushback, progress,
  deliberation, triage, confirm) — the plain batched form is the
  substrate the constructs sit on, not a construct; the "member #N"
  numbering in code comments follows the same count

## [0.5.0] — 2026-08-14

The grammar-expansion release: the communication grammar grows from
three constructs on three surfaces to six constructs on four — every
one with a validated round-trip — deliberated by the multi-LLM round
table (thread `q-forms-grammar-expansion-001`: 3/3 on the markdown
surface and triage, id-keying and strict-degradation amendments
applied as ruled), and hardened by a post-merge 8-angle review plus a
cloud ultrareview before this cut.

### Added
- Tolerant markdown ingestion (spec `markdown-ingestion`, the S4
  surface's return path — roundtable-ruled "spec next"):
  `markdown_to_answers` deterministically parses a typed reply (pasted
  JSON skeleton or line shorthand — `field_id: value`, `N: value`,
  dotted triage rows) with every unparseable line and unknown id a
  named problem, never a guess; `problems_to_markdown` renders
  validation failures as a markdown re-ask of only the offending
  fields. Validation truth stays `collect_form_response`; free-text
  replies remain the host agent's skill-taught lane
- `confirm` construct (spec `confirm-construct`, roundtable-ruled
  "spec next"): action preview with a structured `consequences` list
  (`{label, severity?, detail?}`) and a two-way approve/abort gate —
  exactly two options, and `default`/`recommended` are rejected by
  the validator (a pre-selected approval defeats the gate, D2). Flat
  surfaces render a two-option single-select with a compact "Will: …"
  receipt; the markdown skeleton never prefills the answer
- `deliberation` construct: multi-voice endorsements per option
  (`{option: [voice, ...]}`) rendered as chips, synthesis pick badged,
  chair picks one; flat fallback folds endorsements into a compact
  summary; answer validates as a single-select
- `triage` construct: per-item rulings over a reviewed list
  (`triage_items` + `dispositions` + optional `suggested`); answer is
  `{item id: disposition}` keyed on stable per-item ids (label
  fallback); expands to one single-select per item on flat surfaces
  via dotted ids that fold back in `collect_form_response`
- Portable markdown surface (`form_to_markdown`, S4): renders any form
  for text-only hosts (Codex CLI, Antigravity) and emits the widget's
  sentinel-marked JSON answer skeleton as the return path — one
  postback grammar across all four surfaces
- `triage_item_key` exported: the one keying rule every surface shares
- Reference form + example answers now cover the two new constructs;
  widget round-trip, CSS-family, and markdown conformance guards
  extended to them

### Fixed
- Twelve post-merge review findings, each with a pinned regression
  (#18, #19): typed shorthand now overrides a pasted JSON skeleton
  (including dotted triage rows merging into a quoted mapping, typed
  wins); the dotted triage namespace is guarded at definition time;
  code fences with any language tag are excluded from shorthand
  parsing; unknown JSON answer keys are named problems; non-finite
  numbers are rejected by the validator on every surface;
  label-keyed triage shorthand parses; triage answers render per-item
  in summaries; `to_ask_user_format` raises loudly for triage; falsy
  defaults survive into the reply skeleton
- CSS class-uniqueness guard: no class may be styled by two family
  blocks — the collision mode the coverage guard cannot see (#17)

### Changed
- Form theme budget raised 6 KB → 8 KB (8,158 B measured with the
  TRIAGE + CONFIRM families and deliberation seat chips; ratified
  with the #14 merge)
- MCP field schema documents the new types and extras (tool names and
  result shapes unchanged)

## [0.4.0] — 2026-08-14

The plugin release: attune-forms becomes installable as a Claude Code
plugin, and the communication-grammar article ships in-repo as its
verified master.

### Added
- Claude Code plugin wrapper: generic forms skill + marketplace scaffold, installable via `claude plugin marketplace add Smart-AI-Memory/attune-forms` (#4)
- "A Communication Grammar for AI Agents" — the article introducing the grammar, kept in `docs/` as its verified master (#6, #7, #8)
- Widget-preview dev lane: `.claude/launch.json` renders the reference form through the real widget pipeline (#9)
- Version-sync drift guard test: README install snippets can't silently diverge from `pyproject.toml` (#5)

### Fixed
- Test suite pins imports to the checkout's own `src/`, so a stale editable install can no longer swap in another worktree's code

## [0.3.0] — 2026-08-12

### Added
- Standalone MCP server (`attune-forms-mcp`): the four elicitation tools — ask, render form, render widget, collect response — mirrored from attune-ai, stdio transport, `[mcp]` extra (#3)

## [0.2.0] — 2026-08-12

### Added
- Collision-proof public names with legacy attune-ai names honored as shims (P1) (#2)
- Lint gate in CI: pre-commit (black/ruff, pinned to attune-ai's versions) on every push/PR (#1)

## [0.1.0] — 2026-08-12

### Added
- Initial extraction of the attune-ai elicitation subsystem: declarative `FormSchema`, build/collect validation, multi-surface renderers (widget HTML, AskUserQuestion batching, MCP elicitation), surface router, template layer with ask-time intake generation
- Trusted-publishing release workflow (tag-triggered, PyPI environment)

[Unreleased]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Smart-AI-Memory/attune-forms/releases/tag/v0.1.0
