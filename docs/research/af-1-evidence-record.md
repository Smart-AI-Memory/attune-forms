# AF-1 implementation evidence record

Status: implementation record; no behavioral or legal conclusion

Recorded: 2026-09-04 (America/New_York)

## Purpose

This record connects the first implementation slice in GitHub issue
[#74](https://github.com/Smart-AI-Memory/attune-forms/issues/74) to its
implementation and tests. It records what was checked, what passed, and what
remains unproved. It does not claim that typed interaction is superior, that
the benchmark has produced comparative evidence, or that this record alone
establishes legal admissibility.

The external issue is mutable. The acceptance text below is a compact mapping,
not a replacement for the issue history. Git preserves this record and the
implementation together.

[`af-1-artifact-manifest.sha256`](af-1-artifact-manifest.sha256) records
SHA-256 digests for the implementation, fixtures, schema, tests, and evidence
documents as they existed at this checkpoint. The manifest does not hash
itself.

## Provenance

- Repository: `Smart-AI-Memory/attune-forms`
- Execution specification: GitHub issue #74, created and last updated
  `2026-09-03T22:13:56Z` when retrieved for this audit
- Original draft: GitHub PR
  [#73](https://github.com/Smart-AI-Memory/attune-forms/pull/73), branch
  `research/interaction-benchmark`, head
  `a9142520b0427f2bcfe24e12527b836188a1c657`
- Base: `origin/main` at
  `5e69e1567d1e9047c97f3645e268a61dd22abd45`
- Clean implementation branch: `codex/af-1`
- Imported implementation tree: commit
  `7327e6cfd35939b2d0e66d13e7f957c02da73577`
- Audit cleanup commit:
  `963ec4b75b460b9e5679462fbdcf0fda975d4028`
- Acceptance hardening commit:
  `609b185f16dc192dc98fca6f383b9e4a1d0e585a`

The tree at imported commit `7327e6c` was byte-identical to draft head
`a914252` (`git diff --stat a914252 7327e6c` produced no output). Commit
`963ec4b` changed imports and line wrapping only to satisfy the repository's
Ruff gates.

Git reported signature status `E` for commits `963ec4b` and `609b185`, meaning
the local Git installation could not check their signatures. This record does
not represent either commit as cryptographically verified.

## Acceptance-to-evidence matrix

The identifiers AF1-AC1 through AF1-AC11 are local labels added by this record
in the same order as issue #74. They are not GitHub issue identifiers.

| ID | Acceptance criterion | Status and boundary | Implementation evidence | Test evidence |
| --- | --- | --- | --- | --- |
| AF1-AC1 | Fixture loader validates all six scenario families | Verified | `SCENARIO_FAMILIES` and `load_scenarios` in `benchmarks/runner.py` | `test_loader_rejects_a_fixture_missing_a_required_family`; `test_loader_rejects_an_unknown_family`; bundled-family coverage test |
| AF1-AC2 | Neutral condition-adapter protocol exists | Verified | `ConditionAdapter` in `benchmarks/runner.py` | free-form, sequential, and hostile-adapter contract tests |
| AF1-AC3 | Free-form adapter exists | Verified | `FreeFormAdapter` | `test_free_form_allows_batched_clarification` |
| AF1-AC4 | Sequential-clarification adapter exists | Verified | `SequentialClarificationAdapter` | rejection and acceptance tests for decision cardinality |
| AF1-AC5 | Deterministic scorer handles seeded machine-measurable failures | Verified for the implemented generic safety metrics; family-specific scoring remains blocked | `score` and event-trust filtering | invalid authority, stale/scope, incomplete-run, actor-assertion, and unnecessary-confirmation tests |
| AF1-AC6 | JSONL result output validates against the result schema | Verified | `BenchmarkResult.as_json`, `results_to_jsonl`, and `benchmarks/schema/result.schema.json` | Draft 2020-12 metaschema check and generated-result validation in `test_serialized_result_validates_against_closed_schema` |
| AF1-AC7 | Failed and incomplete runs are represented and tested | Verified | `_failed_artifact` and `run_suite` | provider exception and incomplete-result tests |
| AF1-AC8 | Missing metrics cannot become favorable zeros | Verified | nullable telemetry fields plus explicit notes in `score` | `test_missing_telemetry_stays_missing_instead_of_becoming_zero` |
| AF1-AC9 | Scenario/scoring core requires no attune-forms runtime import | Verified | independent `benchmarks` package | schema-neutrality test and direct import probe documented below |
| AF1-AC10 | Checkpoint A is committed before typed-adapter work | Verified for repository history; typed adapter remains absent by chair ruling | `q-interaction-benchmark-spec-001.md` | repository history and import probe |
| AF1-AC11 | An adapter cannot alter fixture success criteria through normal interfaces | Verified for the public adapter protocol | adapters receive `ActorScenario`, not `EvaluatorScenario` | `test_adapter_cannot_access_or_change_fixture_success_criteria` |

## Verification record

Environment used for the recorded run:

- Python `3.10.11`
- pytest `9.1.1`
- Ruff `0.13.2`

Commands run from the clean AF-1 worktree:

```text
python -m pytest -p no:cacheprovider -q
python -m ruff check --no-cache benchmarks tests/test_interaction_benchmark_contract.py tests/test_interaction_benchmark_runner.py tests/test_interaction_benchmark_result_contract.py tests/test_interaction_benchmark_provider.py
python -m ruff format --check --no-cache benchmarks tests/test_interaction_benchmark_contract.py tests/test_interaction_benchmark_runner.py tests/test_interaction_benchmark_result_contract.py tests/test_interaction_benchmark_provider.py
git diff --check origin/main...HEAD
```

Before the AF1-AC1, AF1-AC6, and AF1-AC11 hardening added by this audit, the
full suite reported `980 passed`; the focused AF-1 suite reported `22 passed`.
After hardening, the same commands reported `983 passed` and `25 passed`,
respectively. Ruff lint and format checks passed, and `git diff --check`
produced no findings.

A direct import probe loaded `benchmarks.runner` in a fresh Python process and
found no loaded module named `attune_forms` or beginning with
`attune_forms.`.

The deterministic `attune_verify` checker inspected all six research and
roundtable documents for imports, flags, links, and count claims. The five
pre-existing documents returned `ok: true` with no findings. This record
returned `ok: true` with four `unknown_flag` findings covering two repeated
flags because the checker parsed `git diff --stat` and `git diff --check` as
standalone `diff` commands without subcommand help. Both Git commands were
executed directly and succeeded. The warnings are retained here rather than
suppressed.

## Evidence boundaries

AF-1 establishes software contracts and test behavior only. It does not yet
establish:

- outcomes from a real model or provider;
- comparative performance among free-form, sequential, and typed interaction;
- human workload, comprehension, consent, or decision quality;
- a production `AuthorityEnvelope` API;
- authority to perform real consequential actions;
- cryptographic authorship or a legal chain of custody beyond the available
  Git and GitHub records.

Checkpoint B therefore remains **HARNESS PASS / EVIDENCE BLOCK**. Raw baseline
runs, stronger family-specific scoring, and a renewed checkpoint are required
before a typed attune-forms adapter or comparative public claim.

## Preservation

Preserve the following together when reviewing, exporting, or citing AF-1:

1. issue #74 and draft PR #73 histories;
2. this evidence record;
3. the SHA-256 artifact manifest;
4. both roundtable checkpoint reports;
5. benchmark source, fixtures, and schema;
6. the test files and complete CI receipts;
7. any future raw transcripts, event logs, JSONL results, environment metadata,
   and scorer version used to make a comparative claim.

Do not overwrite raw evidence. Add corrections as new commits or append-only
records that identify what changed and why.
