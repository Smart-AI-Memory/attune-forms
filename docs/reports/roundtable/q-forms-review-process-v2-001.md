# Round table — library review process v2 (q-forms-review-process-v2-001)

Curated stub — chair-promoted sections only. Full transcript:
`~/.attune/reports/roundtable/q-forms-review-process-v2-001.md`
(machine-local). Board thread: `q-forms-review-process-v2-001`
(2026-08-20, 1 round, 3/3 seats: Claude, Antigravity, Codex).
Supersedes the execution details of the plan in
[q-forms-module-review-plan-001](q-forms-module-review-plan-001.md);
that thread's decision rule (leave-intact-is-success; LOC never
triggers decomposition) remains binding.

## Ratified process (chair ruling, board msg 9)

**Structure.** Single reviewer agent per module on the templated
brief below; the three-seat table convenes at exactly TWO
checkpoints — (1) after discovery-sweep, to ratify the ledger and
final order; (2) end-of-review retro/sign-off. Per-batch sittings
are chair-only rulings on the ledger. Contested seams escalate ad
hoc. Execution runs in batches of 2–3 module reviews per session,
one chair-ruling sitting per batch. Session budget cap $50
(chair, 2026-08-20); per-module token ceiling ~150k with
abort-and-report, never push-through.

**Order.**
1. discovery-sweep across src → triaged act-now ledger
   (checkpoint 1 ratifies it and may rerank what follows).
2. Parallel cheap track, first execution session: plugin-skill
   `verify` pass (doc-vs-code fact-check — not a deep-review slot).
3. Deep reviews: `mcp_server.py` + `markdown_ingestion.py`
   (untrusted-input boundaries) → `models.py` / `form_events.py`
   (shared contracts before render — a contract defect found late
   stales earlier verdicts) → `widget.py`.
4. Support modules (`theme.py`, `template_store.py`,
   `intake_template.py`, `reference_form.py`,
   `elicitation_schema.py`, `markdown_surface.py`, `form_events.py`
   remainder, `__init__.py`): sweep-gated deep review; otherwise
   the skim floor. `bridge.py` is done (PR #37).

**Stop rule (composite, chair-ruled).** The review is DONE when:
- (a) every public entrypoint and untrusted-input boundary has had
  sweep or targeted deep review;
- (b) every module carries a disposition — deep-reviewed /
  sweep-cleared-and-skimmed / accepted-untouched — and every ledger
  flag is fixed, dismissed-with-stated-reason, or chipped (no
  silent drops);
- (c) TWO consecutive batches yield zero confirmed act-now defects
  with an empty ledger (chair adopted the stricter Codex streak);
- (d) the ledger is frozen at each checkpoint — relabeling or
  splitting findings cannot manufacture zero-yield batches.
New evidence reopens the review. Anti-gaming symmetry: the
empirical-repro bar blocks over-reporting; the dismissed-list ×
sweep-ledger cross-check blocks under-reporting.

**Skim floor (chair-ruled).** Sweep-cleared modules that never get
a deep review each receive a lightweight skim with a one-line
disposition before the library counts as covered — "covered" means
every module was looked at by something.

## The reviewer brief template (ratified)

Every per-module review brief carries:
1. **Binding decision rule** — leave-intact-with-named-seams is
   full success; LOC alone never justifies decomposition; only a
   nameable concrete cost or isolatable failure domain does.
2. **Scope** — the module, its immediate callers, its tests.
3. **Defect-class priors** — the running list of confirmed classes
   from prior reviews (currently: unvalidated defaults / injected
   values; silent-drop folds; definable-but-unanswerable
   definitions; silently-ignored unknown keys). Same-class widening
   applies ACROSS modules: check this module for every known class.
4. **Empirical confirmation** — a finding is "confirmed" only via
   executed snippet or failing test; max 2 repro attempts per
   finding. Every act-now fix ships the regression test that would
   have caught it.
5. **Boundary repro template (MANDATED for boundary modules)** —
   malformed-payload/property-style probes the reviewer must run:
   wrong-typed values, out-of-vocabulary members, duplicate/
   colliding keys, empty/None/[]/{} boundary values, non-ASCII and
   non-canonical numerics, oversize payloads, unknown extra keys.
6. **Caller-contract note** — one paragraph on what dependents
   assume of this module, so leave-intact verdicts are grounded.
7. **Mandatory outputs** — fixed ledger schema: baseline test
   result; act-now table (file:line, defect, observable cost,
   repro); needs-a-look list; dismissed-after-inspection list
   ("areas inspected, no issue found" is required content, not
   filler); verdict under the decision rule; test gaps gating any
   change.
8. **Token ceiling** — ~150k; on hitting it, abort and report
   coverage honestly rather than thinning the work.
9. **Scope discipline** — same-defect-class widening lands in the
   diff; anything beyond goes to a chip, never silently dropped.

## Dissent preserved

- Claude seat argued ONE zero-yield batch should end the review
  ("no victory-lap batch") — overruled for Codex's two-batch
  streak; preserved as the fallback if the confirmation batch
  proves pure ceremony in practice.
- Claude seat argued for reviewer discretion (checklist, not
  mandate) on boundary repros — overruled for Antigravity's
  mandated template.
- Codex flagged the standing risk of sweep-first: static discovery
  misses interaction defects; mitigated by (a) in the stop rule
  plus the skim floor, not eliminated.
