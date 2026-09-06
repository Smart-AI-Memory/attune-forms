# Typed-condition implementation and conformance

`benchmarks.typed_forms.TypedFormActor` uses the existing TextProvider seam.
It receives ActorScenario only; evaluator-only seeded risks and requirements
are not passed to the provider. It adds an explicit JSON form-output contract.

`AttuneFormsAdapter` validates the generated form with `form_from_dict`, invokes
an explicitly supplied response host, and validates accepted answers with
`collect_form_response`. The host receives an immutable FormRequest (unique
request id plus JSON form snapshot) and returns FormSubmission with the same id.
A stale response, invalid answer, unknown key, actor-supplied answer envelope,
model default/inferred answer, malformed form, or host exception yields retained
incomplete evidence. Cancel/decline yields a cancellation event without answers.
No retry or provider follow-up is implicit. Provider text and telemetry survive
validation failures. Adapter identity is fixed.

Only adapter/host-observed requests and validated responses receive runner
provenance. Actor attempts to inject trusted provenance are rejected, even on
incomplete outputs. No authorization or execution event is manufactured.
The request event explicitly marks display_verified=false: this is a headless
contract test, not a native rendering receipt. The response source names the
host or simulator; this does not authenticate a human identity.

The canonical package form and answer set completed a real parser/validator
round trip before the conformance tests were written. Twenty-two tests cover
success, cancellation, invalid data, stale/replayed responses, callback errors,
incomplete provider output and forged provenance. Each of the seven frozen
actor scenarios runs through the adapter with a named canonical-fixture
simulator; every resulting task_success remains null. These tests establish
contract behavior, not scenario completion or human outcomes. No live typed
model calls were collected.

Provider elapsed_ms retains its existing meaning. The adapter records separate
typed_response_elapsed_ms for accepted response handling; these are not a
human task-time comparison. A comparative protocol must define shared timing,
response opportunities, trusted instrumentation and conditions before use.
The baseline collector and its two-condition schema remain unchanged; this
implementation cannot silently add typed runs to the approved 42-unit cohort.
