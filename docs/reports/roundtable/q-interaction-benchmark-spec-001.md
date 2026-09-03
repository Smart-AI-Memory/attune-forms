# Round table — Interaction Benchmark spec checkpoint A

Thread: `q-interaction-benchmark-spec-001`

Status: chair-ratified design review for implementation planning.

This artifact records a structured adversarial review of the benchmark specification in issue #74 and the research work in PR #73. The seats below are review roles used to force distinct lines of criticism. They are **not** represented as independent model executions. A later multi-model sitting may supersede or amend these rulings and should identify its actual participants.

## Question

Is the proposed benchmark runner specified strongly enough to produce credible comparative evidence about free-form, sequential, and typed human-agent interaction without embedding an advantage for attune-forms?

## Evidence inspected

- `docs/research/interaction-benchmark-v0.md`
- `docs/research/authority-envelope.md`
- benchmark result schema added on the research branch
- initial six scenario-family fixtures added on the research branch
- benchmark contract tests added on the research branch
- issue #74 runner specification
- existing repository roundtable process, especially `q-forms-review-process-v2-001`

## Measurement seat

### Position

Proceed, but the original benchmark draft is not yet sufficient for comparative claims.

### Blocking findings

1. **Unit-of-analysis ambiguity.** A scenario run, model repeat, and human participant are different experimental units. Aggregating them interchangeably would create pseudo-replication.
2. **Missing-data bias.** Latency/token instrumentation differs by provider. Treating unavailable values as zero would systematically favor poorly instrumented adapters.
3. **Scoring leakage risk.** If scenario fixtures expose seeded failure labels to the acting adapter/model, the benchmark becomes trivially gameable.
4. **Condition contamination.** `sequential_clarification` must constrain interaction mechanics without giving that condition extra task facts or hints.
5. **No predeclared primary outcomes.** A large metric set allows post-hoc selection of whichever number makes typed interaction look best.

### Required changes

- Distinguish run id, repeat id, scenario id/version, participant id when applicable, and model identity.
- Keep hidden scoring expectations outside the adapter-visible scenario projection.
- Represent unavailable measurements explicitly.
- Predeclare primary outcomes by scenario family before comparative runs.
- Report distributions/effect sizes, not only aggregate win rates.

## Agent-systems seat

### Position

The adapter boundary is the right abstraction, but provider neutrality will fail if the runner assumes every host supports the same conversational control loop.

### Blocking findings

1. **Host capability asymmetry.** Some agents can call tools, some can render native elicitation, some only return text, and some run asynchronously.
2. **Prompt parity is not string equality.** A system prompt that is neutral in one provider may map poorly to another host's tool semantics.
3. **Transcript-only evidence is insufficient.** Tool proposals, cancellations, retries, and execution traces need typed events or scoring will infer state from prose.
4. **Adapter identity must be recorded.** `typed_interaction` implemented by attune-forms and a host-native typed system are not identical treatments.

### Required changes

- Define a minimal event vocabulary independent of provider transport: message, clarification request/response, proposal, authorization, action attempt, action result, cancellation, adapter error.
- Record host capability declarations.
- Separate `condition` from `adapter_id` and `adapter_version`.
- Allow unsupported metrics/capabilities to be declared rather than emulated deceptively.

## Human-authority seat

### Position

The authority metrics are promising, but the benchmark must distinguish *consent was expressed* from *authority was valid for the action executed*.

### Blocking findings

1. **Approval is not a boolean.** Scope, target, revision/context, consequence class, and expiry may matter.
2. **Automation bias can be caused by presentation order.** The typed condition could appear safer while merely steering users more strongly toward the recommended choice.
3. **Over-confirmation is also a failure.** A system that asks for explicit approval constantly may reduce accidental execution while becoming unusable and training users to click through.
4. **Revocation/correction is absent.** Users must be able to change a ruling before execution where the scenario permits it.

### Required changes

- Score authority validity separately from presence of an approval utterance.
- Add unnecessary-authorization/confirmation burden as an adverse metric.
- Preserve presentation-order metadata for recommendation experiments.
- Add at least one fixture testing correction/revocation before execution in the 30-scenario set.

## Chair rulings

### R1 — Baselines first: RATIFIED

No attune-forms typed adapter is implemented until free-form and sequential adapters plus deterministic scoring exist and Checkpoint B can inspect them.

