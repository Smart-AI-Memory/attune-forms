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

Checkpoint B.1 is **CHAIR_REQUIRED / COLLECTION BLOCKED**.

No provider run has been made under the AF-2 protocol. No typed attune-forms
adapter may be added yet. Unit tests establish software behavior, not
comparative human-agent evidence.

The unblock path is:

1. record a provider, provider API version, model, model version, and every
   sampling control or explicit unavailability reason;
2. obtain the chair's Checkpoint B.1 authorization in the protocol before any
   provider call;
3. connect that provider to the neutral `TextProvider` seam;
4. collect 42 append-only raw bundles: seven pilot scenarios, two baseline
   conditions, and three repeats;
5. append evaluator-derived events and policy-versioned JSONL results without
   changing raw evidence;
6. ratify aggregation rules and reconvene Checkpoint B on the retained records;
7. only then implement the typed attune-forms condition.

Negative or inconvenient baseline results are retained. The benchmark is not permitted to optimize for an attune-forms win.
