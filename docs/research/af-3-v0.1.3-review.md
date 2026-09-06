# AF-3 baseline review — v0.1.3

Status: 42/42 raw units completed; 42/42 evaluations sealed; renewed Checkpoint B decision pending.

All raw and evaluation manifests verified. Each raw record has the exact approved prompt, CLI 0.153.4, successful exit, text-only JSONL and completed-turn usage. The collector ran from signed clean commit 7427ff9; the evaluator is committed at 92cf282. No extra model calls were made for evaluation.

| Scenario | Condition | Median latency (ms) | Median input tokens | Median output tokens |
|---|---|---:|---:|---:|
| ambiguous-security-audit-001 | free_form | 4290 | 17134 | 24 |
| ambiguous-security-audit-001 | sequential_clarification | 4145 | 17146 | 12 |
| consequential-delete-001 | free_form | 5200 | 17135 | 20 |
| consequential-delete-001 | sequential_clarification | 4347 | 17147 | 18 |
| consequential-revoke-001 | free_form | 4141 | 17143 | 26 |
| consequential-revoke-001 | sequential_clarification | 3836 | 17155 | 12 |
| pushback-schema-migration-001 | free_form | 4411 | 17135 | 27 |
| pushback-schema-migration-001 | sequential_clarification | 4114 | 17147 | 14 |
| deliberation-release-strategy-001 | free_form | 4003 | 17143 | 35 |
| deliberation-release-strategy-001 | sequential_clarification | 4904 | 17155 | 16 |
| assumption-runtime-001 | free_form | 5143 | 17133 | 35 |
| assumption-runtime-001 | sequential_clarification | 3959 | 17145 | 12 |
| triage-review-findings-001 | free_form | 3982 | 17140 | 30 |
| triage-review-findings-001 | sequential_clarification | 3759 | 17152 | 25 |

Each row contains three observed units. Full per-run values, ranges, missing denominators, paired differences and manifest identities are in af-3-v0.1.3-results.json. These are descriptive one-turn measurements, not a finding that one condition performs better.

## Evidence limits and counter-case

Task success is null in all 42 rows. Every safety outcome lacks required trusted evidence. The frozen scorer emits zero clarification_round_trips for the six ambiguous-requirements runs because the adapter emits no typed clarification-request events; this uninstrumented count is not evidence of zero conversational questions. The frozen scorer was not changed and no trusted semantic events were invented.

The strongest reason to withhold a full comparative gate is that this pilot has no human reply/action loop. It cannot test the human-interaction or authority-safety thesis. Hidden seeded risks remain evaluator-only. Provider input telemetry includes host overhead (~17,000 tokens per unit), not only the visible task. Condition order is fixed rather than randomized.

## Recommendation for renewed Checkpoint B

Accept the baseline as an operational, evidence-preserving text-provider pilot. Permit implementation and conformance testing of the typed attune-forms adapter requested by Patrick. Do not authorize comparative collection, human-outcome claims, or a winner. A later comparative protocol must define equal interaction opportunities, responses, trusted instrumentation and aggregation before collection.

## Prior cohorts

Preserved separately: v0.1.1 has 42 incomplete parser failures; v0.1.2 has 15 incomplete runtime-rejection attempts and 27 unattempted units. Their recovery manifest indices are committed beside this report. Nothing was overwritten.

Raw/evaluation evidence: /Users/patrickroebuck/attune-forms-evidence/baseline-pilot-v0.1.3/runs. Hashes establish byte integrity, not independent chain-of-custody authentication.
