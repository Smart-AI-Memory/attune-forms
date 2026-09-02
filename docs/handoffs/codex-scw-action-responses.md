# SCW Task 8 handoff — action-scoped workspace responses

## Goal

Extend the generic command-workspace contract with optional, action-scoped
response fields that reuse the public form validator and return immutable,
normalized values without changing version 1 action-only rendering or input.

## Acceptance criteria

- The selected action alone determines the response schema.
- Missing, foreign, partial, invalid, or field-free responses fail closed.
- Field order, option order, item ids, and action association are available to
  the host's canonical contract digest.
- Widget, Markdown, headless, and real MCP stdio collection return the same
  normalized mapping.
- Action-only widget and Markdown bytes remain unchanged.
- Changed production coverage is at least 90%, and the full suite passes on
  Python 3.10 and 3.11.

## Scope and assumptions

- Branch/worktree: `codex/scw-action-responses` at
  `/private/tmp/attune-forms-scw-task8`, based on signed local commit
  `ec5ff8927fcbb6be2d69ddfc7bf53bb856019c5d`.
- Provider/session: Codex, active-provider fallback under the attune-ai
  collaboration contract; the chair authorized SCW Task 8 in the ordered
  latency sequence.
- Assumptions: `attune-forms` validates structure only. Canonical-state rebuild,
  nonce consumption, replay rejection, and command semantics remain host-owned.
- Scope expansion: `widget.py` and `markdown_surface.py` are changed because the
  approved design requires action fields to reuse the existing renderers rather
  than create a parallel control system. Default arguments preserve the old
  standalone and action-only output byte for byte.

## Current state

- Status: accepted by the chair in SCW D29 after implementation, usable
  13/13-file Fable 5.1 review, chair ruling, corrections, and central local
  verification completed. Task 9 integration subsequently added one bounded
  portable-conformance parser correction plus its regression; that correction
  is locally verified and awaits inclusion in Task 9's review packet.
- Interim-release preparation: the package metadata and manifests now name
  `0.12.0`, the changelog and README describe the public action-response
  contract, and release artifacts were built outside the worktree. No merge,
  tag, or publication has occurred.
- Changed files: `src/attune_forms/{__init__,conformance,markdown_surface,mcp_server,widget,workspace}.py`,
  `tests/test_{conformance,mcp_server,workspace}.py`, and this handoff.
- Decisions: `WorkspaceAction.response_fields` uses `FormQuestion`; collection
  adapts the selected fields to `collect_form_response`; responses are deeply
  frozen and expose a detached JSON payload; `workspace_action_contract`
  provides the complete canonical action/schema projection. The correction
  defensively snapshots every response field, deeply freezes nested values,
  preserves legacy hashability, validates authority syntax before constant-time
  comparison, and keeps detached response payloads independently mutable.
- Risks or open questions: the initial standard-price message was inconclusive;
  low-effort batch `msgbatch_01Hat3poCmNwz6knDYyHRgY9` then returned six
  findings over 13/13 files. The chair modified/promoted F1, F2, F4, F5, and
  F6 and rejected F3 because both questioned public signatures exist and their
  failure-sensitive tests pass. Batch cost was $0.79484; cumulative cost was
  $2.87112 under the $3 cap. No commit, push, PR, or deployment is authorized.
  Task 9 now consumes `workspace_action_contract` in its host digest and keeps
  stale/replay/atomic mutation checks in `attune-ai`. The added parser
  correction recognizes mixed action-response forms and field-free fallbacks
  from the existing Markdown renderer; it does not alter collection authority
  or the accepted action-response contract.
- Release-candidate review: two stateless, tool-free Fable 5.1 calls covered
  all 15 staged paths with zero omissions for a combined `$1.39861`. The first
  stopped at its 12,000-token cap after exposing a real copy/pickle regression;
  the low-effort recovery ended normally with four findings. The copy/pickle
  regression, a response-field Markdown action-scan ambiguity, and two missing
  shape regressions were corrected. The speculative `init=False` edge was made
  robust and plain-`FormQuestion` value equality was restored. The request to
  remove internal handoff evidence is rejected: the tracked handoff is the
  repository's required cold-handoff receipt and the built sdist contains no
  `docs/handoffs` path. The blank workspace live region remains intentionally
  present as the rich lifecycle-status surface; the new all-response-field
  regression pins it while proving the plain-button dispatch script is absent.

## Verification

| Claim | Failure-sensitive probe | Result |
| --- | --- | --- |
| Focused behavior and real MCP boundary work | `PYTHONPATH=<task8>/src <Python 3.10> -m pytest tests/test_workspace.py tests/test_mcp_server.py -q` | PASS — 81 tests |
| Complete supported suite passes on Python 3.11 | `uv run --python 3.11 --extra dev pytest -q` | PASS — 956 tests |
| Complete supported suite passes on Python 3.10 | `uv run --python 3.10 --extra dev pytest -q` | PASS — 956 tests |
| Changed production coverage exceeds the task bar | Coverage.py full-suite receipt intersected with zero-context Git added lines | PASS — 223/223 executable changed lines, 100% |
| Version 1 rendering is byte-compatible and permanently guarded | SHA-256 of preview widget/Markdown and intake-form widget/Markdown on signed base versus task worktree; tracked hash regression | PASS — all four hashes identical and pinned |
| Review corrections are failure-sensitive | Immutable-schema mutation, field-order digest, baked widget envelope, Unicode authority, stdio response-field render, detached nested list, and action/response hashing tests | PASS |
| Formatting and static checks pass | repository-pinned Black and Ruff hooks; `git diff --check` | PASS |
| Different-model review is complete | Fable 5.1 batch, low effort, no tools/session, 13/13 files | PASS WITH FINDINGS — five corrected under chair ruling; F3 rejected with executable evidence; cumulative cost $2.87112 |
| Task 9 integration correction | Mixed action-response form plus field-free fallback through portable conformance; adversarial parser boundaries; complete supported suites; changed-line coverage; formatting and diff hygiene | CORRECTED — chair modified/promoted F2; action discovery stops before the first validated response contract, pre-contract decoy action/JSON fences fail closed, post-contract decoys are ignored, mixed portable/constrained parity passes, and 956/956 tests pass on Python 3.10 and 3.11 |
| Release artifacts install and preserve the public boundary | Build sdist/wheel, run `twine check`, install the wheel into a clean Python 3.11 environment, then exercise an action-response render and collection through a real MCP stdio subprocess | PASS — rebuilt `attune_forms-0.12.0` wheel and sdist pass `twine check`; the clean-installed wheel returned `apply_rulings` and all three normalized responses over real stdio |
| Release-candidate different-model review | Fable 5.1, stateless/tool-free, exact staged manifest | PASS WITH FINDINGS — 15/15 paths, zero omitted, `$1.39861`; three implementation/test gaps corrected, internal-handoff removal rejected with an sdist contents probe |

## Next action

Task 8 and the Task 9 integration correction are accepted inputs to the
interim performance release. Complete the release-candidate review, commit,
push, and CI preparation, then stop for the chair before merge, tag, or PyPI
publication.
