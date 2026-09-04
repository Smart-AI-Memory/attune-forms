# AF-2 — scoring and evidence protocol freeze

Status: executing

Outcome: Freeze and test the benchmark scoring and evidence protocol before
any real provider baseline output is observed.

Done when:

- all six scenario families have versioned executable scoring rules;
- actor-asserted events cannot produce safety findings;
- missing required evidence remains null;
- a run protocol must identify provider, model, sampling controls, repeats,
  exclusions, missing-data handling, and falsification rules before collection;
- raw runs and later evaluations use separate append-only artifact bundles;
- every family has seeded pass/fail tests;
- Checkpoint B.1 records the evidence and remains chair-required until Patrick
  reviews the completed policy.

<tasks>
  <task id="AF2-1" title="Freeze scoring policy">
    <objective>Add a versioned machine-readable policy and schema covering all six families.</objective>
    <acceptance>Policy and fixture primary outcomes agree; policy validation rejects actor-asserted evidence.</acceptance>
  </task>
  <task id="AF2-2" title="Execute policy scoring">
    <objective>Score retained events through the frozen policy with explicit missingness.</objective>
    <acceptance>Every family has seeded passing and failing tests; missing evidence is null.</acceptance>
  </task>
  <task id="AF2-3" title="Freeze collection protocol">
    <objective>Define the pre-run provider/model/sampling declaration and its readiness gate.</objective>
    <acceptance>A draft protocol cannot run until chair-required fields are resolved and ratified.</acceptance>
  </task>
  <task id="AF2-4" title="Preserve append-only evidence">
    <objective>Write raw runs and later evaluations as separate immutable bundles with SHA-256 manifests.</objective>
    <acceptance>Second writes fail; all manifest entries verify; evaluation evidence references raw evidence.</acceptance>
  </task>
  <task id="AF2-5" title="Document and review">
    <objective>Publish operational definitions, evidence limits, traceability, and Checkpoint B.1.</objective>
    <acceptance>Documentation is fact-checked; B.1 does not claim ratification before chair review.</acceptance>
  </task>
</tasks>
