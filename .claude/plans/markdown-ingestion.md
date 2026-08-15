# Tolerant Markdown Ingestion — execution plan

**Created:** 2026-08-14
**Source:** /spec (attune-ai:spec)
**Status:** pending
**Spec:** ~/attune-ai/docs/specs/markdown-ingestion/
**Repo:** attune-forms
**Provenance:** roundtable q-forms-grammar-expansion-001 "spec next"
(resp-20260814-211025) → intake ruled (resp-20260814-213951).

## Outcome

The S4 markdown surface becomes a full round-trip: typed replies
(shorthand or filled JSON block) parse deterministically into raw
answers, validate through collect_form_response, and failures echo
back as markdown re-asks of only the offending fields.

<task id="T1" name="Parser core: markdown_to_answers">
  <objective>New module src/attune_forms/markdown_ingestion.py: markdown_to_answers(form, reply) -> (answers, problems). Precedence: last fenced JSON block (sentinel payload or bare answers object) wins; else shorthand lines — 'field_id: value', 'N: value' (1-based), 'field_id.item_key: disposition' (triage, folds via the existing collect pre-pass). Type-aware values: exact option membership left to the validator, Yes/No boolean passthrough, numeric parse for NUMBER, comma-separated values -> list for MULTI_SELECT. Unknown ids and unparseable non-empty lines become named problems; nothing silently guessed or dropped. Export in __init__.</objective>
  <files-to-create>
    <file path="src/attune_forms/markdown_ingestion.py"></file>
    <file path="tests/test_markdown_ingestion.py"></file>
  </files-to-create>
  <files-to-modify>
    <file path="src/attune_forms/__init__.py"></file>
  </files-to-modify>
  <validation>
    <check>AC-1 shorthand reply (id lines + N line + dotted triage + comma multi-select) parses for the reference form and validates</check>
    <check>AC-2 filled JSON skeleton (payload and bare forms) parses identically</check>
    <check>unknown id and junk line each yield a named problem, never a guess</check>
  </validation>
  <dependencies></dependencies>
</task>

<task id="T2" name="Error echo loop: problems_to_markdown">
  <objective>problems_to_markdown(form, problems) renders ONLY the offending fields as markdown (reusing the S4 field renderer), headed by the named problems — the re-ask a text-only host relays verbatim. Problem-to-field attribution by quoted field id; problems that name no field render in the header. Fields that validated are never re-rendered.</objective>
  <files-to-modify>
    <file path="src/attune_forms/markdown_ingestion.py"></file>
    <file path="src/attune_forms/__init__.py"></file>
    <file path="tests/test_markdown_ingestion.py"></file>
  </files-to-modify>
  <validation>
    <check>AC-3: one bad option + one unknown id -> both named, exactly the offending field(s) re-rendered</check>
  </validation>
  <dependencies><dep>T1</dep></dependencies>
</task>

<task id="T3" name="Skill free-text lane + reply footer + conformance guard">
  <objective>form_to_markdown's reply footer documents the shorthand (so users discover it in-band); the forms skill gains the ingestion discipline: try markdown_to_answers first, propose a mapping for free text, validate everything through elicitation_collect_response, re-ask uncertain fields rather than guess. Reference-form conformance test: a typed shorthand reply covering every QuestionType round-trips to a validated FormResponse. CHANGELOG entry.</objective>
  <files-to-modify>
    <file path="src/attune_forms/markdown_surface.py"></file>
    <file path="plugin/skills/forms/SKILL.md"></file>
    <file path="tests/test_markdown_ingestion.py"></file>
    <file path="tests/test_markdown_surface.py"></file>
    <file path="CHANGELOG.md"></file>
  </files-to-modify>
  <validation>
    <check>R5 conformance test green over the full reference form</check>
    <check>footer documents both reply modes without bloating the render</check>
  </validation>
  <dependencies><dep>T1</dep></dependencies>
</task>

<task id="T4" name="Live receipt + PR">
  <objective>Record AC-4: one real typed shorthand reply from the chair parsed and validated end-to-end (receipt in the spec's decisions.md). Full suite + lint green; PR opened linking the spec; CI 7/7.</objective>
  <files-to-modify>
    <file path="CHANGELOG.md"></file>
  </files-to-modify>
  <validation>
    <check>AC-4 receipt recorded in decisions.md</check>
    <check>AC-5 full suite + lint green; PR opened</check>
  </validation>
  <dependencies><dep>T2</dep><dep>T3</dep></dependencies>
</task>
