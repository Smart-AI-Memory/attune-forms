# Round table — Interaction Benchmark baseline checkpoint B

Thread: `q-interaction-benchmark-baseline-001`

Status: implementation review; comparative-evidence gate remains closed.

This checkpoint reviews the baseline harness added under issue #74 / draft PR #73. The seats are structured review roles, not claims of independent external model executions.

## Question

Are the free-form and sequential-clarification baselines implemented fairly enough to allow an attune-forms typed-interaction adapter to be added without contaminating the experiment?

## Evidence inspected

- `benchmarks/runner.py`
- `benchmarks/fixtures/scenarios-v0.json`
- `benchmarks/schema/result.schema.json`
- `tests/test_interaction_benchmark_contract.py`
- `tests/test_interaction_benchmark_runner.py`
- `tests/test_interaction_benchmark_result_contract.py`
- Checkpoint A rulings in `q-interaction-benchmark-spec-001.md`

## Measurement seat

### Position

The harness is materially improved, but this is not yet baseline *evidence* in the scientific sense.

### Positive findings

- Actor-visible and evaluator-only projections are separated in the persisted fixtures.
- The runner passes only `ActorScenario` to adapters/actors.
- Missing token/latency telemetry remains `null` and is explicitly noted.
- Failed/incomplete runs remain representable and cannot score task success.
- Result JSONL records condition identity separately from adapter identity/version.
- Primary outcomes are declared per scenario family before comparative execution.

### Blocking findings

1. No real model/provider baseline runs have been recorded yet.
2. The deterministic scorer currently trusts generic event payload claims such as `scope_valid` and `context_valid`; provenance/trust boundaries for scorer-consumed fields are not yet formalized.
3. The current scorer defines task success mostly from action-result and authority events; family-specific primary outcomes are declared but not yet all computed.
4. No aggregation/effect-size layer exists yet, so comparative claims would be premature even if runs existed.

## Agent-systems seat

### Position

The adapter boundary is sufficient for baseline implementation, but not yet for cross-provider execution.

### Positive findings

- Free-form explicitly permits batched clarification.
- Sequential clarification enforces one decision id per request event, making its treatment mechanically distinct.
- Core benchmark modules import no `attune_forms` runtime code.
- Condition, adapter id, adapter version, model, and repeat id are retained independently.

### Blocking findings

1. There is no concrete provider actor adapter yet, so prompt/capability parity cannot be inspected.
2. Host capability declarations are not yet represented in `RunArtifact`.
3. Adapter failures raised as exceptions need a runner-level capture path so they remain dataset rows rather than aborting a suite.
4. Event-source trust is only a string today; the scorer cannot distinguish adapter assertion from runner-observed execution evidence.

## Human-authority seat

### Position

The benchmark now treats authorization failure as multidimensional and includes a correction/revocation scenario, but it still needs stronger evidence semantics.

### Positive findings

- `scope_mismatch`, stale-context execution, accidental approval, and unnecessary confirmations are separate metrics.
- Unnecessary confirmation is explicitly adverse rather than counted as safety success.
- The fixture set now includes a correction/revocation case where an earlier approval becomes superseded before execution.
- Typed interaction remains blocked, so authority semantics have not been reverse-fit to attune-forms.

### Blocking findings

1. The revocation fixture exists but the scorer does not yet have a first-class supersession/revocation rule.
2. `AUTHORIZATION` event payload booleans can currently assert their own validity; evaluator-owned predicates should determine validity.
3. No presentation-order metadata exists yet for the later automation-bias experiment.

## Chair rulings

### R1 — Baseline architecture: PASS

The actor/evaluator split, two baseline adapters, event log, missing-data representation, failure retention, and JSONL contract are sufficiently sound to continue baseline infrastructure work.

### R2 — Comparative baseline evidence: NOT YET ESTABLISHED

Unit tests and deterministic actors prove software behavior, not behavioral outcomes. No claim may state that free-form or sequential interaction performs better or worse until real model runs are captured.

### R3 — Typed attune-forms adapter: REMAINS BLOCKED

Checkpoint A required baseline evidence before typed-interaction implementation. This checkpoint does not waive that requirement.

The next unblock condition is:

1. add a concrete provider-neutral actor interface/adapter capable of producing real baseline runs;
2. capture baseline records for at least the pilot fixture set;
3. formalize scorer trust so authority validity is evaluator-derived or runner-observed rather than self-certified by the acting adapter;
4. rerun Checkpoint B on those records.

### R4 — Event trust boundary: NEW BINDING REQUIREMENT

Future scorer-consumed fields are classified as one of:

- **runner-observed** — generated by harness behavior (timing, adapter error, action trace from the simulator);
- **actor-asserted** — emitted by the model/adapter and never sufficient alone for safety success;
- **evaluator-derived** — computed from evaluator-only expectations against runner-observed evidence.

Authorization validity MUST ultimately be evaluator-derived from action/context evidence, not accepted from actor assertions.

### R5 — Suite exceptions must become rows

The runner must catch adapter/provider failures at suite boundaries and retain an incomplete/error artifact instead of silently aborting later scenarios.

### R6 — Family-specific scoring required before claims

Declared primary outcomes are a preregistration step, not implementation. Comparative publication remains blocked until each primary outcome used in a claim has an executable scorer or clearly documented human-evaluation procedure.

## Preserved dissent

### D1 — Should typed adapter implementation proceed in parallel behind a feature flag?

The agent-systems seat argues parallel implementation could save time if no results are examined. The measurement seat argues its presence would still exert architecture pressure on the supposedly neutral core.

**Chair:** reject parallel typed-adapter implementation for now. The cost of waiting is smaller than the credibility cost of reverse-design suspicion.

### D2 — Are adapter-asserted events useful?

Yes for transcript normalization and debugging; no as sole proof of safety. Preserve them but tag their trust class.

## Resulting work order

1. Introduce event trust classification and runner-observed failure events.
2. Capture suite exceptions as incomplete artifacts.
3. Add host/provider capability metadata.
4. Implement a concrete baseline actor/provider seam without importing attune-forms.
5. Run the pilot baseline fixtures and retain raw JSONL.
6. Re-open Checkpoint B with actual run evidence.
7. Only then begin the typed attune-forms adapter.

## Exit ruling

**Checkpoint B: HARNESS PASS / EVIDENCE BLOCK.**

The baseline harness may continue. The typed-interaction adapter and comparative claims remain blocked pending actual baseline runs and stronger scorer trust semantics.
