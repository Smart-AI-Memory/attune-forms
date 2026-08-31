# Changelog

All notable changes to attune-forms are documented here. The format
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.11.1] — 2026-08-31

### Fixed
- Consequential workspace actions now use an inline two-click confirmation
  instead of `window.confirm`, which is unavailable in sandboxed MCP App
  hosts. Choosing another action disarms and restores the pending action.

## [0.11.0] — 2026-08-30

Project path selection becomes a reusable form capability while preserving
manual entry and portable fallbacks.

### Added
- **Path-aware text fields** — `path_kind` selects file, directory, or either,
  while `path_options` carries host-validated project-relative choices.
- **Searchable Browse modal** — widget forms render a polished, accessible path
  picker with Safari/Chrome-compatible overlay behavior, filtering, Escape and
  backdrop closing, focus management, and escaped option labels.
- **Template support** — `FieldSlot.path_kind` lets intake templates request
  the same picker without post-build mutation or form-id drift.

### Changed
- `FORM_THEME_CSS` budget raised 12 KB → 16 KB for the isolated path-picker
  family (chair-ratified 2026-08-30); forms without path fields do not emit it.

## [0.10.0] — 2026-08-30

### Added
- **Portable MCP Apps transport** — capability-aware tool metadata links
  form and workspace renderers to one self-contained `ui://` resource.
  User actions post back through the existing validation tools, and only
  validated results are offered to host model context. Non-supporting and
  partially supporting hosts retain the meaningful structured/text result
  and name the manual fallback visibly.

## [0.9.1] — 2026-08-29

### Added
- **Bound workspace action round trips** — optional workspace id,
  revision, contract hash, and one-render nonce context is preserved by
  widget and Markdown renderers. The strict collector accepts only an
  action defined by the rendered view, requires explicit confirmation
  where declared, and rejects stale or fabricated context without
  authorizing or executing the action.
- **Workspace dictionary and MCP boundaries** —
  `workspace_from_dict` rejects unknown keys throughout the closed view
  grammar. `elicitation_render_workspace` and
  `elicitation_collect_workspace_action` expose the same render/collect
  pattern as forms, with a non-mocked stdio round-trip receipt.

## [0.9.0] — 2026-08-29

### Added
- **Fix-first command workspace grammar** — four portable state views
  (`intake`, `preview`, `execution`, `receipt`) compose the existing
  validated `FormSchema` with a closed display-block vocabulary and stable,
  host-dispatched actions. Widget and Markdown renderers preserve the same
  view/action return contract without accepting executable callbacks or
  arbitrary HTML.
- **Provider-neutral semantic token artifact** — versioned light/dark color
  roles, typography, spacing, radius, motion, and control targets are loaded
  from packaged JSON and exposed as a recursively immutable mapping. Shared
  form CSS and separately-budgeted workspace CSS project from that source.
- **Workspace showcase and hostile-boundary receipts** — all four views,
  every form construct, and every display block are exercised. Tests parse
  emitted action JavaScript with Node, reject script-context action values,
  calculate WCAG AA dark-action contrast, pin explicit confirmation parity,
  and enforce independent form/workspace CSS budgets.

### Changed
- Form widget and portable Markdown renderers accept optional stable action
  and view context, action-specific labels, workspace-owned titles, and
  explicit-action consequences while retaining their existing defaults for
  standalone callers.

### Fixed
- Display-action widgets now emit valid JavaScript, disable actions after
  dispatch, announce success through a live region, and send the same fenced
  sentinel grammar as form-backed views.
- Dark workspace tokens retain host-variable fallbacks, embedded forms inherit
  the workspace profile, and primary-action foregrounds meet WCAG AA.
- Runtime enum guards, Markdown structural escaping, code-language validation,
  evidence-table scopes, stable instance ids, and recursive token freezing
  close the contract and accessibility gaps found by cross-review and the
  three-seat release-readiness roundtable.
- **Multi-line item `detail` kept its shape on both rendering surfaces**
  (round table `q-forms-hunk-review-001`, 2026-08-28). A `detail`
  carrying more than one line — a diff hunk, a log excerpt — was
  corrupted on the way out:
  - **Widget**: it rendered as an inline `<span>` inside a flex row with
    no `white-space` rule, so HTML folded its newlines and leading
    indentation into single spaces and a diff arrived as one run-on
    line. A multi-line detail now renders as an `ae-detail-block` —
    full-width, `white-space:pre-wrap`, monospace. Fixed across
    `triage`, `assumption_review`, `progress` and `confirm` through one
    shared `widget._detail_html` helper and one `CSS_BASE` rule. A
    single-line detail still renders as the same inline span it always
    did (output byte-identical).
  - **Markdown**: it was interpolated into the item's bullet line, so
    every line the detail started with `-` — every removed line of a
    diff — parsed as a NEW bullet, and a `suggested` suffix landed on
    the detail's last line. A multi-line detail now renders as an
    indented code block under the bullet, with the suffix left on the
    bullet. The block is INDENTED rather than fenced because
    `_defuse_fences` breaks every three-backtick run in author text to
    keep the reply skeleton's boundaries; for the same reason an
    author's own ` ```lang ` wrapper is stripped rather than rendered
    as defused noise. Fixed for `triage`, `assumption_review` and
    `confirm` consequences.

