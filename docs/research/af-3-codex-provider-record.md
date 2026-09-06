# AF-3 Codex CLI provider implementation record

Status: pre-collection record corrected after retained v0.1.1 parser failure

Recorded: 2026-09-06 (America/New_York)

## Purpose

This record documents the implementation and pre-collection verification of
the Codex CLI `TextProvider` used by protocol `baseline-pilot-v0.1.1`. It does
not report provider output, evaluated outcomes, or a comparison between the two
conditions.

Patrick Roebuck authorized Checkpoint B.1 collection under
`baseline-pilot-v0.1.1` using the recorded Codex runtime. The signed protocol
commit `8e0194c12f83ca57208328a0d46862106825be09` records the chair identity,
offset-bearing authorization timestamp, and `COLLECTION_AUTHORIZED` ruling.

## Invocation contract

For every logical completion, `CodexCliProvider` invokes this credential-free
argument sequence, with the executable and neutral workspace recorded as
absolute paths:

```text
codex
  --ask-for-approval never
  exec --json
  --ephemeral
  --ignore-user-config
  --ignore-rules
  --strict-config
  --skip-git-repo-check
  --sandbox read-only
  --model gpt-6-astra
  -c model_reasoning_effort="medium"
  -c service_tier="priority"
  -c project_doc_max_bytes=0
  -C <empty-neutral-workspace>
  -
```

Before each invocation, the provider requires the executable to be a regular
file, the neutral workspace to exist and be empty, and `codex --version` to
report `codex-cli 0.144.6`. It also substitutes `--help` for the standard-input
prompt and requires the installed CLI to parse the otherwise exact command.
The CLI receives the live prompt on standard input. No
credential or credential value is placed in the command, prompt, environment
record, or provider record by this implementation.

The command uses ephemeral non-interactive JSONL execution. It ignores user
configuration and execution-policy rules, sets the project-document byte limit
to zero, and runs in a read-only sandbox with approval disabled. The host
capability record nevertheless reports `tools: true`, because the CLI exposes a
read-only tool surface. A command, file-change, MCP, web-search, or other
non-text item makes the run incomplete; it is not represented as a successful
text completion.

OpenAI's official non-interactive-mode documentation describes `codex exec`,
JSONL output, ephemeral sessions, configuration and rule suppression, sandbox
selection, and completed-turn usage. Its AGENTS.md documentation describes the
ordinary global and project instruction chain and the project-document byte
limit. Those pages were inspected on 2026-09-06:

- https://learn.chatgpt.com/docs/non-interactive-mode
- https://learn.chatgpt.com/docs/agent-configuration/agents-md

## Prompt and response record

The benchmark's role-separated system and user messages are normalized into a
compact JSON array in their original order. A fixed transport instruction tells
Codex to treat that array as the complete conversation and return only the next
assistant message. The exact compiled prompt and its SHA-256 are retained in
`provider.json`; `prompts.json` retains both the logical messages and transport
prompt.

On a completed call, the adapter retains the parsed JSONL event stream, stderr,
exit status, elapsed milliseconds, input tokens, and output tokens. Missing
agent text, missing completed-turn usage, malformed JSONL, a nonzero exit, a
timeout, or a disallowed item becomes a runner-observed incomplete artifact.
Partial stdout and stderr are retained. Timeout byte streams are decoded with
replacement rather than becoming unserializable.

The evidence writer rejects provider metadata containing credential-shaped
keys before creating an immutable bundle. Raw evidence format `0.2.0` adds the
separately hashed `provider.json` file. Existing sealed evidence is not changed.

## Collection controls

The collector independently checks the ratified provider, model, CLI version,
reasoning effort, and service tier. It computes the plan from the retained
fixture and protocol and refuses any plan other than 42 unique runs in
scenario-condition-repeat order. Collection requires:

- a clean Git worktree;
- raw evidence and provider workspace paths outside the repository;
- an empty provider workspace;
- immediate append-only sealing after every attempted run; and
- byte-identical protocol snapshots when resuming an already-sealed run.

No probe call is permitted before collection. The first live provider call will
therefore be the first retained experimental unit. An interrupted collection
may resume only by verifying existing manifests and the embedded protocol; run
paths are never overwritten.

## Pre-collection verification

The focused provider, collector, evidence, runner, and protocol suites reported
`45 passed`. The complete repository suite reported `1130 passed`. Ruff,
Black, and `git diff --check` passed before signed commit `c9bae60`.

## Correction after v0.1.1 collection

Commit `c9bae60` placed the global `--ask-for-approval never` option after the
`exec` subcommand. Codex CLI 0.144.6 rejected that position with exit status 2
before emitting a JSONL event. The collector retained all 42 attempts as
incomplete bundles under `baseline-pilot-v0.1.1`; it did not overwrite or omit
them. The uniform retained error was `ProviderExecutionError: Codex CLI exited
with status 2`, and each retained stderr records the unexpected argument.

The correction moves that option before `exec` and adds the no-network parser
preflight described above. The installed CLI accepted the corrected parser
preflight. Patrick Roebuck then authorized proceeding, and successor protocol
`baseline-pilot-v0.1.2` records that authorization. The fixture, conditions,
provider/model declaration, sampling declaration, repeats, order, exclusions,
missing-data handling, and falsification rules are unchanged.

## Evidentiary limits

The adapter records observable local command inputs and CLI outputs. It does not
expose or establish an immutable provider model snapshot, backend API revision,
undisclosed service-side instructions, or independent custody of provider
systems. ChatGPT authentication occurs through the existing Codex installation;
this implementation neither reads nor records its credential value.

The 42-run pilot is one completion per experimental unit. The sequential
condition adds the predeclared constraint to ask about at most one unresolved
decision in a clarification request; it does not synthesize user replies or
create an unratified multi-turn procedure.

Raw collection alone authorizes no scoring change, aggregation rule,
comparative claim, or typed attune-forms adapter as an experimental condition.
This is a protocol boundary, not a claim that forms are technically unavailable
or nonfunctional in Codex. Adding that condition remains subject to the renewed
Checkpoint B review required by falsification rule F6.
