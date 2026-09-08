# Outcome pilot v0.2 results

The task set did not discriminate between the conditions. Every condition passed all three repeats in every scenario/variant — 72 of 72 units — so the primary outcome has no variation to rank them by. This is a ceiling result about these tasks and this instrument. It is not a finding that typed forms confer no advantage, not proof that the conditions are equivalent, and not evidence either way about whether forms help human users.

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

All nine fully specified control runs completed in one call with no clarification requests. The tested typed condition did not force a form when no facts were missing. This is the one conformance claim the pilot does support on its own terms: the routing does not over-trigger on a fully specified task, and it is worth holding as a regression even though it says nothing about comparative task success.

Latency showed mixed directions against free-form: typed-minus-free-form median paired differences were negative in security, removal and release strategy, and positive in the other five groups. These three-pair observations are descriptive; they do not establish a general speed advantage. Typed input-token medians were higher in every group, by 0.2% to 0.4% (largest absolute gap 311 tokens on a base of 106,676). Output-token medians were higher in seven groups, by 18 to 62 tokens on bases of 59 to 200, and tied in the fully specified control. The direction is consistent and the magnitude is small: on this task set the structure carries a measurable but marginal token cost. Token counts are provider telemetry, not a dollar-cost estimate.

## Interpretation and next experiment

These results support a narrow statement: under the frozen simulator, runtime, task API and scoring rules, every retained run completed its defined task. The instrument now records task outcomes, but this task set does not distinguish the conditions on success. No general safety, equivalence, superiority, human-effort or abandonment claim follows.

The shared JSON action envelope is the primary threat to construct validity, and it works against detecting any form advantage. Every condition receives structured decision keys, the deliverable field list and the artifact JSON Schema through the same public context, so the free-form condition already holds much of what the typed condition is meant to supply. A design that controls the task API this tightly cannot isolate the contribution of typed structure; a comparison that could would have to let the free-form condition work without that scaffolding.

Deterministic user answers are the second limit. The simulated user returns the same complete, correct facts however a question is posed, so misreading, partial answers and abandonment — the mechanisms typed forms are meant to reduce — cannot occur by construction. Human effort and human abandonment are null in all 72 units for this reason, not because they were measured at zero. The typed condition exercises form parsing and response validation, not a human operating the native UI. The common sandbox prevents real side effects; observed authorization behavior applies only inside that sandbox.

Before a larger confirmatory comparison, define representative tasks independently of these results, including realistic ambiguity, contradictory requirements and corrections, and audit their scoring contracts. Select sample size around a declared meaningful improvement and observed variability. Do not tune tasks merely to make forms win or pool the invalid cohort.

A claim about users needs a separately designed comparison of the actual forms UI with chat, randomized or counterbalanced across equivalent tasks. Measure artifact quality, time, corrections, effort and abandonment. That study has not been run or budgeted.

## Evidence

- `outcome-pilot-v0.2-report.json`: frozen descriptive aggregation.
- `outcome-pilot-v0.2-verification.json`: per-unit raw manifest hashes and turn counts.
- Local raw evidence: `/Users/patrickroebuck/attune-forms-evidence/outcome-pilot-v0.2/runs`.
- Validation before collection: 1,247 repository tests passed; 26 scorer audit cases; all CI checks passed, including both Windows lanes.