### Changed
- `FORM_THEME_CSS` budget raised 10 KB → 12 KB (chair-ruled
  2026-08-28) for the shared `ae-detail-block` rule in `CSS_BASE`; a
  trim to fit under 10 KB was offered and declined. Current size
  10,263 B. The cap remains a design decision, not a ratchet.

## [0.8.0] — 2026-08-24

Per-stage form telemetry: the lifecycle is now measurable end to end
(chair-approved 2026-08-24, route "measure first" — the prior log had
only `form_surface` and a bare `form_submitted`, so per-stage latency
was not computable).

### Added
- **`FormSchema.form_id`** — a telemetry join key on every parsed
  form. An explicit top-level `"form_id"` in the definition wins
  (short `[A-Za-z0-9._-]` token, validated); otherwise
  `form_from_dict` derives a deterministic content hash, so the
  render call and the collect call — which each re-parse the same
  dict — land on the same id without the agent threading anything.
- **Stage events** in `~/.attune/telemetry/form_events.jsonl` (same
  append-only JSONL, consent gates, and 5 MB rotation):
  - `form_build` (`form_id`, `source`: `"dict"` or
    `"template:<name>"` — the V7 template-adoption signal,
    `question_count`) — emitted by `form_from_dict` /
    `form_from_template` on every successful cast.
  - `form_rendered` (`form_id`, `duration_ms`, `html_bytes`) —
    emitted by `form_to_widget_html`.
  - `form_submitted` now carries `form_id` (the MCP collect handler
    passes it; the zero-arg form stays valid for older callers).
  - `form_surface` records also carry `form_id`.
- **`stage_latency()`** — reads the log back as per-stage p50/p95:
  render cost from each `form_rendered`'s own `duration_ms`, and the
  user-facing wait as first `form_rendered` → first `form_submitted`
  per `form_id`; plus build/render/submission counts and the
  cast-source mix.
- `log_form_build` / `log_form_rendered` log helpers (same
  never-raises contract), shared `_append` write path.

### Changed
- `form_from_dict` accepts a keyword-only `source` (default
  `"dict"`); `form_from_template` passes `template:<name>`.

## [0.7.0] — 2026-08-20

The output of a four-stage library review (checkpoint-1 sweep, a
bridge.py pilot, two adversarial confirmation passes) plus a
dynamic-forms architecture review — 23 confirmed correctness fixes,
policy single-sourcing, and drift catchers so the grammar cannot
silently rot again.

### ⚠️ Breaking
- **Stricter input validation now REJECTS input earlier versions
  silently accepted.** Three tightenings can surface as a
  `FormValidationError` where 0.6.0 returned clean:
  - An unknown **definition** key — a typo'd or unrecognized field- or
    top-level key in a form dict (`{"type": "number", "maximun": 10}`)
    — is now a named problem, and the mirrored MCP `inputSchema`
    carries `additionalProperties: false`. Previously the stray key was
    dropped and the field built without the intended constraint.
  - An unknown **answer** key against an optional-with-default field is
    named instead of silently collecting the default.
  - Supplying an expanding question's answer both canonically and as
    dotted keys is a named contradiction instead of the canonical value
    silently winning.
  Migration: remove stray keys from form definitions and answer maps;
  every rejection names the exact offending key. **Downstream mirror:**
  attune-ai hand-maintains its own copy of these MCP tool schemas and
  must re-sync `additionalProperties` (tracked as a fast-follow).

### Added
- Widget gate parity pin (architecture review finding F2, 2026-08-20):
  the submit script's client-side required-field gate (incomplete
  rulings boards, unfilled ranking slots, blank `edit` text, the
  optional partial-ranking block) is now ported rule-for-rule into the
  round-trip simulator and asserted equivalent to the server
  validators — for every construct × fill state, the gate blocks the
  post exactly when `collect_form_response` would reject the payload.
  A structural anchor check also pins the DOM attributes the gate
  queries (`data-required`, `[data-item]`, `data-rank-n`) to what the
  renderer emits. Tests only — no behavior change; the previously
  untested drift class (gate lets an invalid answer post, or blocks a
  valid one, after the widget is dead) now fails red in CI
