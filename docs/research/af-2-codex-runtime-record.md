# AF-2 Codex runtime declaration

Status: machine facts recorded; Checkpoint B.1 chair decision required

Recorded: 2026-09-06 (America/New_York)

## Purpose

This addendum records the provider and sampling information exposed by Patrick
Roebuck's local Codex installation for the proposed 42-run baseline pilot. It
does not authorize collection and contains no provider output.

The original AF-2 evidence record and manifest remain unchanged. The proposed
machine-specific protocol is
[`baseline-pilot-v0.1.1.draft.json`](../../benchmarks/protocols/baseline-pilot-v0.1.1.draft.json).
It retains the fixture, scoring-policy, adapter, repeat, exclusion,
missing-data, falsification, and simulated-action declarations from protocol
version `0.1.0`.

## Observations

The following read-only checks were made on 2026-09-06 before any provider
call:

- `/Users/patrickroebuck/.codex/config.toml` declared model
  `gpt-6-astra`, model reasoning effort `medium`, and service tier `priority`;
- `codex --version` reported `codex-cli 0.144.6`;
- `codex login status` reported `Logged in using ChatGPT`; and
- `codex exec --help` exposed model and general configuration overrides but no
  temperature, top-p, seed, or maximum-output-token option.

No credential or credential value was read or retained.

The official OpenAI model guidance inspected on the same date identifies
`gpt-6-astra` as the request model id, reasoning effort as a supported control,
the Responses API as the tool-calling interface, and `temperature` and `top_p`
as unsupported parameters for GPT-6 Astra.

## Recorded declaration

Protocol version `0.1.1` records:

- provider `openai-chatgpt-via-codex-cli`;
- Codex CLI `0.144.6`, authenticated through ChatGPT;
- model id `gpt-6-astra`;
- medium reasoning effort and priority service tier;
- provider-default sampling; and
- explicit reasons for each unavailable sampling control.

Codex CLI does not expose a dated provider API version or an immutable model
snapshot identifier. The protocol records those facts as
`not-exposed-by-codex-cli-0.144.6` and `not-exposed-by-provider`. These are
availability declarations, not version claims.

## Remaining gate

Automated preflight now reports only four blockers:

1. protocol status is not ratified;
2. Checkpoint B.1 does not authorize collection;
3. Checkpoint B.1 has no authorizing chair; and
4. Checkpoint B.1 has no offset-bearing authorization timestamp.

Before authorization, AF-3 must also define and test the exact `codex exec`
adapter invocation. That adapter must retain enough host metadata to detect a
change in effective instructions or tool access between paired conditions.
The current interactive Codex task is not itself the benchmark provider seam.

No baseline call should occur until the chair has reviewed this declaration,
the invocation contract is executable, and a signed commit records
`COLLECTION_AUTHORIZED` with the chair identity and timestamp.

## Evidentiary limits

The observations establish what the named local commands and configuration
reported on the recorded date. They do not establish the provider's internal
deployment snapshot, backend API revision, or undisclosed host instructions.
Git and SHA-256 can make later repository changes detectable under stated trust
assumptions; they do not supply third-party timestamping, immutable storage, or
a complete legal chain of custody.
