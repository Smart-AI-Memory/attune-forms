# AF-2 implementation evidence record

Status: implementation record; baseline collection remains blocked

Recorded: 2026-09-04 (America/New_York)

## Purpose

This record connects the AF-2 scoring and evidence-protocol scope to the code,
tests, documentation, and review state preserved in Git. It records what was
implemented and checked. It does not claim a behavioral result, authorize a
provider call, or offer an opinion on legal admissibility.

The controlling scope is
[`af-2-scoring-protocol.md`](../../.claude/plans/af-2-scoring-protocol.md).
Execution began after the user replied `go` to the AF-2 work order in the
originating Codex task. The repository does not contain the full task
transcript, so that authorization must be preserved separately if it is needed
as evidence outside the development record.

[`af-2-artifact-manifest.sha256`](af-2-artifact-manifest.sha256) records
SHA-256 digests for the files named in this record. The manifest does not hash
itself.

## Provenance

- Repository: `Smart-AI-Memory/attune-forms`
- Starting point: merged AF-1 commit
  `cc94fc202d4d4921359da886064aee86f8552c29`
- Clean worktree branch: `codex/af-2-scoring-protocol`
- Implementation commit:
  `95b400c01a9257f86346b0077fa62835bf2d1a37`
- Documentation checkpoint commit:
  `d8fc3306dec4b1605535f938ea30686953cf25bb`

`git verify-commit` returned a good signature for both commits. Each signature
used EDDSA key `24CAB79DDA859FF51BAD6E2BD36957ACAE09C705` and resolved locally to
`Patrick Roebuck <patrick.roebuck@smartaimemory.com>` with ultimate trust. That
result authenticates the commits under the local keyring's trust state; it does
not independently establish custody of the key or third-party time of signing.

No AF-2 branch, pull request, release, or provider result had been pushed or
published when this record was prepared.

## Acceptance-to-evidence matrix

The identifiers below are local labels for this record.

| ID | Acceptance criterion | Status and boundary | Implementation evidence | Test evidence |
| --- | --- | --- | --- | --- |
| AF2-AC1 | All six scenario families have versioned executable scoring rules | Verified for policy `0.1.0` | `benchmarks/policies/scoring-v0.1.json`; `benchmarks/scoring.py`; closed policy schema | policy-schema validation; fixture-to-policy coverage; seeded family cases |
| AF2-AC2 | Safety findings cannot be based on actor assertions | Verified for the policy loader and scorer | allowed trust is limited to runner-observed and evaluator-derived evidence | unsafe-policy rejection; actor-authority isolation; raw/evaluation separation tests |
| AF2-AC3 | Missing required evidence is not converted to zero, success, or failure | Verified | nullable result contract; incomplete-run and field-missing rules | incomplete, actor-only, and partial-evaluator tests |
| AF2-AC4 | Provider, model, sampling, repeats, exclusions, missingness, and falsification are fixed before collection | Implemented; provider/model/sampling values remain chair-required | draft protocol, closed schema, immutable loader, and fail-closed readiness check | blocked-draft, ratified fixture, sampling-unavailability, changed-hash, and 42-run tests |
| AF2-AC5 | Raw and later evaluation evidence are append-only and independently hashed | Verified at the software-contract level | `benchmarks/evidence.py` raw/evaluation paths and exact-file manifests | rewrite refusal, tamper detection, evaluator separation, simulated-action, and raw-reference tests |
| AF2-AC6 | Every scorer has seeded passing and failing cases | Verified for all six scenario families and the stale-authorization rule | policy thresholds and reducers | parameterized pass/fail cases plus stale, conflicting, and partial evidence cases |
| AF2-AC7 | Operational definitions and evidentiary limits are documented | Verified for repository content | scoring policy, evidence protocol, status page, and Checkpoint B.1 report | live-schema example test and document-relative link test |
| AF2-AC8 | Checkpoint B.1 is recorded before baseline collection | Recorded but not ratified | `q-interaction-benchmark-scoring-001.md`; draft protocol chair fields | readiness test proves collection remains blocked |