- Drift guards batch (architecture review findings F1/F6/F9,
  2026-08-20):
  - `tests/test_grammar_completeness.py` — the F1 pin: every
    `QuestionType` member must carry a row in the completeness tables
    (widget collect mode + a wrong-shaped answer), and each of the
    four surfaces must emit construct-specific output for it — a
    construct wired into only three surfaces, or a new type added
    without updating the tables, fails red instead of silently falling
    through a default branch
  - `tests/test_docs_drift.py` — the grammar's hand-maintained docs
    tracked mechanically: README's spelled-out construct count and
    per-construct coverage, SKILL.md's coverage of every question
    type, and every MCP tool / `x_to_y` library function the skill
    names must actually exist (the count had already rotted by hand
    once, commit 543a7a0)
  - `docs/adding-a-construct.md` — the ~19-touchpoint checklist for a
    new construct, with the review's accept-and-pin ruling and the
    rejected registry/base-class alternatives recorded
  - Surface-decision authority stated where it was only implicit
    (F9): `select_form_surface` docstring and README now say the
    router is advisory in the shipped plugin — the agent's MCP tool
    choice is the effective decision and the router runs after the
    fact for telemetry agreement; binding only for library consumers
    routing their own calls

### Changed
- 0.6.x cleanup batch (architecture review findings F4/F5/F7,
  2026-08-20) — single-sourcing and schema hygiene, output
  byte-identical (pinned by the characterization suite):
  - The last policy duplications moved into `models`:
    `BOOLEAN_OPTIONS` (was defined independently in bridge and
    widget), `recommended_first()` (was implemented three times —
    widget, markdown surface, and inline in `to_ask_user_format`),
    `RATIONALE_HEADERS` and `PROGRESS_STATUS_ICONS` (each surface
    carried its own copy with a "matches the widget" comment nothing
    enforced). New `tests/test_single_sourcing.py` pins the
    single-sourcing per surface
  - `bridge._CONFIRM_DEFAULT_OPTIONS` deleted — the bridge now
    consumes `models.CONFIRM_DEFAULT_OPTIONS`, making the 0.5.0
    changelog's single-sourcing claim true
  - The MCP `_field_schema` types its object-array extras
    (`progress_items`, `triage_items`, `consequences`, `assumptions`)
    and gains a drift test: every `QuestionType` value must appear in
    the schema's type enum and every `FormQuestion` field in its
    properties (the prose description stays hand-written on purpose)
  - Stale docstrings corrected: `keyboard_mode_enabled` and the
    package overview now document `ATTUNE_FORMS_KEYBOARD_MODE` as the
    preferred override with `ATTUNE_KEYBOARD_MODE` as the legacy
    fallback, matching what the code reads
- `collect_form_response` rejects unknown top-level answer keys,
  naming them — a typo'd key against an optional-with-default field
  used to silently collect the default. Keys inside an expanding
  question's dotted namespace (`"<id>.<key>"`) remain exempt
- A directly-built CONFIRM (constructed in Python rather than through
  `form_from_dict`) now defaults its options to the two-way gate
  (`Approve` / `Abort`) like every other construction path — before,
  it rendered a gate nothing could approve (0.5.0 review, queued with
  the cleanup batch); `CONFIRM_DEFAULT_OPTIONS` is single-sourced in
  `models`
- A directly-built item-keyed construct carrying the wrong `suggested`
  shape (a list where a mapping belongs) degrades to "no suggestion"
  on every surface instead of crashing the elicitation schema
- Widget submit script reworked from a per-ftype if/else reader into a
  `data-collect` attribute switch (0.5.0 cleanup batch): each rendered
  field now carries `data-collect`
  (`value` / `checked-one` / `checked-many` / `rulings` / `ranked` /
  `rulings-with-text`), emitted at render time from a per-type map, and
  the script switches on that attribute — so a new construct type that
  answers like an existing one registers its mode in `_COLLECT_MODES`
  and needs NO script edit. The round-trip simulator mirrors the same
  switch; the drift catcher now pins the emitted modes against the
  script's cases. Posted payloads are unchanged
- Item-keyed expansion unified (0.5.0 cleanup batch): every surface —
  AskUserQuestion payloads, the elicitation schema, markdown rows and
  skeleton, the widget rows, and the validators — iterates TRIAGE and
  ASSUMPTION_REVIEW rows through one set of shared helpers
  (`expansion_items` / `suggested_pick` / `item_context` in `models`),
  so the item set, its keys, the suggested lookup, and the context
  line can never differ between surfaces. Rendering output is
  byte-identical; presentation stays per-surface

