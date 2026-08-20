# Adding a construct: the touchpoint checklist

A new construct type costs roughly 19 files and ~1,000 lines, about
half of it tests. The 2026-08-20 architecture review ruled that cost
the honest price of four surfaces — a construct *means something
different* on each one, so the per-surface branches are four genuine
translations, not duplication a registry could collapse (rejected
alternatives, recorded so they stay rejected: a `Construct` base class
with per-surface render methods; entry-point plugin discovery; codegen
from a spec table). What the review added instead is this explicit
checklist and the drift catchers that turn a forgotten touchpoint into
a red test (`tests/test_grammar_completeness.py`).

Worked examples: `ranking` (PR #24, 20 files, +865) and
`assumption_review` (PR #25, 19 files, +1219).

## The model (1–2)

1. **`models.py` — `QuestionType`**: add the member, with the spec
   prose as its comment block (the enum body is the grammar's
   normative text). If the construct carries new extras, add them as
   fields on the `FormQuestion` dataclass — additive columns, no
   subclassing.
2. **`models.py` — `to_ask_user_format` / `to_ask_user_formats`**: how
   the construct degrades on a plain question tool. An expanding
   construct (one payload per item/slot) raises in the singular method
   and expands in the plural one; iterate rows through
   `expansion_items` / `suggested_pick` / `item_context` so the
   surfaces cannot disagree.

## The parser and validator (3–7)

3. **`bridge.py` — `_parse_<x>_extras`**: a new parser returning
   `(value(s), problems)`, called from `form_from_dict` and guarded
   internally by `qtype is not QuestionType.X`. Reject what the
   construct's rules forbid (e.g. `default` on a ranking, D2).
4. **`bridge.py` — `form_from_dict`**: call the parser, extend
   `problems`, pass the new kwarg to the `FormQuestion(...)`
   construction.
5. **`bridge.py` — the frozensets**: `_OPTIONS_REQUIRED_TYPES`,
   `_WIDGET_ONLY_TYPES`, `_EXPANDING_TYPES`, `_NO_PORTABLE_CONTROL` —
   add the type wherever its behavior matches.
6. **`bridge.py` — `_validate_<x>` + `_ANSWER_VALIDATORS`**: the
   answer-shape validator, registered in the dict. Six constructs
   whose answer is one selected option just register
   `_validate_membership`.
7. **`bridge.py` — `_fold_expanded_answers`**: only if the construct
   expands to dotted keys on flat surfaces — how they fold back.

## The four surfaces (8–14)

8. **`elicitation_schema.py` — `_property_for` /
   `form_to_elicitation_schema`**: the native-elicitation projection
   (flat primitives; expanding constructs become dotted properties).
9. **`widget.py` — `_control_<x>_html` + `_CONTROL_RENDERERS`**: the
   rich HTML control, registered in the dict.
10. **`widget.py` — `_COLLECT_MODES`**: how the submit script reads
    the answer out of the DOM. A construct that answers like an
    existing one reuses its mode and needs NO script edit; a genuinely
    new answer shape needs a new script case AND a new case in the
    gate-parity port (`tests/test_widget_roundtrip.py`).
11. **`widget.py` — `_families_for`** and **`theme.py` — `CSS_<X>` +
    `CSS_FAMILIES`**: the control's CSS family, so forms never ship
    styles they don't use.
12. **`markdown_surface.py` — `_control_lines` + `_skeleton_value`**:
    the portable-markdown rendering and the reply skeleton's
    placeholder shape.
13. **`markdown_ingestion.py`**: how a typed shorthand line for the
    construct parses back (`_known_keys`, `_coerce`,
    `_resolve_line_key`, `markdown_to_answers`).
14. **`mcp_server.py` — `_field_schema`**: the type enum entry, a line
    in the prose description, and any new extra-key property. The
    schema drift test names what you forget.

## The exemplar and exports (15–16)

15. **`reference_form.py`**: one field for the new type in
    `REFERENCE_FORM` plus a valid answer in `EXAMPLE_ANSWERS` — the
    round-trip, CSS, and grammar-completeness suites all span it, and
    `test_reference_form` fails until the field exists.
16. **`__init__.py`**: export any new public helper in `__all__`.

## Tests and docs (17–19)

17. **Tests**: a `tests/test_<x>_construct.py` file (definition rules,
    answer validation, each surface's rendering), plus rows in the
    completeness tables of `tests/test_grammar_completeness.py`
    (collect mode + wrong-shaped answer) and gate-parity fixtures in
    `tests/test_widget_roundtrip.py`.
18. **Docs**: README "The grammar" (bullet AND the spelled-out
    construct count), `plugin/skills/forms/SKILL.md` (a `##` section:
    extra keys, answer shape, flat-surface expansion), CHANGELOG.
    `tests/test_docs_drift.py` enforces the count and the name
    coverage.
19. **Sanity**: `python -m pytest` — the drift catchers
    (`test_grammar_completeness`, `test_widget_roundtrip`,
    `test_widget_css_families`, `test_docs_drift`,
    `test_reference_form`, the `_field_schema` coverage test) are
    designed to fail red on any touchpoint you missed above.
