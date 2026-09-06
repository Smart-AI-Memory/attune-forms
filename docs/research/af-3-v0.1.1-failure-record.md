# AF-3 baseline-pilot-v0.1.1 failure record

Status: 42 attempted; 42 retained incomplete; no run id reusable

Recorded: 2026-09-06 (America/New_York)

## Result

The collector attempted all 42 predeclared experimental units in protocol
order. Every attempt exited incomplete with the same runner error:
`ProviderExecutionError: Codex CLI exited with status 2`.

The first and last bundles each retain stderr stating that
`--ask-for-approval` was an unexpected argument to `codex exec`. Inspection of
the installed CLI help established that the option exists only on the global
`codex` parser and must precede the `exec` subcommand. No attempt emitted a
Codex JSONL event. From that local parser evidence, the implementation infers
that no model request was reached; this is an inference, not provider-side
telemetry.

All 42 raw manifests passed `verify_manifest`. Their manifest-file SHA-256
values are preserved in
[`af-3-v0.1.1-run-manifests.sha256`](af-3-v0.1.1-run-manifests.sha256).
The SHA-256 of that canonical, run-id-sorted index is
`24e86802e6a80953fa2e63907a9104a68db4aec58d3e7a155c3f59a057946560`.

## Disposition

The v0.1.1 bundles remain at the external evidence root. They were not deleted,
rewritten, relabeled as successful, or reused. Their protocol does not permit
post-run exclusion, so any account of v0.1.1 must report 42 incomplete attempts.

The command-order defect was corrected in a later signed commit. A no-network
parser preflight now checks the complete invocation before a live call. Patrick
Roebuck separately authorized successor protocol `baseline-pilot-v0.1.2` for
the corrected 42-run collection.