### Fixed
- Unknown DEFINITION keys are now named problems instead of silently
  ignored (confirmation-pass-1 chair ruling, 2026-08-20): a typo'd
  field key (`"maximun": 10`) built a bound-less field that validated
  any answer clean. `form_from_dict` rejects every unrecognized
  top-level and field-level key (`unknown definition key '...'`,
  mirroring #37's answer-side wording; the `label`/`questions` aliases
  stay accepted), and the MCP `inputSchema` declares
  `additionalProperties: false` on both the form and field objects so
  the SDK gate agrees with the parser. The schema is D3-mirrored to
  attune-ai — the mirror must pick up `additionalProperties` at the
  next release-gated re-sync
- Supplying an expanding question's answer both canonically and as
  dotted keys (`{"t": {...}}` plus `"t.i2": "skip"`) is a named
  validation problem instead of the canonical answer silently winning —
  the contradicting dotted value used to vanish, the same silent-drop
  class #39/#40 named for rank slots (chair ruling on
  confirmation-pass-1, 2026-08-20)
- A DELIBERATION whose `endorsements` is the empty mapping `{}` is a
  named definition problem — it satisfied the required check vacuously,
  yielding exactly the "just a decision, no endorsements" the field
  exists to prevent (chair ruling on confirmation-pass-1, 2026-08-20)
- Documented (chair ruling to keep, 2026-08-20): an explicit empty
  answer (`""`, `[]`, `{}`) on a field with a `default` collects the
  default — empty is the accept-the-default gesture, indistinguishable
  from an untouched prefill, so a surface needing a clearable field
  must not prefill it via `default`
