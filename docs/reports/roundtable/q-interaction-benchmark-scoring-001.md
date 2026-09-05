# Round table — Interaction Benchmark scoring checkpoint B.1

Thread: `q-interaction-benchmark-scoring-001`

Status: implementation reviewed; chair authorization required; collection
gate closed

Recorded: 2026-09-04 (America/New_York)

The seats below are structured review roles. They are not represented as
independent model executions.

## Question

Are the scoring and evidence controls complete enough for the chair to freeze a
provider-specific baseline protocol before any real baseline output is seen?

## Evidence inspected

- `benchmarks/policies/scoring-v0.1.json`
- `benchmarks/schema/scoring-policy.schema.json`
- `benchmarks/scoring.py`
- `benchmarks/protocols/baseline-pilot-v0.1.draft.json`
- `benchmarks/schema/run-protocol.schema.json`
- `benchmarks/protocol.py`
- `benchmarks/evidence.py`
- `benchmarks/schema/result.schema.json`
- AF-2 scorer, protocol, evidence, runner, and result-contract tests
- Checkpoint A and Checkpoint B reports

## Measurement seat

### Findings

- Every fixture primary outcome resolves to an executable rule under one of the
  six scenario-family policies.
- Pass/fail thresholds, reducers, directions, missingness, and allowed trust
  classes are recorded before collection.
- The policy is versioned and hashed independently of fixtures and adapters.
- Incomplete runs and missing required fields produce `null`, not a favorable
  zero or an automatic failure.
- Each family has seeded passing and failing tests.

### Remaining limits

- The seven-scenario set is a pilot, not the planned 30-scenario benchmark.
- No aggregation, uncertainty, effect-size, or multiple-comparison policy has
  been ratified.
- Seeded scorer tests prove implementation behavior, not the validity of an
  evaluator's factual judgment.

## Agent-systems seat

### Findings

- Collection cannot begin while protocol identity, provider identity, model
  identity, sampling controls, or Checkpoint B.1 is unresolved.
- Raw and evaluator evidence occupy separate append-only bundles.
- Exact prompts, transcripts, events, result JSONL, protocol and scorer
  snapshots, environment metadata, and manifests are retained.
- A raw run id is fixed by scenario, condition, and repeat; a failed run cannot
  be overwritten by rerunning the same experimental unit.
- Trusted action evidence must identify a simulated trace. Core collection
  cannot perform a real external action.

### Remaining limits

- `TextProvider` still has no selected real provider implementation.
- AF-2 does not prove prompt or tool-access parity in a live host.
- An interrupted reserved path is retained as incomplete and requires a new
  protocol or repeat identity; the implementation does not repair it in place.

## Human-authority seat

### Findings

- Actor assertions cannot be named as trusted inputs by the policy.
- Accidental authorization, scope mismatch, and stale-context execution remain
  separate findings.
- Semantic absence is not treated as proof: silent assumptions require an
  evaluator-derived count.
- Unnecessary confirmation remains adverse rather than safety credit.
- Corrections are new evaluations; raw evidence is not rewritten.

### Remaining limits

- The evaluator procedure still needs a retained implementation identity for
  each real run. The bundle requires that SHA-256 but AF-2 does not choose the
  evaluator implementation for AF-3.
- Machine fixtures do not establish human comprehension, workload, consent, or
  trust calibration.
- Manifest integrity is not a complete legal chain of custody.

## Review rulings

### R1 — Executable policy: PASS

Policy version `0.1.0` covers all six families and fails closed on missing or
conflicting required evidence.

### R2 — Trust boundary: PASS

Actor-asserted fields are retained but cannot support a scored outcome. Safety
findings are runner-observed or evaluator-derived under the frozen policy.

### R3 — Evidence layout: PASS

Raw runs and later evaluations have separate append-only paths, exact-file
manifests, and explicit references from an evaluation to the raw manifest and
scoring-policy identity.

### R4 — Comparative claims: BLOCKED

No baseline output, aggregation rule, or effect estimate exists. AF-2 supports
future collection only; it establishes no product advantage.

### R5 — Typed attune-forms adapter: REMAINS BLOCKED

The Checkpoint A and B sequence remains binding. Typed-adapter implementation
waits until real free-form and sequential records survive renewed Checkpoint B
review.

## Preserved dissent

### D1 — Can absence in a complete event stream score zero?

For mechanically recorded clarification requests, yes: a complete runner stream
with no request is an observed count of zero. For semantic findings such as a
silent assumption, no: the evaluator must state the count. Incomplete streams
produce `null` for both.

### D2 — Should an interrupted run id be reusable?

No. Reuse would make it possible to replace inconvenient or failed evidence.
The partial directory remains, fails manifest verification, and prevents reuse.

## Checkpoint B.1 chair field

**Ruling: CHAIR_REQUIRED / COLLECTION BLOCKED.**

This is not an authorization to collect. The provider, provider API version,
model, model version, sampling settings, authorizing chair, and authorization
timestamp remain blank in the draft protocol. Recording
`COLLECTION_AUTHORIZED` before those values are reviewed would be false.

Once the chair supplies those values and ratifies the unchanged fixture,
scoring-policy hash, two conditions, three repeats, exclusions, missing-data
rules, falsification rules, and evidence layout, the protocol may be amended in
a new signed commit. No provider call or baseline output may precede that
commit.
