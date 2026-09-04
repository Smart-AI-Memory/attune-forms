# Interaction benchmark evidence protocol v0.1.0

Status: implemented; Checkpoint B.1 chair decision required

Recorded: 2026-09-04 (America/New_York)

## Current ruling

The collection gate is closed. The draft protocol at
[`baseline-pilot-v0.1.draft.json`](../../benchmarks/protocols/baseline-pilot-v0.1.draft.json)
has no provider, API version, model, model version, sampling controls, chair,
or authorization timestamp. Its current SHA-256 is
`a3f95fbf4031ac6bf8b998a90b84a743befbe86a800c23021e2081c11deaa35c`.

The readiness check in
[`protocol.py`](../../benchmarks/protocol.py) rejects collection until those
fields are concrete, the protocol status is `ratified`, and Checkpoint B.1 says
`COLLECTION_AUTHORIZED` with an identified chair and timestamp.

## Frozen inputs

The draft binds collection to these independent identities:

- benchmark version `0.1`;
- seven-scenario fixture SHA-256
  `3f8b92820c55a598b0f61e1d090f68790da7b3114cb08e51b135059e1d5c49d7`;
- scoring-policy version `0.1.0` and SHA-256
  `7d7501c349f6a658277afe9c93c55e51a18a9658b6f22206435cccd7c6279d93`;
- free-form adapter `baseline/free-form` version `0.1`;
- sequential adapter `baseline/sequential-clarification` version `0.1`;
- three repeats per scenario-condition pair; and
- execution order `scenario_condition_repeat`.

With seven scenarios, two baseline conditions, and three repeats, a complete
pilot contains 42 raw run bundles. No post-run exclusion is permitted.
Incomplete runs remain in the evidence set.

The protocol predeclares six falsification rules. They block collection after a
fixture or policy hash change, mark mismatched paired conditions contaminated,
preserve missing primary outcomes as `null`, invalidate a policy whose seeded
tests fail, prohibit real external actions, and prohibit comparative claims
before an aggregation policy and renewed Checkpoint B review.

## Append-only layout

[`evidence.py`](../../benchmarks/evidence.py) writes this hierarchy:

```text
<evidence-root>/
└── <protocol-id>/
    └── runs/
        └── <scenario-id>--<condition>--<repeat-id>/
            ├── raw/
            │   ├── environment.json
            │   ├── events.jsonl
            │   ├── prompts.json
            │   ├── protocol.json
            │   ├── run.json
            │   ├── transcript.json
            │   └── manifest.sha256
            └── evaluations/
                └── <scoring-policy-version>/
                    └── <evaluation-id>/
                        ├── evaluation.json
                        ├── evaluator-events.jsonl
                        ├── results.jsonl
                        ├── scoring-policy.json
                        └── manifest.sha256
```

The raw bundle is sealed before evaluation. It may contain actor-asserted and
runner-observed events, but no evaluator-derived event. A later evaluation
bundle may add one consolidated evaluator-derived event of each permitted kind
and records the raw manifest digest it evaluated.

Every final bundle path is reserved with an exclusive directory creation.
Writing the same raw experimental unit or evaluation id twice fails. The
manifest is installed last. If a process is interrupted after path reservation,
the partial target remains visibly incomplete and the path cannot be reused.

Each manifest lists every regular file in that bundle except the manifest
itself. Verification rejects a malformed manifest, duplicate entry, missing or
extra file, symlink, directory, or content-digest mismatch.

## Collection invariants

Before a raw bundle can be written, the implementation checks all of the
following:

- Checkpoint B.1 and every protocol field pass preflight;
- the live protocol, fixture, and scoring policy still match their retained
  SHA-256 identities;
- scenario, family, condition, adapter, model, and repeat match the protocol;
- the effective prompt contains the retained actor task exactly;
- evaluator-derived events are absent;
- trusted action traces are explicitly marked `simulated: true`;
- the runner environment records operating system, architecture, Python
  version, a full Git commit id, and a clean worktree; and
- collection and evaluation timestamps include a UTC offset.

Before an evaluation bundle can be written, the raw manifest is reverified,
the raw protocol snapshot must match the active protocol byte-for-byte, the
retained fixture scenario must match, and the evaluator and scoring-policy
identities must be complete.

## Correction and preservation

Do not edit a sealed raw or evaluation bundle. A corrected interpretation is a
new evaluation id. A changed source rule or threshold is a new scoring-policy
version. A changed fixture, adapter, provider configuration, repeat count, or
collection rule is a new run-protocol version.

Preserve the raw bundle, every evaluation bundle, both manifests, the Git
commits containing the implementation and protocol, and the external provider
receipt where one exists. A later export should verify every manifest before
copying and again after copying.

## Evidentiary limits

SHA-256 manifests make later file changes detectable under current assumptions;
they do not prevent alteration. The implementation does not provide WORM
storage, third-party timestamping, access logs, custody-transfer signatures, or
an opinion on legal admissibility. Git signatures authenticate commits only to
the extent that the signing key, verification environment, and custody of that
key are independently established.

No real provider output has been collected under this protocol. The files and
tests currently establish protocol behavior, not behavioral results.