- Author-supplied field text can no longer desync the markdown reply
  skeleton (confirmation-pass-2 needs-a-look, 2026-08-20 — the LOUD
  sibling of the pass-2 silent-injection fix). A literal triple-backtick
  fence inside a label, help text, or OPTION used to open a stray code
  fence in the rendered form, so the trailing `answers` skeleton was no
  longer cleanly delimited and paste-back failed loudly ("fenced code
  block is not valid JSON"). Every author/host line rendered by
  `form_to_markdown` and the `problems_to_markdown` re-ask is now defused
  — runs of three+ backticks get a woven zero-width break so no ```
  substring survives, while inline `` `code` `` (runs under three)
  renders untouched. A fence-bearing value that reaches the JSON skeleton
  itself (a default/recommended/suggested option carrying a fence) has
  each backtick emitted as the JSON unicode escape `\u0060`, which
  `json.loads` restores on ingestion, so the skeleton's own fence stays
  intact and exact option matching is unchanged. The widget surface
  HTML-escapes and was already immune
- **Directly-built D2 gate with a `default` can no longer pass
  unanswered** (checkpoint-2 promoted item, 2026-08-20 — empirically
  confirmed). The no-`default` rule for the two-way constructs (confirm,
  ranking, assumption_review) was enforced ONLY definition-side in
  `form_from_dict`. A `FormQuestion` built directly (dataclass
  constructor, bypassing `form_from_dict`) with `default="Approve"`
  slipped past it, and then `collect_form_response({})` auto-injected
  the default — so an UNANSWERED confirm gate collected as *approved*
  with no user act, defeating the gate CONFIRM exists to enforce. The
  prohibition now also lives on the collect/inject path
  (`collect_form_response`), where it can't be bypassed: a directly-built
  confirm / ranking / assumption_review carrying a `default` is rejected
  (`FormValidationError`, wording consistent with the definition-time
  message) instead of injected. Defense in depth: the elicitation schema
  no longer emits a `default` for those construct types either, so a
  bypassing question can't pre-select approval in the client dialog
  (this also stops a stray `default` from clobbering a ranking's
  legitimate `suggested`-derived schema default).
- Confirmation-pass-1 needs-a-look items (library review, 2026-08-20):
  - `submission_count()` and `inference_rate()` accept the same
    optional `home` argument as sibling `surface_mix()` — a
    configured-home reader (the ops dashboard) now reads the store it
    displays instead of the process-env one
  - `inference_rate()` skips a line with a FRACTIONAL count
    (`question_count: 2.7`) as malformed instead of silently
    truncating it — the same skip-whole-line class as negative and
    non-numeric counts; an integral float (`5.0`) still counts
  - MCP `handle_collect_response` called as an import (the attune-ai
    mirror path, which the SDK's stdio jsonschema gate does not cover)
    names a non-dict `answers` argument through the module's own
    `{success: false, problems: [...]}` contract instead of raising a
    raw `AttributeError`/`TypeError`
- A declared slot name outside the placeholder grammar (e.g. `Who`,
  `café`) is named as the real problem — "not a valid placeholder name
  (lowercase [a-z][a-z0-9_]*)" — instead of the factually-false
  "declares unused slot" it produced even when the literal `{Who}` text
  was present in a field (confirmation-pass-1 needs-a-look, 2026-08-20)
- Confirmation-pass-2 batch (library review, 2026-08-20 — all five
  findings empirically confirmed before fixing):
  - **Silent answer injection closed**: the markdown re-ask
    (`problems_to_markdown`) now ends in a trailing `answers` skeleton
    for the re-asked fields, restoring the last-block-wins invariant
    `form_to_markdown` relies on. A fenced `answers` block quoted
    inside an offending field's author-supplied text was the only JSON
    candidate, so a user quoting the re-ask back ingested answers they
    never typed with no problem named
  - A BOOLEAN field's elicitation schema is a `["Yes", "No"]` string
    enum, not `{"type": "boolean"}` — the validator accepts only
    Yes/No, so the boolean projection was unanswerable in both
    directions (a conformant client's `true`/`false` bounced at
    collect; the only collectable answers violated the schema)
  - Intake prefill: the "was the prefill applied?" check is by
    identity, not equality — a self-unequal prior answer (`nan != nan`)
    slipped past the `!=` guard and reopened the whole-build crash the
    prefill fold otherwise closes
  - `inference_rate` skips a record with more inferred fields than
    total fields, the same malformed-record class as negative counts —
    one such line had pushed `inferred_share` to 10.4
  - The markdown assumption merge applies the collect fold's
    `set(current) == {"edit"}` guard: a quoted non-edit dict ruling
    (`{"keep": true}`) beside a typed text lane is no longer silently
    laundered into a valid `{"edit": …}` that this surface alone
    accepted while the collect path names it
  - A display-only PROGRESS field (no blocked options) no longer
    projects to `{"type": "string", "enum": []}` in the elicitation
    schema — an empty enum is a property no value can satisfy (an
    unanswerable field, or a whole-schema rejection on a strict
    client). Such a report is narrated, not answered, so it is now
    skipped from `properties`/`required` entirely; a PROGRESS that
    carries blocked options is a real single-pick and still projects
- `form_from_template` now validates the `slots` argument type *before*
  the `values = slots or {}` coalesce (confirmation-pass-2 needs-a-look,
  2026-08-20). The pass-1 `isinstance(values, dict)` guard ran after the
  coalesce, so a falsy non-mapping (`[]`, `MappingProxyType({})`) folded
  to `{}` and slipped past the named `slot values must be a mapping`
  message — harmless today (it still failed via missing-slot problems)
  but a silent accept on a future zero-slot template. A non-`None`,
  non-`dict` `slots` is now named directly; `None` still coalesces to
  an empty mapping. `dict` stays strict so the "mapping" wording matches
  what is accepted — a `Mapping` that is not a `dict` is rejected too
- The widget's `::` radio-group namespace is now collision-guarded at
  definition time, symmetric with the existing dotted-key guard
  (confirmation-pass-2 needs-a-look, 2026-08-20). A TRIAGE or
  ASSUMPTION_REVIEW board with id `a` renders one radio group per item
  named `a::<idx>`; a sibling field whose id was literally `a::1` emitted
  a group sharing that `name`, so the browser fused the two into one
  mutually-exclusive group and one field became unanswerable in the
  widget. A field id colliding with a board's `a::<idx>` namespace is now
  rejected at `form_from_dict` time, so the colliding HTML is never
  rendered. Low realism (no author writes `::N` ids) but a genuine
  unguarded namespace analogous to the guarded dotted one
- Confirmation-pass-1 batch (library review, 2026-08-20 — all eight
  findings empirically confirmed before fixing):
  - An assumption-review text lane whose item has NO ruling (a
    nonexistent item, or a real one the answer never ruled) is a named
    problem from the collect-time fold and the markdown merge — typed
    replacement text no longer vanishes from a response that validates
    clean (text beside a non-edit ruling stays a documented drop)
  - `form_from_template` names a non-mapping `slots` argument through
    its normal problems seam instead of crashing with `AttributeError`
  - Telemetry: reserved record keys (`v`/`ts`/`event`/`surface`) can no
    longer be clobbered by caller kwargs (a forged `form_submitted`
    advanced the keyboard-hint counter); the "never raises" contract
    now covers more than `OSError` (a circular context raised
    `ValueError` through live surface routing); `inference_rate` skips
    NEGATIVE counts like any other malformed record instead of letting
    one corrupt line push `inferred_share` outside 0–1
  - Intake prefill fold: a prior answer is kept iff it validates for
    the built field — an invalid string (e.g. the `other` free-text
    lane's prior answer) no longer crashes the whole intake build, and
    faithful list/number prefills on multi-select/number slots are no
    longer blanket-dropped
  - MCP `inputSchema` types `default` to include `"object"` — a legal
    triage default (`{item id: disposition}`) no longer rejected by
    the SDK's schema gate before the tool's problems contract can run
- `inference_rate()` skips a telemetry line with non-numeric counts
  instead of raising `ValueError` — matching the skip-don't-raise
  contract of its sibling readers (discovery-sweep, 2026-08-20)
- An intake-template prefill that isn't a string (e.g. a prior
  multi-select answer) is no longer repr-coerced into the slot's
  default (`"['src/', 'tests/']"` presented as a settled value); the
  slot's own default survives instead
- `FormResponse.response_id` carries a uuid suffix — two responses in
  the same second no longer collide
- The MCP `inputSchema` types `default` as answer-shaped
  (string/number/boolean/array) instead of string-only, and declares
  `inferred_from` — the advertised schema no longer steers an agent
  into a definition-time validation failure on list/numeric defaults
- `plugin.json` description names all nine constructs shipped in 0.6.0
- A field `default` is now validated like the answer it pre-supplies
  (pilot review of bridge.py, 2026-08-19): `form_from_dict` rejects an
  out-of-vocabulary or wrongly-typed default at definition time, and
  `collect_form_response` refuses to inject one from a directly-built
  form — before, `default: "zzz"` on a select collected an
  out-of-option answer into a "validated" `FormResponse`. A
  MULTI_SELECT default is now a LIST (the answer's shape); the widget
  pre-checks by membership, so several boxes can be pre-checked — the
  old scalar form, which could only ever pre-check one and collected a
  non-list, is a definition problem
- A ranking answer supplying the same rank slot twice via dotted keys
  (`"r.01"` and `"r.1"` both fold to slot 1) is a named validation
  problem instead of an arbitrary winner validating clean
- The markdown surface's ranking fold applies the same rule: two typed
  shorthand lines claiming one rank slot (`prio.01:` and `prio.1:`)
  are a named problem from `markdown_to_answers` instead of a silent
  overwrite — the quoted (JSON-block) lane was already collision-proof,
  admitting only canonical slot keys
- A template slot declared in `"slots"` but used by no `{placeholder}`
  is a named definition problem from `form_from_template`
  (checkpoint-1 finding, 2026-08-20) — before, the loader demanded a
  caller value for it and then silently discarded it. Declaration and
  use now must match in both directions, mirroring the existing
  undeclared-placeholder check
- A PROGRESS with no options (display-only) auto-defaults to
  `required=False` when `required` is omitted, and an explicit
  `required: true` is a definition problem — before, the definition
  passed and collect failed both ways (no answer → required; any
  answer → not in options)

## [0.6.0] — 2026-08-16

The backlog-constructs release: the communication grammar grows from
six constructs to eight — `ranking` and `assumption_review`, the two
backlog candidates the chair ruled into this cut — each spec-driven
(D1 intake → D2 ratified forks → D3 execution → D4 live AC-4 receipt),
shipped on all four surfaces with validated round-trips, and hardened
by a five-lens adversarial review per construct BEFORE the cut, every
finding fixed with a pinned regression. 611 tests.

### Added
- `ranking` construct (spec `ranking-construct`, communication-grammar
  member #7 — roundtable `q-forms-grammar-expansion-001` backlog
  candidate, chair-ruled into 0.6.0 on 2026-08-15): the user orders the
  options, all of them or only the top `top_n`; the answer is the
  ordered list (distinct, exactly `top_n`/all long, every entry an
  option); a `suggested` order renders visibly as a proposal and is
  never the answer, and `default` is rejected (D2-c). Widget: a ranked
  list + unranked pool moved by buttons (no drag dependency); with no
  `suggested` order an untouched form posts nothing, and with one the
  proposal renders pre-ranked under the visible badge, so submitting
  untouched posts it — the submit IS the confirmation. Flat surfaces
  expand to one single-select per rank slot (`"<id>.<k>"`, D2-b) and
  fold back in `collect_form_response`; elicitation schema is a bounded
  unique array; markdown renders the rule + skeleton and ingests a
  comma list in order (a leading ordinal stripped only when the strip
  lands on an option) or one slot per line, typed slots overriding a
  pasted skeleton. `ranking_slot_count` exported — the one sizing rule
  every surface shares
- `assumption_review` construct (spec `assumption-review-construct`,
  communication-grammar member #8 — roundtable
  `q-forms-grammar-expansion-001` backlog candidate, "the
  inference-first discipline made a construct", chair-ruled into 0.6.0
  on 2026-08-15): the agent lists the assumptions it inferred
  (`assumptions`: `{label, id?, detail?, source?}`) and the user rules
  each from the FIXED vocabulary accept / edit / reject, an edit
  carrying replacement text; answer =
  `{item key: "accept" | "reject" | {"edit": text}}` (D2-c); `suggested`
  may pre-mark accept only (D2-b); `default` and `dispositions` are
  rejected (D2-a). Widget: triage-style rows with the source shown, an
  inline replacement-text box (pre-filled with the label) revealed only
  while edit is picked. Flat surfaces expand to one single-select per
  assumption PAIRED with an optional `"<id>.<key>.text"` question; the
  fold keeps the text only on edit and the validator requires it then;
  elicitation schema flattens the same way; markdown renders the rule +
  rows + skeleton and ingests `field.item: edit: <text>` (a bare `edit`
  shapes to `{"edit": ""}` and is named, never guessed into an accept),
  typed rows overriding a pasted skeleton. `ASSUMPTION_RULINGS` exported.
  The skill draws the boundary with "Infer first": settled dimensions
  are never reviewed; inferred ones about to be acted on are
- Reference form + example answers cover `ranking` and
  `assumption_review` (one edit ruling exercises the text lane); widget
  round-trip, CSS-family, needs-widget, markdown-conformance and
  ingestion guards extended

### Changed
- Form theme budget raised 8 KB → 10 KB (10,064 B measured with the
  RANK and ASSUME families; ratified 2026-08-15, ranking-construct
  D2-a — a CSS consolidation pass was offered and not chosen, so the
  cap is not a ratchet: the next raise needs its own ruling)
- The dotted answer namespace guard now covers every expanding type
  (triage items, ranking slots, assumption rows + text lanes); the
  markdown parser names a dotted key on a non-expanding field as such
- `form_response_summary` renders an assumption edit as
  `key: edit → <text>` rather than a raw dict
- `problems_to_markdown` attributes a problem to the FIRST quoted field
  id only (every collect-time problem opens with it) — a later quoted
  value or vocabulary word can no longer re-ask a sibling field that
  happens to share its name (five-lens review of the assumption-review
  construct, 2026-08-15; five findings pinned in
  `tests/test_assumption_review_construct.py::TestReviewFindings`:
  unquoted vocabulary hint, blank-edit widget gate, duplicate-label
  rejection, `edit: <text>` accepted on the JSON reply path, inline
  edit text beating the text lane on both paths)

### Fixed
- Docs state the construct count as six (decision, pushback, progress,
  deliberation, triage, confirm) — the plain batched form is the
  substrate the constructs sit on, not a construct; the "member #N"
  numbering in code comments follows the same count
- Seven ranking-ingestion findings from the five-lens review of the
  construct's diff (2026-08-16; four confirmed by two skeptics each,
  three reproduced from the unverified pool), every one pinned in
  `tests/test_ranking_construct.py::TestReviewFindings` and
  `tests/test_widget_roundtrip.py::TestReviewFindings`:
  - Ordinal stripping is now option-aware on both markdown paths: an
    option label that legitimately starts `<digits>.`/`<digits>)`
    ("3.12", "2) legacy") ingests exactly instead of being mangled into
    a membership failure no retry could fix; plain shaping noise
    ("1. billing") still strips
  - `decimal_key_number` (new, single-sourced, ASCII-only) parses every
    numeric answer key: a Unicode-digit slot suffix (`prio.²`) can no
    longer raise a raw `ValueError` out of `collect_form_response` and
    the MCP collect tool (`str.isdigit()` accepts 95 BMP characters
    `int()` rejects)
  - The bridge fold keeps EVERY decimal rank slot — zero and
    out-of-range included — so an over-long dotted ranking is named by
    the validator's length check instead of ranks being silently
    dropped
  - A pasted JSON block's dotted rank slots no longer override a TYPED
    list line (the typed-beats-quoted contract held everywhere else);
    quoted slots overlay only a quoted base
  - The widget submit gate blocks a partial OPTIONAL ranking
    (0 < ranked < slots) with "Rank every slot or none: …" — the
    validator is all-or-nothing whatever `required` says, so posting a
    partial list after the widget disabled itself dead-ended the form
  - The round-trip simulator reads rows pre-populated in the ranked
    list and respects the slot cap, modelling the real submit script
    instead of a fill no user could perform
  - Docstrings corrected to match behavior: the elicitation schema
    carries a ranking as ONE bounded array (only AskUserQuestion and
    markdown expand to dotted slots), and an untouched ranking with a
    `suggested` order posts the proposal — visibly badged — rather
    than "nothing"

## [0.5.0] — 2026-08-14

The grammar-expansion release: the communication grammar grows from
three constructs on three surfaces to six constructs on four — every
one with a validated round-trip — deliberated by the multi-LLM round
table (thread `q-forms-grammar-expansion-001`: 3/3 on the markdown
surface and triage, id-keying and strict-degradation amendments
applied as ruled), and hardened by a post-merge 8-angle review plus a
cloud ultrareview before this cut.

### Added
- Tolerant markdown ingestion (spec `markdown-ingestion`, the S4
  surface's return path — roundtable-ruled "spec next"):
  `markdown_to_answers` deterministically parses a typed reply (pasted
  JSON skeleton or line shorthand — `field_id: value`, `N: value`,
  dotted triage rows) with every unparseable line and unknown id a
  named problem, never a guess; `problems_to_markdown` renders
  validation failures as a markdown re-ask of only the offending
  fields. Validation truth stays `collect_form_response`; free-text
  replies remain the host agent's skill-taught lane
- `confirm` construct (spec `confirm-construct`, roundtable-ruled
  "spec next"): action preview with a structured `consequences` list
  (`{label, severity?, detail?}`) and a two-way approve/abort gate —
  exactly two options, and `default`/`recommended` are rejected by
  the validator (a pre-selected approval defeats the gate, D2). Flat
  surfaces render a two-option single-select with a compact "Will: …"
  receipt; the markdown skeleton never prefills the answer
- `deliberation` construct: multi-voice endorsements per option
  (`{option: [voice, ...]}`) rendered as chips, synthesis pick badged,
  chair picks one; flat fallback folds endorsements into a compact
  summary; answer validates as a single-select
- `triage` construct: per-item rulings over a reviewed list
  (`triage_items` + `dispositions` + optional `suggested`); answer is
  `{item id: disposition}` keyed on stable per-item ids (label
  fallback); expands to one single-select per item on flat surfaces
  via dotted ids that fold back in `collect_form_response`
- Portable markdown surface (`form_to_markdown`, S4): renders any form
  for text-only hosts (Codex CLI, Antigravity) and emits the widget's
  sentinel-marked JSON answer skeleton as the return path — one
  postback grammar across all four surfaces
- `triage_item_key` exported: the one keying rule every surface shares
- Reference form + example answers now cover the two new constructs;
  widget round-trip, CSS-family, and markdown conformance guards
  extended to them

### Fixed
- Twelve post-merge review findings, each with a pinned regression
  (#18, #19): typed shorthand now overrides a pasted JSON skeleton
  (including dotted triage rows merging into a quoted mapping, typed
  wins); the dotted triage namespace is guarded at definition time;
  code fences with any language tag are excluded from shorthand
  parsing; unknown JSON answer keys are named problems; non-finite
  numbers are rejected by the validator on every surface;
  label-keyed triage shorthand parses; triage answers render per-item
  in summaries; `to_ask_user_format` raises loudly for triage; falsy
  defaults survive into the reply skeleton
- CSS class-uniqueness guard: no class may be styled by two family
  blocks — the collision mode the coverage guard cannot see (#17)

### Changed
- Form theme budget raised 6 KB → 8 KB (8,158 B measured with the
  TRIAGE + CONFIRM families and deliberation seat chips; ratified
  with the #14 merge)
- MCP field schema documents the new types and extras (tool names and
  result shapes unchanged)

## [0.4.0] — 2026-08-14

The plugin release: attune-forms becomes installable as a Claude Code
plugin, and the communication-grammar article ships in-repo as its
verified master.

### Added
- Claude Code plugin wrapper: generic forms skill + marketplace scaffold, installable via `claude plugin marketplace add Smart-AI-Memory/attune-forms` (#4)
- "A Communication Grammar for AI Agents" — the article introducing the grammar, kept in `docs/` as its verified master (#6, #7, #8)
- Widget-preview dev lane: `.claude/launch.json` renders the reference form through the real widget pipeline (#9)
- Version-sync drift guard test: README install snippets can't silently diverge from `pyproject.toml` (#5)

### Fixed
- Test suite pins imports to the checkout's own `src/`, so a stale editable install can no longer swap in another worktree's code

## [0.3.0] — 2026-08-12

### Added
- Standalone MCP server (`attune-forms-mcp`): the four elicitation tools — ask, render form, render widget, collect response — mirrored from attune-ai, stdio transport, `[mcp]` extra (#3)

## [0.2.0] — 2026-08-12

### Added
- Collision-proof public names with legacy attune-ai names honored as shims (P1) (#2)
- Lint gate in CI: pre-commit (black/ruff, pinned to attune-ai's versions) on every push/PR (#1)

## [0.1.0] — 2026-08-12

### Added
- Initial extraction of the attune-ai elicitation subsystem: declarative `FormSchema`, build/collect validation, multi-surface renderers (widget HTML, AskUserQuestion batching, MCP elicitation), surface router, template layer with ask-time intake generation
- Trusted-publishing release workflow (tag-triggered, PyPI environment)

[Unreleased]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Smart-AI-Memory/attune-forms/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Smart-AI-Memory/attune-forms/releases/tag/v0.1.0
