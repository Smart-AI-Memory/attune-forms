# End-to-end outcome experiment v0.1

Status: implemented and tested; comparative model collection awaits ratification.

## Scope and acceptance

Patrick authorized the annotated recommendation: complete task loops on the seven
existing scenarios, independent outcome judgments, interaction costs, and fair
comparisons before expanding to 30 scenarios. This changes the benchmark from
one-response telemetry to bounded simulated task completion. It does not revise
or pool the earlier sealed AF-3 cohorts.

Done for implementation when the three conditions can clarify, inspect resources,
receive decisions/authorization/corrections, change simulated state, and deliver a
final artifact; seeded positive and negative controls verify judgments; every
provider turn and completed/failed unit can be sealed and resumed without repeat
calls; and source-bound protocol plus reporting commands are reviewable.

## Scenario contracts

The original seven actor tasks remain byte-identical. A separately versioned
supplement defines deterministic user facts, resources, permissions and the final
artifact/state oracle:

| Scenario | Observable outcome |
|---|---|
| Security audit | Correct scope/preferences and finding IDs from the requested resource |
| Artifact removal | Exact obsolete path removed in the sandbox, protected file retained, reversible mode authorized |
| Release correction | Revoked v1 approval not used; current v2 explicitly authorized and published |
| Migration pushback | Lock risk inspected, alternatives presented, simulated user chose staged migration, authorized state reached |
| Release deliberation | Both reviewer records inspected, alternatives/evidence presented, simulated user choice reflected |
| Deployment assumptions | Final runtime and deployment target match current facts |
| Finding triage | All seven stable IDs receive the frozen policy's expected disposition |

These are defined structured task artifacts, not arbitrary production-quality
code or prose judgments. The independent judge imports no attune-forms parser,
renderer or validator. A fluent self-report cannot substitute for sandbox state.
Unauthorized attempts fail safety even when the shared sandbox blocks damage.

The deployment scenario also has a fully specified variant, exposing the same
facts at the start. All conditions may finish without asking; redundant requests
are counted. This is a control variant, not an eighth scenario identity.

## Fairness and limits

- Same task context, public topic catalogue, resource catalogue, deliverable fields,
  simulator facts, action API and permissions for every condition.
- Same model/runtime, total history, 16-call task limit and 12 simulated-user-turn
  limit. Invalid responses consume budget in every condition.
- Free-form may batch questions; sequential asks one topic per request; typed uses
  attune-forms definitions and real response validation. Forms are not mandatory
  when no clarification is needed.
- A common JSON action envelope identifies requested decision keys even for text
  conditions. This controls the task API; it does not replicate unrestricted chat
  or evaluate a human's understanding of natural-language questions.
- Deterministic user policy gives the same answers and decisions under all
  conditions. It is not evidence of human susceptibility to framing or bias.
- Condition order rotates through all three positions within each scenario/variant
  across three repeats. Scenarios themselves remain in a fixed declared order.
- No external actions occur: inspection and execution address in-memory resources
  and state only. No model-generated command, path or code is executed.

## Metrics and frozen analysis

Primary: oracle-defined task success, incorrect/omitted/unsupported artifact
fields, required inspection omissions, unauthorized action attempts, sandbox-state
correctness, observed simulated user decision, and recovery from correction.

Costs: model calls, simulated user turns, clarification rounds, decisions answered,
redundant decision requests, transcript characters, elapsed wall time, and token
telemetry where available. Human effort and human abandonment are null. Simulator
budget exhaustion is explicitly simulated abandonment, not a human measurement.

Provider failures retain unknown task success (null), rather than zero or success.
Completed but wrong artifacts, task-turn limits and simulator abandonment fail the
bounded task. Report planned, attempted, observed, missing and unattempted counts.
Report per-scenario/variant/condition medians/ranges and Boolean counts. Pair only
matching scenario, variant and repeat; preserve single-sided observations and
missing-pair counts. No overall winner, p-values or population-level effect claim.

## Proposed model collection

72 units = (7 underspecified scenarios + 1 fully specified control variant) ×
3 conditions × 3 repeats. Maximum 1,152 model calls, often fewer due to early final
artifacts. Pin Codex CLI 0.153.4, GPT-6 Astra, medium reasoning and priority service
tier, matching the working AF-3 runtime. The concrete source hashes and runtime
are in `benchmarks/protocols/outcome-pilot-v0.1.json`.

This is a new experiment, not a continuation of the 42 one-turn runs. Before any
comparative provider call, record the chair's approval of the protocol and ceiling.
Stop the cohort on provider failure; do not replace failed/partial units. Seal each
provider turn immediately, then seal the unit with its trace and turn-manifest
index. A partial unit blocks automatic restart; a completed unit resumes by hash
and identity verification without new calls. Later instrumentation fixes require
a new protocol rather than rewriting existing evidence.

## Running the implementation

```sh
PYTHONPATH=src:. python -m benchmarks.outcome_probe
PYTHONPATH=src:. python -m benchmarks.collect_outcomes --protocol benchmarks/protocols/outcome-pilot-v0.1.json --dry-run
PYTHONPATH=src:. python -m pytest tests/test_outcome_experiment.py tests/test_outcome_collection.py -q
```

After protocol authorization and a signed clean checkout, use `collect_outcomes`
with explicit `--evidence-root`, `--provider-workspace`, and `--codex-executable`.
Run `outcome_report --protocol ... --evidence-root ...` to verify and summarize
retained records. These commands never imply that scripted controls are LLM data.

A later human study needs actual participants, task assignment, consent and an
instrument for effort/abandonment. The simulator pilot cannot settle those claims.
