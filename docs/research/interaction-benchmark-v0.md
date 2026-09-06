# Attune Interaction Benchmark v0

Status: AF-3 baseline collected under approved v0.1.3; renewed Checkpoint B accepted for typed implementation/conformance

See `af-3-v0.1.3-review.md` for measured results and limits.

## Thesis

Typed human-agent interaction should reduce ambiguity and consequential-action errors without imposing unacceptable interaction cost.

This benchmark is designed to test that claim rather than assume it.

The benchmark MUST remain runnable without attune-forms so that attune-forms does not become the judge of its own design.

## Conditions

The complete benchmark is intended to compare three interaction conditions
using the same task, model family, tool permissions, context, and success
criteria. The baseline pilot collects the first two conditions before the typed
condition is implemented.

1. **Free-form chat** — the agent uses ordinary conversational text and may ask questions however it chooses.
2. **Sequential clarification** — the agent asks one explicit clarification at a time before proceeding.
3. **Typed interaction** — the agent uses a declared interaction contract with validated responses. attune-forms is one implementation of this condition, not part of the metric definition.

A fourth optional condition may test a host-native structured interaction system when available.

## Scenario families

### 1. Ambiguous requirements

The task contains several independent missing decisions, such as scope, depth, target environment, and acceptable risk.

Primary question: does batching independent decisions reduce clarification turns without increasing incorrect assumptions?

### 2. Consequential actions

The agent may perform an irreversible, destructive, externally visible, costly, or security-relevant action.

Primary question: does explicit structured authorization reduce accidental or over-broad approval?

### 3. Agent pushback

The user's initial approach contains a material weakness and the agent has a defensible alternative.

Primary question: can the agent surface disagreement without either steamrolling the user or collapsing into passive compliance?

### 4. Conflicting recommendations

Two or more reviewers, models, or analysis passes support different options.

Primary question: does a deliberation artifact improve the user's ability to inspect disagreement and make a stable ruling?

### 5. Assumption exposure

The agent can infer missing facts from context, but one or more inferred facts are wrong or materially uncertain.

Primary question: does explicit assumption review reduce silent assumption propagation?

### 6. Multi-item triage

The user must rule on multiple independent findings, review comments, or proposed changes.

Primary question: does structured triage reduce omission and inconsistent disposition?

## Core metrics

Metrics are captured per scenario and aggregated by condition.

### Efficiency

- clarification round trips
- total human turns
- elapsed task time
- total model tokens
- interaction payload size

### Correctness

- task completion rate
- invalid or ambiguous human responses
- silently accepted assumptions
- omitted required decisions
- incorrect execution caused by misunderstood intent
- post-execution correction rate

### Authority safety

- accidental approval rate
- approval scope mismatch
- execution after stale approval
- execution without explicit authorization where authorization was required
- authorization reuse outside its original scope

### Decision quality

- rate of accepting an objectively inferior recommendation in seeded scenarios
- decision reversal after evidence is revealed
- consistency across equivalent presentations
- completeness of multi-item rulings

### Human factors

- perceived effort
- perceived clarity
- confidence in the final decision
- trust calibration: confidence relative to actual correctness

A short post-task instrument SHOULD be used. NASA-TLX or another established workload instrument may be used where appropriate, but the benchmark core MUST not depend on proprietary scoring.

## Pushback / automation-bias experiment

Pushback is tested separately because visible recommendations may improve clarity while also increasing automation bias.

Use the same underlying decision with four presentations:

1. neutral options only
2. AI-recommended option identified
3. AI recommendation plus rationale
4. AI recommendation plus rationale plus explicit counterargument / tradeoff

Seed a controlled subset with an incorrect AI recommendation.

Measure:

- incorrect recommendation acceptance rate
- time to decision
- confidence
- later reversal when ground truth is shown
- rate at which users inspect alternatives

The desired result is not maximum agreement with the agent. The desired result is calibrated reliance.

## Experimental controls

For a comparison to count as evidence:

- identical task facts and tool access across conditions
- randomized condition order where human participants are involved
- model and version recorded
- temperature / sampling configuration recorded when controllable
- prompts and interaction transcripts retained in a reproducible format
- seeded failure cases declared before scoring
- success criteria declared before observing results
- missing data reported rather than silently dropped

For model-to-model comparisons, report the interaction effect separately from the model effect.

## Minimum viable benchmark

The first publishable benchmark can be small.

Target:

- 6 scenario families
- 5 scenarios per family
- 30 scenarios total
- 3 interaction conditions
- at least 3 repeated model runs per scenario-condition pair for machine-only measures

This yields 270 runs before optional human-subject evaluation.

The first release SHOULD emphasize reproducibility over headline statistics.

## Machine-readable result schema

Each evaluated run emits a record under
[`result.schema.json`](../../benchmarks/schema/result.schema.json). The example
below is illustrative structure, not an observed result:

```json
{
  "benchmark_version": "0.1",
  "scoring_policy_version": "0.1.0",
  "scenario_id": "ambiguous-security-audit-001",
  "scenario_family": "ambiguous_requirements",
  "condition": "free_form",
  "adapter_id": "baseline/free-form",
  "adapter_version": "0.1",
  "model": "provider/model-version",
  "repeat_id": "r1",
  "host_capabilities": {
    "tools": true,
    "native_structured_input": false,
    "token_telemetry": false,
    "latency_telemetry": false
  },
  "primary_outcomes": {
    "silent_assumptions": 0,
    "clarification_round_trips": 1
  },
  "missing_primary_outcomes": [],
  "primary_outcomes_pass": true,
  "clarification_round_trips": 1,
  "task_success": true,
  "silent_assumptions": 0,
  "accidental_approval": null,
  "scope_mismatch": null,
  "stale_approval_execution": null,
  "unnecessary_confirmations": 0,
  "tokens_input": null,
  "tokens_output": null,
  "elapsed_ms": null,
  "incomplete": false,
  "error": null,
  "notes": ["token telemetry unavailable", "latency telemetry unavailable"]
}
```

The schema is intentionally independent of attune-forms internals.

## What would falsify the thesis?

The project should explicitly accept evidence against its preferred design.

The thesis is weakened if typed interaction:

- produces no meaningful reduction in ambiguity or consequential errors,
- materially increases time or cognitive load for ordinary tasks,
- creates recommendation bias greater than the errors it prevents,
- performs worse than simpler sequential clarification on most task families,
- or only shows gains when attune-forms itself defines the scoring rules.

A negative result should change the product design, not be explained away.

## Initial implementation sequence

1. Freeze benchmark vocabulary, result schema, and the seven-scenario pilot.
2. Implement the neutral runner, free-form baseline, and sequential baseline.
3. Freeze executable scoring and append-only evidence controls.
4. Ratify a provider-specific baseline protocol before observing output.
5. Collect and evaluate the two baselines, then renew Checkpoint B.
6. Expand toward 30 vendor-neutral scenarios and define aggregation.
7. Implement typed interaction through attune-forms only after the baseline gate.
8. Add human-subject evaluation only after the machine-reproducible core is stable.

## Publication rule

Published claims must distinguish:

- **conformance evidence** — whether a renderer or host preserves the interaction contract;
- **software correctness evidence** — whether validation and state handling behave as specified;
- **behavioral evidence** — whether the interaction improves human-agent outcomes.

Passing one category must never be presented as proof of another.
