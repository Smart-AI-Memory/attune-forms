# Outcome experiment handoff

Branch: codex/outcome-experiment. PR #89, draft. Base: merged PR #88, 18dbe77.

The seven-scenario outcome loop, independent artifact/state judge, fully specified
control, costs, counterbalancing, sealed collector and descriptive reporter are
implemented. Patrick approved 72 units for outcome-pilot-v0.1, recorded in signed
collector commit 8506101.

The live cohort exposed a benchmark defect: all five completed security answers
identified SQL-001, but were rejected because the oracle required string IDs
without disclosing that shape. Collection was stopped with five completed units,
21 sealed calls and one interrupted call in a sixth unit. No collector/model
process remained after stopping. Original evidence is untouched. Manifest checks
and the defect are recorded in docs/specs/outcome-experiment/v0.1-stopped-cohort.json.
These scores cannot support task-performance comparisons. Use revision 8506101
for source-bound verification of that cohort; never resume or overwrite it.

The v0.2 correction exposes artifact schemas without expected answers, scores
schema validity separately, and ignores ID-list ordering while rejecting duplicate
IDs. The proposal remains 72 new units / at most 1,152 additional model calls. A
new approval is required for the replacement collection; no v0.2 call has run.

Verification: 54 focused tests and the full repository suite pass. Scripted
positive controls cover all 24 combinations; they are conformance, not model
performance evidence. See the versioned scripted receipt and plan for details.

Next: obtain approval for benchmarks/protocols/outcome-pilot-v0.2.json, then record
it in a signed clean revision and collect using the isolated CLI 0.153.4. Keep
original AF-3 and outcome-v0.1 evidence at
/Users/patrickroebuck/attune-forms-evidence unchanged. Windows CI must pass before
review completion. No merge has been authorized for PR #89.
