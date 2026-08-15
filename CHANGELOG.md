# Changelog

All notable changes to attune-forms are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

The grammar-expansion tranche, deliberated by the multi-LLM round
table (thread `q-forms-grammar-expansion-001`: 3/3 on the markdown
surface and triage, id-keying and strict-degradation amendments
applied as ruled).

### Added
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

### Changed
- Form theme budget raised 6 KB → 8 KB (7,204 B measured with the
  TRIAGE family + deliberation seat chips; ratified in this PR's
  review)
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
