# Interaction benchmark implementation status

## Implemented

- actor-visible / evaluator-only scenario split
- vendor-neutral result schema
- provider-neutral event vocabulary
- event trust classes: actor-asserted, runner-observed, evaluator-derived
- free-form baseline adapter
- sequential-clarification baseline adapter
- resilient suite execution that retains adapter/provider failures as incomplete rows
- host capability metadata
- JSONL result serialization
- independently versioned executable scoring policy for all six scenario families
- scorer trust enforcement: actor assertions cannot support scored outcomes
- explicit `null` handling for incomplete runs and missing primary evidence
- pre-run protocol schema and fail-closed collection readiness gate
- frozen fixture and scoring-policy SHA-256 identities
- separate append-only raw-run and policy-versioned evaluation bundles
- exact-file SHA-256 manifest creation and verification
- seeded passing and failing scorer cases for every scenario family
- provider-neutral text-provider seam for real baseline execution
- initial fixtures covering all six scenario families
- correction/revocation consequential-action fixture
- contract tests for leakage, missing telemetry, event trust, baseline behavior, serialization, and failure retention
- Roundtable Checkpoint A specification review
- Roundtable Checkpoint B harness review
- acceptance-to-evidence record:
  [`af-1-evidence-record.md`](af-1-evidence-record.md)
- scoring definitions:
  [`scoring-policy-v0.1.md`](scoring-policy-v0.1.md)
- evidence collection and preservation protocol:
  [`evidence-protocol-v0.1.md`](evidence-protocol-v0.1.md)
- Roundtable Checkpoint B.1 scoring review:
  [`q-interaction-benchmark-scoring-001.md`](../reports/roundtable/q-interaction-benchmark-scoring-001.md)

## Current gate

AF-3 successor baseline-pilot-v0.1.3 has 42 complete raw units and 42 sealed
observed-only evaluations. Manifest verification, exact prompt/runtime checks,
and the approved descriptive aggregation are recorded in
[the baseline review](af-3-v0.1.3-review.md).

Renewed Checkpoint B was accepted for typed-adapter implementation and
conformance tests only. `benchmarks/typed_forms.py` now provides the typed actor
and adapter through the existing attune-forms parser and answer validator.
Twenty-two conformance tests cover all seven actor scenarios and terminal,
invalid, stale, default-injection and forged-provenance cases. No comparative collection or
human-performance/safety claim is supported by this one-turn pilot.

Prior failed cohorts remain preserved and separately reported. The original
AF-2 "collection blocked" status was superseded by the recorded B.1 rulings.

## Next outcome experiment

The user-authorized end-to-end simulator is implemented in
`benchmarks/outcome_loop.py`, with an independent oracle, fully specified control,
source-bound protocol and per-turn evidence collection. Its specification and
scripted conformance evidence are in `docs/specs/outcome-experiment/`.
Comparative model collection awaits approval of the concrete 72-unit protocol;
there are no model-performance findings from this new experiment yet.

The approved outcome-pilot-v0.1 was stopped after five completed units and one
interrupted call because its undisclosed findings shape invalidated task scoring.
Evidence is retained; these are not comparative findings. The corrected v0.2
proposal exposes artifact schemas and treats ID-list order as immaterial. A
replacement collection awaits explicit approval; see the outcome experiment plan.
