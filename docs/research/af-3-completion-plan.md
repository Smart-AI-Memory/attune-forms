# AF-3 completion and successor collection proposal

## Verified starting point

At recovery on 2026-09-06, all 42 v0.1.1 and 15 v0.1.2 raw manifests verified at `/Users/patrickroebuck/attune-forms-evidence`. All are incomplete. v0.1.1 records CLI parser failures; v0.1.2 records server rejection requiring a newer Codex version for GPT-6 Astra. The remaining 27 v0.1.2 units were not collected. Preserve this stopped cohort and every attempted unit; do not overwrite or pool it with a successor.

## Approved successor

Protocol baseline-pilot-v0.1.3 uses isolated Codex CLI 0.153.4, unchanged GPT-6 Astra / medium / priority settings, frozen fixture and scoring policy, seven scenarios, two conditions, and three repeats (42 new units). Its exact local parser check passes. Actual model compatibility still requires the first retained call. No preliminary model call is permitted. Stop on a systemic provider failure, preserving the attempted unit and reporting unattempted units separately. No retries replace sealed units.

## Approved aggregation policy 0.1.0

- Descriptive pilot only: no significance claims, overall winner, or generalized human-performance claim.
- Partition by protocol, condition, scenario and metric. Never pool failed predecessor cohorts into the successor's performance metrics; report them separately in the collection history.
- For every metric report planned, attempted, observed and missing counts. Keep missing outcomes null; no imputation and no post-run exclusions.
- Report numerical observed values with median, min and max; report Boolean outcomes as true count / observed count. Preserve all individual rows.
- Pair conditions only by the same scenario and repeat. Report paired observed count and missing-pair count. Report paired differences only when both values exist; label these descriptive and retain the single-sided observations.
- Do not infer task completion, safety, human effort, clarification round trips, or approval from fluent text or token telemetry. This pilot contains one completion per unit and no actual human-response loop. Outcomes lacking the frozen policy's trusted evidence remain null.
- No new semantic scoring rules after seeing outputs. Apply only the frozen scoring policy and explicitly supported evidence.

## Checkpoint sequence

The chair approved the successor and aggregation proposal in this task. Collect and validate 42 records, then present the retained baseline results for renewed Checkpoint B. Typed-condition implementation follows that review; it does not imply authorization to collect a comparative cohort. Its conformance tests must distinguish valid form generation/validation from human interaction or outcome evidence.
