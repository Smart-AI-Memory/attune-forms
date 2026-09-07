# Outcome experiment handoff

Branch: codex/outcome-experiment. Draft PR #89. No merge authorization.

Patrick authorized auditing the scorer then running the corrected 72-unit pilot.
The 26-case audit found and fixed hidden decision-alternative ordering. Full
suite: 1,247 passed. All CI checks at collector f623590 passed, including Windows.

Outcome-pilot-v0.2 completed: 72 units, 288 model calls, all task success checks
passed. All 72 raw and 288 turn bundles verified against manifests, exact unit and
protocol bytes, and retained call data. A scorer replay without condition labels
matched all outcomes. No provider failures or missing units. The frozen protocol,
source hashes and collector commit are recorded in the verification receipt.

The result is a task-success ceiling, not evidence of a forms advantage. Typed
and free-form median calls matched in every group. The fully specified control
finished in one call without clarification in all nine runs. Human UI outcomes
were not measured. See docs/specs/outcome-experiment/outcome-pilot-v0.2-results.md
and its report/verification JSON files for conclusions and exact evidence.

Original v0.1 evidence remains untouched and excluded (five completed units,
21 sealed calls, one interrupted call); its undisclosed output shape invalidated
scoring. All raw evidence remains in
/Users/patrickroebuck/attune-forms-evidence. Never replace retained units.

Next: review PR #89 and the pilot findings. A follow-on needs representative fresh
tasks and an actual-user comparison before any product-wide benefit claim.
No further collection, human study or merge has been authorized.
