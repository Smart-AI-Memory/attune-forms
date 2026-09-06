# AF-3 — exact Codex CLI provider and authorized baseline pilot

Status: provider implementation complete; collection authorized and pending

Outcome: Implement a pinned, evidence-retaining Codex CLI `TextProvider`, then
collect exactly 42 raw runs under ratified protocol `baseline-pilot-v0.1.1`.

Done when:

- the provider command, prompt compilation, runtime checks, telemetry parsing,
  and failure retention are executable and tested;
- every run is made from the signed, clean collector commit in protocol order;
- each success or failure is immediately sealed in its append-only raw bundle;
- all 42 run manifests verify and a repository record identifies their digests;
- no evaluation, aggregation, comparative claim, or typed adapter is introduced;
- `codex/af-3-codex-pilot` is pushed and represented by a draft pull request.

<tasks>
  <task id="AF3-1" title="Implement exact provider" status="done">
    <objective>Compile role-separated messages and invoke the pinned Codex CLI runtime.</objective>
    <acceptance>The full credential-free command and effective prompt are retained for every invocation.</acceptance>
  </task>
  <task id="AF3-2" title="Retain provider evidence" status="done">
    <objective>Seal JSONL events, stderr, exit status, elapsed time, and usage without credentials.</objective>
    <acceptance>Successes and failures remain JSON-serializable and append-only.</acceptance>
  </task>
  <task id="AF3-3" title="Verify collector" status="done">
    <objective>Prove protocol matching, exact order, clean-runner enforcement, and resumable verification.</objective>
    <acceptance>The focused tests and complete repository suite pass before collection.</acceptance>
  </task>
  <task id="AF3-4" title="Collect authorized pilot" status="pending">
    <objective>Execute and seal seven scenarios by two conditions by three repeats.</objective>
    <acceptance>Forty-two immutable raw-run manifests verify, including retained incomplete runs.</acceptance>
  </task>
  <task id="AF3-5" title="Preserve remotely" status="pending">
    <objective>Push the signed branch and open a draft pull request.</objective>
    <acceptance>The remote record contains the implementation and a digest index for the external raw evidence.</acceptance>
  </task>
</tasks>
