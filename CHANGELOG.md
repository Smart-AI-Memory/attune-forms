# Changelog

All notable changes to attune-forms are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Smart-AI-Memory/attune-forms/releases/tag/v0.1.0