## Verification record

Environment used for the final recorded checks:

- Python `3.12.2`
- pytest `7.4.3`
- jsonschema `4.25.1`
- Ruff `0.14.4`
- Black `25.9.0`

Commands run from the AF-2 worktree:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider -q
ruff check --no-cache .
black --check .
git diff --check
git verify-commit 95b400c01a9257f86346b0077fa62835bf2d1a37
git verify-commit d8fc3306dec4b1605535f938ea30686953cf25bb
```

The full suite reported `1018 passed`. The focused AF-2 and inherited AF-1
benchmark suites reported `58 passed`. Ruff lint, Black format, and
`git diff --check` passed. The repository's commit hooks also passed under the
versions pinned in `.pre-commit-config.yaml`: Black `24.10.0`, Ruff `0.8.4`,
end-of-file, and trailing-whitespace checks passed; YAML and TOML checks were
skipped because the commits contained no files of those types.

Draft 2020-12 validation checked both new closed schemas and a generated result.
The published result example is tested against the live result schema. The
protocol test computes the documented pilot size from seven scenarios, two
conditions, and three repeats rather than accepting the number 42 as prose.

## Documentation fact-check

`attune_verify` `0.5.0` checked imports, flags, links, and count claims in five
AF-2 research and review documents. Every result returned `ok: true`. It also
reported seven `dead_link` warnings because its declared document-directory root
refused correct Markdown links containing `..`:

- two links in `scoring-policy-v0.1.md`;
- three links in `evidence-protocol-v0.1.md`;
- one link in `implementation-status.md`; and
- one link in `interaction-benchmark-v0.md`.

The persistent test
`test_af2_document_relative_links_resolve_from_each_document` resolves every
relative link from the directory containing its document and passed. No link
was changed merely to satisfy the checker's narrower root model.

The ambient source cross-check recomputed the fixture, scoring-policy, and
draft-protocol SHA-256 values; compared the rule table to the executable JSON;
confirmed the six fixture families, seven fixture scenarios, two baseline
conditions, and three repeats; and found no retained raw result bundle in the
repository.

## Evidence boundaries

AF-2 establishes software behavior and a collection protocol. It does not yet
establish:

- a selected provider, API version, model, model version, or sampling regime;
- a retained evaluator implementation for real runs;
- any prompt, transcript, event, or result produced by a real provider;
- comparative performance between free-form and sequential clarification;
- an aggregation method, uncertainty interval, effect size, or publishable
  statistical conclusion;
- performance of a typed attune-forms condition;
- human workload, comprehension, consent, or trust calibration;
- WORM storage, independent timestamping, custody-transfer signatures, or a
  complete legal chain of custody.

The SHA-256 and Git controls make later changes detectable when the original
digests and keys remain trustworthy. They do not make file alteration
impossible.

## Remaining gate

Checkpoint B.1 remains **CHAIR_REQUIRED / COLLECTION BLOCKED**. Before AF-3 may
make its first provider call, the chair must review and record:

1. provider id and API version;
2. model id and model version;
3. sampling mode and every supported value or explicit unavailability reason;
4. the unchanged fixture and scoring-policy digests;
5. three repeats, no post-run exclusions, explicit missingness, all six
   falsification rules, simulated actions only, and the append-only layout; and
6. `COLLECTION_AUTHORIZED`, chair identity, and an offset-bearing timestamp in
   a signed commit.

The typed attune-forms adapter and comparative claims remain blocked until the
resulting free-form and sequential records survive renewed Checkpoint B review.

## Preservation

Preserve this record with the artifact manifest, both AF-2 commits, their
signature-verification output, the originating task transcript, the AF-1
evidence record, and any future protocol-specific raw and evaluation bundles.
Corrections belong in a new signed commit; sealed evidence is not edited in
place.
