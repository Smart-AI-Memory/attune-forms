# Authority Envelope: research model

Status: concept proposal, not a runtime API

## Problem

Agent systems increasingly separate reasoning from tool execution, but the human authorization boundary is still commonly represented by free-form conversation.

That creates an authority gap: a phrase such as "looks good" may be understandable conversationally while remaining underspecified as permission to execute a consequential action.

attune-forms already separates presentation, validated response, and host-side authorization. This proposal asks whether that separation should be made explicit as a portable authority artifact.

## Principle

**A user response is evidence of a decision. It is not automatically authority to execute arbitrary work.**

A host or policy layer decides whether a validated decision grants authority. When it does, that authority should be narrow, inspectable, state-bound, and consumable.

## Conceptual envelope

An authority envelope describes:

- **principal** — who exercised authority;
- **action** — the exact operation or operation class being authorized;
- **context** — the state against which the decision was made;
- **evidence** — consequences, recommendation, alternatives, and other material information presented before the decision;
- **decision** — the validated human ruling;
- **scope** — resources, limits, and permissions covered by the ruling;
- **validity** — revision, expiry, nonce, or other conditions under which the ruling remains usable;
- **provenance** — the interaction contract and response that produced the decision.

Illustrative shape only:

```json
{
  "principal": {"type": "human", "id": "host-defined"},
  "action": {"id": "delete-preview", "kind": "destructive"},
  "context": {"revision": "r17", "digest": "..."},
  "decision": "approve",
  "scope": {"resources": ["preview/123"], "max_items": 1},
  "validity": {"expires_at": null, "nonce": "..."},
  "provenance": {"interaction_id": "...", "contract_digest": "..."}
}
```

This document deliberately does not define identity, authentication, cryptographic signatures, or policy evaluation. Those belong to the host / authorization system unless future evidence demonstrates a provider-neutral seam worth standardizing.

## Invariants worth testing

1. **No scope expansion** — execution cannot exceed the authorized resource/action scope.
2. **State binding** — material state changes can invalidate prior authority.
3. **No presentation authority** — rendering a control grants nothing.
4. **No recommendation authority** — an agent recommendation grants nothing.
5. **Explicit consequential approval** — high-consequence actions cannot infer approval from unrelated conversation.
6. **Inspectable provenance** — a host can explain what the user saw and ruled on.
7. **Single-use where appropriate** — nonce-bound authority can be consumed rather than replayed.
8. **Surface equivalence** — widget, native, Markdown, and headless projections preserve the same authority semantics even when presentation differs.

## Relationship to existing attune-forms constructs

The existing constructs remain interaction grammar, not permission objects.

- Decision records a choice.
- Pushback records a ruling after structured disagreement.
- Deliberation exposes competing positions before a ruling.
- Triage records dispositions over a stable item set.
- Confirm is the strongest candidate for producing authorization evidence because it explicitly represents consequential approval.
- Assumption review records acceptance, correction, or rejection of inferred context.
- Workspace action contracts already provide useful state and contract-binding primitives.

The envelope is therefore above individual widgets and below host execution policy.

## Why not implement this immediately?

Because premature standardization would turn an architectural observation into permanent API surface.

Before adding runtime objects, the Interaction Benchmark should answer:

- Which failures actually occur in realistic agent workflows?
- Which fields are necessary to prevent them?
- Which fields belong in attune-forms versus an authorization framework?
- Does state-bound explicit authority reduce errors enough to justify its interaction cost?
- Can the same semantics survive multiple agent hosts?

## Candidate research scenarios

### Stale approval

User approves deletion of three generated files. The agent's working set changes to four files before execution. Expected: old authority does not silently authorize the fourth file.

### Scope confusion

User approves publishing a draft to staging. Agent attempts production publication. Expected: authority does not transfer across environment scope.

### Conversational ambiguity

User says "looks good" after reviewing a plan. Agent has a pending destructive action. Expected: conversational assent is not treated as destructive-action authorization.

### Replay

User authorizes a one-time external submission. The same response is replayed. Expected: a single-use authorization can be rejected after consumption.

### Cross-surface parity

The same contract is presented in widget and Markdown form. Expected: both yield equivalent validated authority evidence.

## Product positioning hypothesis

If the benchmark supports the model, attune-forms can be described more precisely as a **typed human-authority protocol for AI agents** rather than merely a forms library.

That positioning should not be adopted as a factual safety claim until behavioral evidence exists.