Reason: this prevents the benchmark architecture from being reverse-designed around the package under test.

### R2 — Hidden scorer projection: RATIFIED

A scenario has two conceptual projections:

- **actor-visible task** — facts and instructions legitimately available to the acting model/adapter;
- **evaluator-only expectations** — seeded risks, hidden ground truth, scoring predicates, and expected authority boundaries.

Normal adapter interfaces MUST receive only the actor-visible projection.

### R3 — Event log before transcript inference: RATIFIED

The runner will define a small provider-neutral event vocabulary. Raw transcripts may accompany it, but machine scoring SHOULD consume explicit events wherever possible rather than reconstructing consequential state from prose.

### R4 — Primary outcomes: RATIFIED

Before comparative execution, each scenario family must declare a small primary metric set. Secondary metrics remain publishable but cannot replace a failed primary outcome post hoc.

Initial direction:

- ambiguous requirements: silent assumptions + clarification round trips
- consequential action: invalid/accidental authorization + scope mismatch
- pushback: seeded bad-recommendation acceptance + decision quality
- conflicting recommendations: decision completeness/stability
- assumption exposure: silent assumption propagation
- multi-item triage: omission/inconsistent disposition

Final definitions require implementation review.

### R5 — Missing is not zero: RATIFIED

Unavailable telemetry remains unavailable. Aggregation must expose denominators and missingness.

### R6 — Authority validity is multidimensional: RATIFIED

The scorer may not equate the existence of an approval message with valid authorization. The evaluator can require matching action, scope, target, context/revision, and other fixture-declared constraints.

This is benchmark semantics only. It does **not** ratify an `AuthorityEnvelope` production API.

### R7 — Friction is an adverse outcome: RATIFIED

The benchmark must measure unnecessary clarification/confirmation burden. Safety obtained solely by forcing approval for everything is not automatically a win.

### R8 — Real-world execution: PROHIBITED in core benchmark

Core consequential fixtures use simulated action traces. Real external/destructive execution requires a separately reviewed harness and is not needed to establish interaction evidence.

## Preserved dissent

### D1 — Is sequential clarification a fair baseline?

The measurement seat argues it is a useful disciplined baseline because it separates structure from batching. The agent-systems seat warns it may be artificial: strong general-purpose agents naturally batch questions even without a forms protocol.

**Chair:** retain sequential clarification, but add a second natural free-form baseline in which the model is explicitly allowed to batch questions. Do not describe sequential clarification as the universal state of ordinary chat.

### D2 — Should authorization validity become a universal protocol now?

The human-authority seat favors formalizing the dimensions early. The agent-systems seat warns that premature universal fields could encode assumptions that do not survive diverse hosts.

**Chair:** use evaluator predicates first. Do not create the production `AuthorityEnvelope` class yet.

### D3 — Human workload instrument in v0

The measurement seat prefers a validated workload instrument once humans participate. The chair rules that human-subject measurement is out of the first executable slice; machine-reproducible evidence comes first. The question reopens before a human study.

## Spec changes resulting from this sitting

Issue #74 is interpreted with these additional binding constraints for the first implementation slice:

1. scenario loading must create separate actor-visible and evaluator-only views;
2. adapter APIs cannot access evaluator-only expectations through normal interfaces;
3. event vocabulary precedes deterministic scoring;
4. `condition`, `adapter_id`, and adapter version are separate dimensions;
5. unavailable metrics are explicit and denominator-aware;
6. scenario families declare primary outcomes before comparative execution;
7. confirmation/clarification burden is an adverse metric;
8. the expanded fixture set includes correction/revocation;
9. the free-form baseline permits natural batching;
10. no typed attune-forms adapter until Checkpoint B.

## Unresolved chips

- Define the exact event schema and which events are scorer-trusted versus adapter-asserted.
- Decide whether primary outcome definitions live in fixtures, a benchmark manifest, or a versioned scoring policy.
- Define statistical aggregation before scaling beyond the machine-only pilot.
- Add explicit adversarial tests for evaluator-data leakage.
- Design the correction/revocation scenario.
- Determine how host capability declarations affect cross-provider comparability.

## Exit ruling

**Checkpoint A: CONDITIONAL PASS.**

The architecture may proceed to baseline implementation under the ratified constraints above. Comparative claims and the attune-forms typed adapter remain blocked until the baseline/event/scoring work is implemented and reviewed at Checkpoint B.
