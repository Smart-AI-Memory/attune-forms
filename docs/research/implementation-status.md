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
- provider-neutral text-provider seam for real baseline execution
- initial fixtures covering all six scenario families
- correction/revocation consequential-action fixture
- contract tests for leakage, missing telemetry, event trust, baseline behavior, serialization, and failure retention
- Roundtable Checkpoint A specification review
- Roundtable Checkpoint B harness review
- acceptance-to-evidence record:
  [`af-1-evidence-record.md`](af-1-evidence-record.md)

## Current gate

Checkpoint B is **HARNESS PASS / EVIDENCE BLOCK**.

No typed attune-forms adapter may be added yet. Unit tests establish software behavior, not comparative human-agent evidence.

The unblock path is:

1. connect at least one real text-completion provider to the neutral `TextProvider` seam;
2. run the free-form and sequential baselines over the pilot fixtures;
3. retain raw transcripts/events and normalized JSONL results;
4. strengthen evaluator-derived family-specific scoring where required;
5. reconvene Checkpoint B on the actual baseline records;
6. only then implement the typed attune-forms condition.

Negative or inconvenient baseline results are retained. The benchmark is not permitted to optimize for an attune-forms win.
