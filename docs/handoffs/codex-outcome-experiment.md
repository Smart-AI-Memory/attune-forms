# Outcome experiment handoff

Branch: codex/outcome-experiment. Base: merged attune-forms PR #88, 18dbe77.

Implemented the user-authorized seven-scenario outcome loop, independent artifact
and sandbox-state judge, fully specified deployment control, cost telemetry,
condition-order counterbalancing, source-bound protocol, per-turn append-only
collector and descriptive reports. No comparative model call has been made.

Verification: 1,212 repository tests passed. Forty-five focused tests cover the
new experiment; the collector, loop, judge and report have at least 90% coverage
in their focused runs. The scripted probe completed 24 scenario/condition/control
combinations, all passing their defined oracle. These are conformance controls,
not evidence that any model or interface performs better. The dry run produced
72 units with an upper bound of 1,152 model calls. Pinned checks passed.

Next action: obtain explicit approval for outcome-pilot-v0.1 in
benchmarks/protocols/outcome-pilot-v0.1.json (currently chair_required). Then record
the ruling, freeze a signed clean collector commit, and run using the isolated
Codex CLI 0.153.4 and an empty neutral workspace. Never replace partial or failed
units. The prior AF-3 evidence remains at
/Users/patrickroebuck/attune-forms-evidence and must not be modified.

See docs/specs/outcome-experiment/plan.md for scope, metrics, fairness controls,
commands and limits. Human effort/abandonment remain null; the deterministic
simulator is not a human study. Approval to build this experiment did not supply
a concrete budget for its comparative collection.
