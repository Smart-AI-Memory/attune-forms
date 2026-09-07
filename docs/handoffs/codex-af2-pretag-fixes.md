# Agent work handoff

## Goal

Resolve the bounded AF-2 review findings before v0.15.0 is tagged.

## Acceptance criteria

Reserved unanswered markers and unverified scalar multi-select escaping fail
admissibility; emitted headers fit their profile; payload copies cannot mutate
retained batch state; duplicate installed profile IDs fail closed. Synthetic
fixture tests do not claim trusted host-response evidence.

## Scope and assumptions

- Branch/worktree: `codex/af2-pretag-fixes`, `/private/tmp/attune-forms-af2-fixes-20260907`.
- Provider/session: Codex, implementing Patrick's narrowed review disposition.
- Base: squash `aa9b28bf2f421792bcc683996ed6aacfd91139de`.
- Release PR #92 handles the version bump separately. This branch changes no version.

## Current state

- Source: `host_question.py`, `conformance.py`; regression tests in
  `test_host_question.py` and `test_renderer_registry.py`.
- `HostQuestionBatch.payload` preserves the dict interface but returns a fresh
  copy backed by an immutable JSON snapshot. Use `.payload` for transport;
  dataclass serialization now includes the private snapshot, not a payload field.
- `MultiSelectEncoding.escaping_verified` defaults to false and participates in
  profile serialization/digests. The installed profile refuses multi-select
  labels containing its delimiter or a quote. Synthetic encoder fixtures cannot
  establish host verification. Single-select and list encodings are unaffected.
- Attempts/deadline are documented as consumer policy, not measured host limits.
- The test-side simple decoder remains only as a synthetic fixture consistency
  check; real codec/correlation and validator boundary evidence belong to Task 2.
- Unverified: live host escaping. Do not enable the profile flag without retained
  host evidence covering delimiters, quotes, backslashes, and ordering.

## Verification

| Claim | Failure-sensitive probe | Result |
| --- | --- | --- |
| Suite regression | `.venv/bin/python -m pytest -q --cov=attune_forms --cov-report=term-missing --cov-report=json:/private/tmp/af2-fixes-coverage.json` | 1224 passed, 96% package coverage; 26/26 added executable source lines covered |
| Packaging and registry | `uv build --wheel`, fresh Python 3.12 venv, wheel installation, `scripts/af2_clean_wheel_probe.py` from /private/tmp | Passed; site-packages import, unique route-active profile, no-escape sweep clean |
| New behavior in installed wheel | Direct predicate/renderer/router probes for marker, comma/quote labels and 1-character header; mutation of returned payload; duplicate profile injection | All refused/isolated as intended; marker/codec forms recommend widget |
| Style | Repository-pinned pre-commit hooks on changed Python files | Passed |

Updated wheel facet digest:
`577e0c05bb48d67b19c740a4df99dc298efc7ce0f1a420ee5c163209b1232c47`.
Updated implementation digest:
`dbe923fd2db1c7454f3d84cb753898f75aaea7c08cfb445a8f32e036c0c675be`.
These are pre-version-bump receipts, not a receipt for the eventual release wheel.

## Next action

Review and merge this follow-up before tagging; ensure release PR #92 includes
it, rerun release receipts at the final release commit, and obtain separate tag
authorization. Task 2 must lock that released artifact and derive fresh evidence.
Delete this handoff when the branch merges.
