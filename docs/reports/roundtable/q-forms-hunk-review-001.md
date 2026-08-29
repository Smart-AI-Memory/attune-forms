# Round table — a ninth construct? (q-forms-hunk-review-001)

Curated stub — chair-promoted sections only. Full transcript:
`~/.attune/reports/roundtable/q-forms-hunk-review-001.md`
(machine-local, TTL-exempt). Board thread: `q-forms-hunk-review-001`
(2026-08-28, 1 round, 3/3 seats: Claude, Antigravity, Codex).

**Question.** Should attune-forms build a ninth construct
`hunk_review`, or is a per-hunk diff review just `triage` /
`assumption_review` with code-shaped items plus a presentation flag?
Measured cost of a construct: ~19 files, +865 (ranking, PR #24) to
+1219 (assumption_review, PR #25).

## Ruling: build nothing (3/3, board msgs 3/4/5)

No seat argued for building the construct. The candidate fails
admission test #4 (no committed consumer) and no seat could state a
construct-defining validator rule under test #2 that `triage` does not
already cover.

Two corrections the independent round made to the chair's held lean
(msg 2, deliberately not shown to the seats):

1. **The reuse target is `triage`, not `assumption_review`.** All
   three seats rejected `assumption_review` independently. Its
   vocabulary is fixed *because* the vocabulary is the construct
   (D2-a), so `accept` / `edit` / `reject` over hunks is semantically
   wrong even though the answer shape matches. `triage`'s dispositions
   are author-named; that is the correct member.
2. **The interim costs zero files, not three.** A verdict-only hunk
   board is expressible in shipped `triage` slots with no library
   change at all.

## The zero-change encoding (msg 3, chair-promoted)

| hunk review needs | existing `triage` slot |
|---|---|
| stable hunk key | `triage_items[].id` = `path@base_sha:start-end` |
| what changed | `triage_items[].detail` = the unified diff, fenced ` ```diff ` |
| file / severity | `triage_items[].tag` |
| verdict vocabulary | `dispositions` = `["apply","revise","drop"]` (author-named) |
| agent's proposal | `suggested` (already rendered as a proposal) |
| answer | `{hunk id: verdict}` — already the shape |

Validated, on all four surfaces, for the price of a helper function in
the *consumer*. What is lost versus a purpose-built construct is
red/green diff rendering — a rendering gap, and rendering gaps do not
buy `QuestionType` members here (`list_style`, `progress_style` are the
standing precedent).

## Needs, classified (msgs 3/4/5, unanimous)

| Need | Kind | Verdict |
|---|---|---|
| file/line anchors | rendering + key stability | `id` already carries the key |
| `+`/`−` line semantics | rendering | flag |
| syntax highlighting | rendering (evaporates on 3 of 4 surfaces) | flag |
| hunk ordering | presentation; `ranking` is a different speech act | not a need |
| per-hunk replacement **code** | **answer-shape** | one field on `triage`, not a construct |
| partial-hunk / line-subset selection | **answer-shape**, genuinely new | **out of scope** — see below |

**Line-level selection is the boundary.** It turns the answer from
`{key: scalar}` into `{key: subset-of-a-variable-list}`, and there is
no honest `AskUserQuestion` control for "lines 3, 4, 7 of 12" short of
an option-per-line explosion — it fails admission test #3 on the
flattest surface. `git add -p` line staging belongs to a widget-only
staging UI, not to a four-surface grammar.

## Flip conditions (pre-recorded so the gate is a decision, not a drift)

The backlog item stays gated. It flips to **build** only when all three
hold:

1. A committed consumer is **already shipping** the `triage` encoding
   above and can point at a wall.
2. The wall is **answer-shape, not paint**. If the wall is "I need to
   hand back replacement code," the answer is an opt-in
   `edit_dispositions: ["revise"]` on `triage` — lifting the
   `assumption_review` edit lane (`{"edit": text}` + paired
   `"<id>.<item>.text"` + the text-iff-edit fold, all already written
   and paid for). That is one field, **not** a construct.
3. Someone can state, in one sentence, the validator rule that *is*
   `hunk_review`. The table named exactly one candidate — anchor
   integrity — and the chair did **not** promote it; it is recorded in
   the machine-local transcript (msg 3) as the seat's own stated risk
   of waiting, not as project doctrine.

## Open chair fact

All three seats converged on the same follow-up (msgs 6/7/8): does the
prospective consumer need the human to hand back **code**, or only a
**verdict**? Verdict-only is free today; code-back is one field. The
answer decides which of the flip conditions is even reachable.
