# Outcome pilot v0.2 results

The pilot found no task-success advantage for typed forms on these seven simulated tasks. Every condition passed all three repeats in every scenario/variant. This is a ceiling result, not proof that the conditions are equivalent or that forms help human users.

## Collection and verification

- Frozen collector: `f623590c76fec2d44b419675409015481d4bbf8c`; protocol `outcome-pilot-v0.2`.
- 72 planned units, 72 completed, 0 missing, 0 provider failures; 288 model calls of the authorized maximum 1,152.
- All 72 raw bundles and 288 turn bundles passed manifest verification, exact protocol/unit checks, and call-to-trace equality checks.
- Replaying the judge on artifacts, state and events with condition labels removed reproduced all 72 retained outcomes. This is a deterministic replay, not a separate human review.
- All artifacts matched their disclosed schemas; no unauthorized execution attempts were observed. All required sandbox changes, inspections, decisions and corrections passed their defined checks.
- The invalid v0.1 cohort remains separate and untouched: five completed units, 21 sealed calls and one interrupted call. Its scores are excluded.

## Per-scenario results

Each cell is median model calls across three runs. Task success is 3/3 for each cell. The accompanying JSON includes observed/missing counts, ranges, tokens, latency and exact matched-pair differences.

| Scenario | Free-form | Sequential | Typed forms |
|---|---:|---:|---:|
| Security audit | 3 | 6 | 3 |
| Artifact removal | 5 | 5 | 5 |
| Revoked approval | 5 | 5 | 5 |
| Migration | 6 | 7 | 6 |
| Release strategy | 5 | 6 | 5 |
| Runtime, missing facts | 2 | 3 | 2 |
| Runtime, fully specified | 1 | 1 | 1 |
| Finding triage | 3 | 3 | 3 |

Typed forms matched free-form median call counts in all eight scenario/variant groups. Both can batch questions; their advantage over sequential clarification in four groups does not establish an advantage specific to forms.

All nine fully specified control runs completed in one call with no clarification requests. The tested typed condition did not force a form when no facts were missing.

Latency showed mixed directions against free-form: typed-minus-free-form median paired differences were negative in security, removal and release strategy, and positive in the other five groups. These three-pair observations are descriptive; they do not establish a general speed advantage. Typed input-token medians were higher in every group, and output-token medians were higher in seven groups (tied in the fully specified control). Token counts are provider telemetry, not a dollar-cost estimate.

## Interpretation and next experiment

These results support a narrow statement: under the frozen simulator, runtime, task API and scoring rules, every retained run completed its defined task. The instrument now records task outcomes, but this task set does not distinguish the conditions on success. No general safety, equivalence, superiority, human-effort or abandonment claim follows.

The conditions use a shared JSON action envelope and deterministic user answers. The typed condition exercises form parsing and response validation, not a human operating the native UI. The common sandbox prevents real side effects; observed authorization behavior applies only inside that sandbox.

Before a larger confirmatory comparison, define representative tasks independently of these results, including realistic ambiguity, contradictory requirements and corrections, and audit their scoring contracts. Select sample size around a declared meaningful improvement and observed variability. Do not tune tasks merely to make forms win or pool the invalid cohort.

A claim about users needs a separately designed comparison of the actual forms UI with chat, randomized or counterbalanced across equivalent tasks. Measure artifact quality, time, corrections, effort and abandonment. That study has not been run or budgeted.

## Evidence

- `outcome-pilot-v0.2-report.json`: frozen descriptive aggregation.
- `outcome-pilot-v0.2-verification.json`: per-unit raw manifest hashes and turn counts.
- Local raw evidence: `/Users/patrickroebuck/attune-forms-evidence/outcome-pilot-v0.2/runs`.
- Validation before collection: 1,247 repository tests passed; 26 scorer audit cases; all CI checks passed, including both Windows lanes.
