# Agent work handoff

## Goal

Implement Interaction Quality Contract Task 2 in `attune-forms`: a generic,
capability-based conformance harness for structural, viewport, projection,
retention, and latency evidence. The harness must not contain command semantics
or grant workspace authority.

## Acceptance criteria

- The original unpaginated seven-action constrained-host shape fails.
- Paginated or compact shapes pass the applicable deterministic receipts.
- Screenshots and button-label substrings cannot pass structural checks.
- Renderer-only timings cannot pass the full latency receipt.
- Cold and warm raw samples produce reproducible p50/p95/p99 phase aggregates.
- Changed production code has at least 90% coverage.

## Git state

- Branch: `codex/iqc-conformance-harness`
- Worktree: `/private/tmp/attune-forms-iqc-conformance`
- Base: `origin/main` at `e5ec4f85f699c4c8e0592825b7eaa1d325144992`
- No commit or push has been made.

## Changed files

- `src/attune_forms/conformance.py` — capability profiles, structural probes,
  phase samples, aggregates, findings, and reports.
- `src/attune_forms/__init__.py` — public exports.
- `tests/test_conformance.py` — behavioral, hostile-boundary, timing, and
  validation coverage.
- `README.md` and `CHANGELOG.md` — public contract and release note.

## Verification receipts

- Baseline before changes: `893 passed in 2.90s`.
- Focused suite after review corrections: `39 passed`.
- Python 3.10 compatibility receipt: the same 39 focused tests passed under
  CPython 3.10.11 with the worktree source on `PYTHONPATH`.
- Full suite after review corrections: `932 passed in 2.61s`.
- Focused production coverage for `conformance.py`: 90% (585 statements,
  56 missed), meeting the approved engineering floor.
- Final real local timing diagnostic: 20 fresh subprocesses reached an
  actionable rich projection at p50 69.766 ms, p95 72.329 ms, and p99
  74.082 ms; 50 warm in-process renders measured p50 0.009083 ms, p95
  0.012625 ms, and p99 0.016292 ms.
- Ruff passed for the changed Python files after its import-sort fix.
- Black formatted the new implementation and tests.
- `python -m compileall` and `git diff --check` passed.
- Final owning-spec execution boundary: symbol reality `24246eb22d8a` and
  falsifiability `db76d318edee` passed; public-export blast radius produced
  chair receipt `7f3e8359466f`.
- Final owning-spec verification boundary: symbol reality `12109dceae7c` and
  falsifiability `a4ba055877dd` passed; public-export blast radius produced
  chair receipt `45f5878983bf`.
- Claude Fable 5 reviewed all six files with zero omissions in
  `review-codex-iqc-conformance-harness-20260901-1735`; tools and session
  persistence were disabled, and the run cost $1.4014575 under its $3 cap.
  The chair promoted findings 1 and 5–10 and modified/promoted findings 2–4.
  All ten corrections are covered by the focused suite above.

The chair's 2026-09-01 instruction to proceed with this exact IQC Task 2 slice
is the acknowledgment for those two mechanical chair-radius receipts. It is
not a waiver for later tasks or a broader public-surface change.

These receipts establish the local Python contract and the attributed local
render phase only. They do not establish transport, acknowledgement, progress,
terminal, live rich-host, or native-dialog behavior.

## Unresolved risks and next action

- Rich-widget and native-dialog live host receipts remain unavailable in this
  environment and must stay recorded as unavailable, never inferred passing.
- Transport acknowledgement, progress delivery, terminal publication, and
  human-dwell timing remain Task 5 boundaries; local renderer measurements do
  not satisfy them.
- Next: integrate command-semantic fixtures under IQC Task 3 after its owning
  task gate. No commit, push, or deployment has been performed.
