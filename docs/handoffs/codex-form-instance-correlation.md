# Form instance correlation handoff

## Goal
Pair overlapping displays correctly and expose the workspace telemetry API used
by the attune-ai companion change. Preserve action authority and legacy counts.

## State
Implementation and review are complete on `codex/form-instance-correlation`,
based on `cc94fc2`. This isolated checkout is owned by the paired latency task.

## Receipts
- 994 full-suite tests passed, including real MCP stdio collection and shipped
  JavaScript argument forwarding.
- All 57 changed executable Python lines covered in the final measurement.
- Pinned Black and Ruff passed; gpt-5.6-sol review has no remaining findings.
- The companion attune-ai change was exercised in four actual browser/MCP runs:
  baseline, batched, batched, baseline; identical seven synthetic candidates
  and terminal receipts; 20 accepted actions paired to exact render instances.
- Browser measurements and raw data live in attune-ai's
  `docs/probes/latency/`, with the paired task handoff in its `docs/handoffs/`.
  These measurements describe an isolated browser, not a native chat host.

## Next action
Review this PR, then publish an appropriately versioned forms release before
promoting the companion attune-ai integration and updating its dependency floor.
No release or merge is authorized by this handoff itself.
