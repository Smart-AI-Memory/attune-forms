# Confirm Construct — execution plan

**Created:** 2026-08-14
**Source:** /spec (attune-ai:spec)
**Status:** pending
**Spec:** ~/attune-ai/docs/specs/confirm-construct/ (requirements + decisions)
**Repo:** attune-forms
**Provenance:** roundtable q-forms-grammar-expansion-001 → chair "spec
next" (resp-20260814-211025) → intake accepted (resp-20260814-212130).
**Open ruling:** decisions.md D2 (no-default/no-recommended rule,
lead-proposed) — must be ruled before T1 executes, since T1 implements it.

## Outcome

attune-forms gains the `confirm` construct (grammar member #7): action
preview + structured consequences list + explicit two-way approve/abort
gate, across all four surfaces.

## Done when (intake, verbatim)

confirm construct merged to attune-forms main with CI green: definition
validation, all four surfaces (widget / AskUserQuestion / elicitation
schema / markdown), answer validation through collect_form_response,
reference-form + round-trip drift guards extended, and one live
human-validated receipt recorded.

<task id="T1" name="Model + definition/answer validation">
  <objective>Add QuestionType.CONFIRM with `consequences` (required non-empty list of {label, severity?, detail?}, validated like triage_items without ids) and exactly two options (default ["Approve", "Abort"] when omitted; any other count is a definition error). Enforce the D2 rule (pending chair ratification): `default` and `recommended` are rejected on a confirm. Answer validates by membership via the existing _validate_membership; CONFIRM joins _WIDGET_ONLY_TYPES and _OPTIONS_REQUIRED_TYPES is untouched (options are defaulted, not required from the author).</objective>
  <files-to-modify>
    <file path="src/attune_forms/models.py"></file>
    <file path="src/attune_forms/bridge.py"></file>
    <file path="tests/test_needs_widget.py"></file>
    <file path="tests/test_batch1_characterization.py"></file>
  </files-to-modify>
  <files-to-create>
    <file path="tests/test_confirm_construct.py"></file>
  </files-to-create>
  <validation>
    <check>missing/empty consequences, option count != 2, or default/recommended on a confirm each raise FormValidationError naming the field (AC-1)</check>
    <check>membership answer round-trips; out-of-option rejected</check>
    <check>needs_widget partition test updated and green</check>
  </validation>
  <dependencies></dependencies>
</task>

<task id="T2" name="Widget surface: renderer + CSS + submit script">
  <objective>Render the confirm: question text as action headline, consequences as rows with severity tags visibly badged (reuse/extend the triage row+tag styling family where possible), the two options as unchecked radios (never pre-selected). Add the ftype branch to the submit script and the round-trip DOM simulator; extend the CSS-family exhaustive test. Stay under the 8,192-byte theme budget or surface the overage as a ruling, never silently.</objective>
  <files-to-modify>
    <file path="src/attune_forms/widget.py"></file>
    <file path="src/attune_forms/theme.py"></file>
    <file path="tests/test_widget_css_families.py"></file>
    <file path="tests/test_widget_roundtrip.py"></file>
    <file path="tests/test_form_theme.py"></file>
  </files-to-modify>
  <validation>
    <check>every emitted class is styled (css-families guard)</check>
    <check>no radio renders checked; hostile labels escape inert</check>
    <check>theme budget test green at its current cap</check>
  </validation>
  <dependencies><dep>T1</dep></dependencies>
</task>

<task id="T3" name="Flat surfaces: ask fold, elicitation enum, markdown">
  <objective>to_ask_user_format: single-select of the two labels with consequences folded compactly into help_text ("Will: X (irreversible); Y — detail"). Elicitation schema: string enum of the two labels (never JSON boolean). Markdown surface: consequences as bullets with severity tags, skeleton value null (no prefill — D2 projected to S4).</objective>
  <files-to-modify>
    <file path="src/attune_forms/models.py"></file>
    <file path="src/attune_forms/elicitation_schema.py"></file>
    <file path="src/attune_forms/markdown_surface.py"></file>
    <file path="tests/test_confirm_construct.py"></file>
    <file path="tests/test_markdown_surface.py"></file>
  </files-to-modify>
  <validation>
    <check>ask payload is a 2-option single_select with consequences in help_text</check>
    <check>elicitation property is a 2-value string enum, no default</check>
    <check>markdown skeleton value is null; filled skeleton validates (AC-2)</check>
  </validation>
  <dependencies><dep>T1</dep></dependencies>
</task>

<task id="T4" name="Drift guards, skill reconciliation, docs, live receipt">
  <objective>Extend REFERENCE_FORM + EXAMPLE_ANSWERS with a confirm field; extend the MCP field schema (type enum + consequences property; tool names/shapes unchanged). SKILL.md gains the confirm section INCLUDING the R5a boundary sentence reconciling "a bare confirmation is never a form" with the construct (bare re-confirmations stay conversational; the construct is reserved for consequence-bearing actions). CHANGELOG entry under Unreleased. Record one live human-validated receipt (AC-3), open the PR, CI green (AC-4).</objective>
  <files-to-modify>
    <file path="src/attune_forms/reference_form.py"></file>
    <file path="src/attune_forms/mcp_server.py"></file>
    <file path="plugin/skills/forms/SKILL.md"></file>
    <file path="CHANGELOG.md"></file>
    <file path="tests/test_reference_form.py"></file>
  </files-to-modify>
  <validation>
    <check>reference-form completeness guard green (one field per QuestionType)</check>
    <check>widget round-trip + markdown conformance green over the new field</check>
    <check>live receipt recorded (rendered, human-answered, collect-validated)</check>
    <check>full suite + lint green; PR opened with the D2 ruling linked</check>
  </validation>
  <dependencies><dep>T2</dep><dep>T3</dep></dependencies>
</task>
