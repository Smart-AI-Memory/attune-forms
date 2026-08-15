# attune-forms content plan — August 2026

*Publication review + plan for two articles and two posts (plus one optional post) about attune-forms and the communication grammar. Written 2026-08-15 against attune-forms 0.5.0 (on PyPI 2026-08-15, tag v0.5.0).*

Master/projection rule (ratified 2026-08-13): every article's verified master lives in `docs/` in this repo; LinkedIn/blog copies are projections. Divergences are fixed here first, then re-projected.

Count convention (ratified 2026-08-15): the grammar has **six constructs** — decision, pushback, progress, deliberation, triage, confirm — on top of the plain batched form (seven plain field types: text_input, single_select, multi_select, boolean, number, date, textarea). The plain form is the substrate, not a construct. (README §The grammar and CHANGELOG 0.5.0 still say "seven constructs"; that fix is tracked separately, not in this plan.)

**What 0.5.0 added — "the new dynamic-forms enhancements"** (per README §The grammar / §One schema, every surface, and CHANGELOG 0.5.0; ratified 2026-08-15 as the tutorial's "new elements"):

| Enhancement | Public API / where | README says |
|---|---|---|
| `deliberation` construct | `type: "deliberation"`, `endorsements` | multi-voice endorsements as chips; synthesis pick is a badge, user chairs |
| `triage` construct | `type: "triage"`, `triage_items`, `dispositions`, `suggested`; `triage_item_key` exported | a ruling per item; answer is the full `{item: disposition}` mapping; stable ids |
| `confirm` construct | `type: "confirm"`, `consequences` | approval gate, exactly two options, nothing pre-selected — validator forbids it |
| Portable markdown surface (S4) | `form_to_markdown` | any form on text-only hosts, ends with the JSON answer skeleton |
| Typed-reply ingestion + re-ask | `markdown_to_answers`, `problems_to_markdown` | deterministic parse (never guesses); re-asks exactly the failing fields |
| Reference form + example answers | `REFERENCE_FORM`, `EXAMPLE_ANSWERS` | now cover all six constructs — the runnable example set |

---

## Part 1 — Publication review

### Inventory

| # | Artifact | Where | Status | Covers | Stale vs 0.5.0? |
|---|----------|-------|--------|--------|-----------------|
| 1 | **"A Communication Grammar for AI Agents"** (article) | Master: `docs/communication-grammar-article.md`. Projection: LinkedIn, published 2026-08-13 — https://www.linkedin.com/pulse/communication-grammar-ai-agents-patrick-roebuck-sutse | Published; thread closed | The idea: a question as a typed, validated artifact; three constructs (decision, pushback, progress); "three surfaces"; the *when-not-to* discipline; a day-in-the-life dogfood story; "380+ tests"; install paths | **Yes, by design (it's a snapshot).** Missing: deliberation, triage, confirm; the fourth (markdown) surface + typed-reply ingestion; test count now 514 collected. Do **not** retro-edit the projection — Article B carries the delta. |
| 2 | **README.md** | repo root; rendered on GitHub + PyPI | Current (0.5.0 rewrite, #11 + 0.5.0 bump) | Install (plugin + pip), the grammar (six constructs listed), quick start, four surfaces, ingestion, validation, intake templates, telemetry, host seams, provenance | Only the "seven constructs" word (tracked separately). |
| 3 | **`plugin/skills/forms/SKILL.md`** (the Claude Code skill) | `plugin/skills/forms/` | Current | The batching rule, infer-first, all six constructs with their extra keys, the four-step surface choice incl. markdown + ingestion order (parse → your lane → validate), keyboard mode | Not stale. This is the most complete *procedural* text and the tutorial's spine. |
| 4 | **CHANGELOG.md 0.5.0 entry** | repo root | Current | What landed and why (roundtable thread `q-forms-grammar-expansion-001`, 3/3 rulings), the twelve post-merge review fixes | Says "five → seven constructs on four surfaces" — same count issue. |
| 5 | **Reference form + example answers** | `src/attune_forms/reference_form.py` (`REFERENCE_FORM`, `EXAMPLE_ANSWERS`, exported) | Current, CI-guarded (one field per `QuestionType`) | The seven plain field types **and** all six constructs in one coherent "new feature intake" scenario, with valid answers | Not stale. The runnable example set for the 0.5.0 enhancements (see the table above) — Article A lifts its construct snippets from here. |
| 6 | **Dynamic Forms demo script** (video) | attune-ai: `docs/process/DEMO_DYNAMIC_FORMS_script.md` (+ `_transcript.md`) | Draft, dated 2026-07-23/25; version-gated on attune-ai 10.6.0; not published as far as the repo records show | "3 turns → 1 turn" arc, pushback specimen, dogfood close, 60s social cut | Predates the library extraction entirely (attune-ai `/elicit` framing, three constructs). Reusable *specimens* (the security-audit scoping form, the "Scope of the fix" pushback), not reusable framing. |
| 7 | **attune-ai docs** — `docs/features/elicitation-forms.md`, `docs(elicitation): name attune-forms as the substrate's home` (#2062) | attune-ai | Current | Points attune-ai readers at attune-forms as the substrate | Not a publication; a link-back target. |
| 8 | Branch `claude/attune-forms-post-144e19` | this repo | Empty (no commits beyond main, clean tree) | — | No post draft exists in-repo. Post drafts live off-repo per the LinkedIn workflow (`~/.attune/scratch/` drafts file with POSTED/UNPOSTED markers). |

### What's already said well (don't repeat)
- The framing "guess or interrogate → forms" and "forms are punctuation, not replacement" (article §1, §"What I'm not claiming"; README intro).
- Decision / pushback / progress explained in prose (article) and as key reference (SKILL.md).
- The dogfood story of the extraction day (article §"A day in the life").

### Uncovered ground (what the new pieces should own)
1. **The three new constructs as *ideas*, not just as keys** — deliberation (multi-voice, minority visible, synthesis ≠ answer), triage (a ruling per item, stable ids), confirm (a gate that *refuses* pre-selection). Nothing published explains why these are speech acts and not widgets.
2. **The return path.** The article ends at "render". Nothing published covers `form_to_markdown` → `markdown_to_answers` → `problems_to_markdown`: text-only hosts, deterministic parsing, "never guesses — every stray line is a named problem", re-ask only the failing fields.
3. **A hands-on build.** No published piece walks a reader from an empty dict to a validated round trip. The README quick start is two fields.
4. **The four-surface claim shown, not asserted** — the same form rendered as widget HTML, batched payloads, MCP elicitation schema, markdown; one validator behind all four.
5. **The grammar deciding its own grammar** — the roundtable ruled the expansion 3/3 through a deliberation-shaped process; the article told a similar story for pushback. A fresh, smaller instance for a post.

### Facts verified for the new pieces (2026-08-15, this checkout)
- 0.5.0 is the latest on PyPI (releases 0.1.0–0.5.0). `v0.5.0` GitHub release 2026-08-15.
- `pytest --collect-only`: **514 tests collected** (README says "510+", article said "380+" — both true when written).
- Public API (from `attune_forms.__all__`): `form_from_dict`, `collect_form_response`, `FormValidationError`, `form_to_widget_html`, `form_to_askuserquestion`, `form_to_elicitation_schema`, `form_to_markdown`, `markdown_to_answers`, `problems_to_markdown`, `select_form_surface`, `REFERENCE_FORM`, `EXAMPLE_ANSWERS`, `triage_item_key`, `WIDGET_RESPONSE_MARKER`, intake-template names.
- Round trip executed: `form_from_dict(REFERENCE_FORM)` → 13 questions (7 plain + 6 constructs) → `collect_form_response(form, EXAMPLE_ANSWERS)` returns `FormResponse` with `responses["priority"] == "high"` and `responses["finding_rulings"] == {"retry-loop": "fix now", "stale-doc": "ticket"}`; `select_form_surface` → `"widget"`; widget HTML ≈ 22 KB; `form_to_askuserquestion` → 4 batched payloads; `form_to_markdown` → ~98 lines ending in the JSON skeleton; `markdown_to_answers` on a pasted skeleton returns the exact answers with zero problems; an out-of-options answer raises `FormValidationError` with `problems == ["'priority' value 'urgent' not in options"]` and `problems_to_markdown` re-renders **only** that field.
- **Tutorial gotchas** (write around them, don't hand-wave): the schema object exposes `.questions` (not `.fields`) and each question's `.type` is a `QuestionType` enum; the *library* validator **raises** `FormValidationError(problems)` on bad answers, while the *MCP tool* `elicitation_collect_response` returns `{"success": false, "problems": [...]}` — the tutorial should show the library form and mention the tool shape once.

---

## Part 2 — Content plan

Publish order and dependencies are at the end. Voice for all four: first person singular, measured claims with provenance, one question CTA per post, no flattery, plugin install path first then pip.

### Article A — tutorial

**Working title:** *Six constructs, then the 0.5.0 layer: building a dynamic form that survives any host*
**Alt:** *Adding deliberation, triage, confirm — and a return path — to the forms grammar, one snippet at a time*

**Audience:** developers building agents or Claude Code plugins who have read (or skimmed) the concept article and want to *type something in*. Python-literate; no attune context assumed.

**Thesis (one sentence):** Take the six constructs the README already documents, add what 0.5.0 layered on — the three newest constructs as working examples, a fourth surface for text-only hosts, and a typed-reply return path that never guesses — and the same dict renders everywhere and validates through one validator.

**Master:** `docs/tutorial-dynamic-forms.md` (new). **Projection:** LinkedIn article (+ optionally GitHub Discussions / dev.to). Target **1,800–2,200 words** + code; every snippet must run against 0.5.0 (`pip install attune-forms==0.5.0`), copied from — not paraphrased from — `reference_form.py`, README, SKILL.md.

**Outline:**
1. *What you'll build* — the reference scenario ("new feature intake" — `REFERENCE_FORM`), the end state (a validated round trip on four surfaces, including a text-only host). Install: plugin path, then `pip install attune-forms`.
2. *The base form in one breath* — a two-field `form_from_dict` (README quick start) plus the batching rule from SKILL.md in two sentences; show build-time refusal of a malformed definition. Keep it short — this is the substrate, not the subject.
3. *The six constructs as they stand* — the grammar the README documents, each with its extra keys, one snippet lifted from `REFERENCE_FORM`, and the one-line conversational move. Mark the last three as **new in 0.5.0** — these are the "new examples" the tutorial exists to demonstrate:
   - `decision` (`recommended`, `rationale`, `option_notes`) — recommend
   - `pushback` (`user_position` + decision keys) — dissent
   - `progress` (`progress_items`, blocked → `options`) — report + unblock
   - **0.5.0** `deliberation` (`endorsements`, synthesis pick badged, user chairs) — chair a split
   - **0.5.0** `triage` (`triage_items`, `dispositions`, `suggested`; stable ids via `triage_item_key`; dotted expansion on flat surfaces) — rule per item
   - **0.5.0** `confirm` (`consequences`; exactly two options; `default`/`recommended` **rejected**) — consent gate. Show the validator refusing a pre-selected approval; that's the article's best single moment.
4. *Adding the 0.5.0 surface: one dict, four hosts* — `select_form_surface`; `form_to_widget_html` (screenshot), `form_to_askuserquestion` (the 4 batched payloads; a triage board arrives pre-expanded), `form_to_elicitation_schema`, and **new** `form_to_markdown` (show the tail: the JSON answer skeleton and the line-shorthand rules).
5. *Adding the 0.5.0 return path* — **new** `markdown_to_answers` on a pasted skeleton and on shorthand (`priority: high`, `finding_rulings.retry-loop: fix now`); a stray line becomes a named problem, never a guess; `collect_form_response` as the only truth; `FormValidationError.problems`; **new** `problems_to_markdown` re-asks only the failing field. Wire the loop: render → reply → parse → validate → re-ask.
6. *When not to build any of this* — the batching rule and the "never form a confirm" boundary vs. the confirm card (SKILL.md's paragraph, condensed).
7. *Where it runs today* — the Claude Code plugin's four MCP tools (widget / batched / native elicitation), and text-only hosts (Codex CLI, Antigravity) via the markdown surface. Close with the repo/PyPI links and one question CTA (which host readers would want it on next).

**Draws on:** `src/attune_forms/reference_form.py`, README §Quick start / §One schema, SKILL.md, CHANGELOG 0.5.0, the verified round trip above. **Assets to produce:** one widget screenshot (via the widget-preview launcher, #9), one markdown-surface text block.

**Verification gate before projecting:** run every snippet in a fresh venv against PyPI 0.5.0; `attune-ai:verify` pass on the master.

### Article B — concept piece

**Working title:** *Six speech acts: what a communication grammar adds to agent chat*
**Alt:** *Recommend, dissent, report, deliberate, adjudicate, consent — a grammar for the half of the conversation chat can't carry*

**Audience:** the readers of the first article — people thinking about AI↔human interaction design, agent builders, engineering leads. Less code than A; one snippet at most.

**Thesis:** Chat carries ambiguity well and decisions badly; a communication grammar names the six *moves* an agent makes when it needs something settled — and makes each a typed, validated artifact — so the exchange becomes auditable in both directions and disagreement, minority opinion, and consent stop being buried in prose.

**Master:** `docs/six-speech-acts-article.md` (new). **Projection:** LinkedIn article. Target **1,300–1,600 words.** Explicitly builds on the first article — one paragraph of recap with the canonical link, then only what's new.

**Outline:**
1. *Recap in five lines* — the first article's claim (question = data structure; forms are punctuation) and its three constructs. Link.
2. *What changed since* — three constructs, a fourth surface, and a return path landed in 0.5.0; and the change was itself ruled through a multi-voice deliberation (thread `q-forms-grammar-expansion-001`, 3/3). State this as fact with provenance, not as a flourish.
3. *The grammar as speech acts* — the six moves, each in a paragraph: what the human gets that prose can't guarantee.
   - Recommend (decision) — the recommendation is *positioned*, not just stated.
   - Dissent (pushback) — overruling is a first-class outcome.
   - Report (progress) — a status that can't go stale as prose because the blockers are answerable.
   - Deliberate (deliberation) — a 2-1 split stays visible; the synthesis pick is a badge, never the answer; the human chairs. Why "never dress one opinion as many" is a *validator-shaped* rule.
   - Adjudicate (triage) — one ruling per item over a reviewed list; stable ids so rulings survive re-renders; the answer is the whole mapping.
   - Consent (confirm) — consequences enumerated with severity; two options; a pre-checked approval is *rejected by the library*, because a gate that can be pre-passed isn't a gate.
4. *Both directions, not symmetric* — the agent asks with a form; the human closes with a word. New since the article: the confirm card's boundary with "never form a confirm" — consequences that deserve enumeration vs. a bare re-confirmation.
5. *The return path is half the grammar* — a form that renders on a text-only host and whose typed reply is parsed *deterministically*: no guessing; every unparseable line is a named problem; free text stays the agent's lane but as a proposal the validator must accept. Why this matters for trust more than the rendering does.
6. *What I'm still not claiming* — one production consumer; constructs that don't earn their place should die (the article's promise, kept: name one thing that was cut or amended in review, e.g. the id-keying / strict-degradation amendments from the roundtable).
7. *Try it* — plugin path first, pip second; question CTA: which speech act is missing.

**Draws on:** `docs/communication-grammar-article.md`, README §The grammar, SKILL.md construct sections, CHANGELOG 0.5.0 (roundtable provenance), `src/attune_forms/models.py` validator rules for confirm/deliberation.

**Verification gate:** every construct rule stated must map to a validator or renderer behaviour in `src/` (cite the test that pins it — `tests/test_deliberation_construct.py`, `tests/test_triage_construct.py`, confirm tests, `tests/test_markdown_surface.py`).

### Post 1 — the gate that refuses to be pre-checked

**Idea carried:** confirm construct. **Hook:** "I shipped an approval form that *rejects* a default answer. On purpose." Two sentences on why (a pre-selected approve is not consent), the two-option rule, one line that this is the validator's rule not the UI's, and the SKILL.md boundary in one line: bare "go" stays a word; consequences that deserve a list get a card. Link → Article B (or the repo until B is up). ≤ 1,100 characters. Question CTA: what's the last approval you clicked without reading the consequences?

### Post 2 — the 2-1 split you're supposed to see

**Idea carried:** deliberation construct + dogfood. **Hook:** three models ruled 3/3 on expanding a grammar — and the tool that shows a 2-1 split with the minority visible was one of the things they ruled on. Explain endorsements-as-chips and "synthesis pick is a badge, never the answer; you chair." Provenance line: thread id and date. Link → Article B. ≤ 1,100 characters. Question CTA: where do you currently lose the minority opinion — review, planning, models?

### Post 3 (optional, tutorial teaser)

**Idea carried:** one dict, four surfaces, one validator. Show the 13-line skeleton the markdown surface emits and say the same form is a widget in Claude Code and a batched question set in a terminal. Link → Article A. ≤ 900 characters. Question CTA: which host would you want it rendered on next?

### Publish order & dependencies

| Step | Item | Depends on | Notes |
|------|------|-----------|-------|
| 1 | Article B master → `docs/` PR | none | Concept first: it carries the "what's new" delta and gives Posts 1–2 a link target. |
| 2 | Article B → LinkedIn projection | step 1 merged | Capture canonical URL in memory + README link. |
| 3 | Post 1 (confirm) | step 2 | 1–2 days after B. |
| 4 | Article A master → `docs/` PR | verify pass against PyPI 0.5.0 | Independent of B; can be drafted in parallel. |
| 5 | Article A → LinkedIn projection | step 4 merged | |
| 6 | Post 2 (deliberation) | step 2 | Can slot between 3 and 5. |
| 7 | Post 3 (optional) | step 5 | |

Off-repo state (which posts are POSTED/UNPOSTED, canonical URLs) goes in the drafts file per the existing LinkedIn workflow, and canonical article URLs get a `reference_*` memory + README link like the first article.

### Open items / could not verify
- Whether the attune-ai dynamic-forms **video** was ever published — the repo records only "draft, version-gated". Treat as unpublished; nothing here depends on it.
- No LinkedIn *post* (as opposed to the article) about attune-forms is recorded in-repo or in memory; if one exists off-repo, add it to the inventory before Post 1 to avoid recycled phrasing.
- README/CHANGELOG "seven constructs" wording — being fixed separately; Articles A/B use six.
