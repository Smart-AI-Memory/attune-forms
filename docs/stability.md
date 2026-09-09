# Stability policy

**Status: draft, unratified.** The tier assignments in
`attune_forms.stability` are a proposal until the chair rules on them.

## Why tiers

attune-forms exports 139 public names. They have not aged alike:

| | |
|---|---|
| Names first shipped in v0.1.0 and unchanged since | **24** |
| Names added in the two releases before 0.15.0 | **40** |
| Public surface growth, v0.6.0 → v0.15.0 (22 days) | **39 → 133 (+241%)** |
| Public names ever removed | **0** |
| Deprecation cycles ever run | **0** |
| Releases, 2026-08-12 → 2026-09-07 | **20** (one per ~1.3 days) |

A single "stable" classifier over that surface would promise the
40-name-old host-parity machinery as strongly as the parser that has not
moved in a month. It would be a promise the project cannot keep, and the
first time it needed breaking the cost would fall on consumers who took
the label at face value.

So the promise is per-name, recorded in `attune_forms.stability`, and
enforced by `tests/test_stability.py`. A new export cannot merge without
choosing a tier.

## The three tiers

| Tier | Count | Guarantee | Change process |
|---|---:|---|---|
| **Stable** | 46 | Signature and documented behavior | Deprecation cycle; removal only in a major |
| **Provisional** | 91 | Works, tested, supported | May change or be removed in any minor, with a changelog entry |
| **Deprecated** | 2 | Still works until `not_before` | Removal at or after the declared version |

**Stable** means: the form core (models, bridge, the four renderers,
markdown ingestion, templates, intake, tokens) first shipped on or
before v0.10.0 and unchanged since — 24 of those date to v0.1.0 — plus
the workspace vocabulary, promoted by chair ruling (below).

**Provisional** is not second-class. It is the honest label for surface
that is real and supported but whose shape is still settling — the
interaction profiles, the renderer registry, the host-question line and
its adapter, the canonical fixtures, the workspace vocabulary. New
surface always starts here.

**Deprecated** holds two names. `form_to_askuserquestion` is the
compatibility-only projection superseded by `form_to_host_question`.
`is_trivial_form` is vestigial: 0.15.0 stopped routing on triviality, so
it answers a question nothing asks. Both are scheduled rather than
removed, and both still work.

### Notable assignments

- `select_form_surface`, `needs_widget` — the router changed its default
  in 0.15.0 (admissible forms now go to the host's own control), and
  `handle_render_form` still does not call the new path. A behavior one
  release old, whose replacement is not yet reachable, cannot be
  promised.
- `workspace_to_headless` — v0.14.0. The promotion covered the workspace
  *vocabulary*, not every projection of it.
- `template_example_slots` — v0.13.0, still under soak.

### First promotion, and the exception it required

The workspace vocabulary (17 names) was promoted by chair ruling on
2026-09-08. It met three of the four criteria below outright — 7
releases with no removal, rename or `### Changed` entry since v0.9.1, a
canonical fixture, and an external consumer in attune-ai — and missed
the fourth: 10 days against a drafted 30.

The exception is recorded rather than waived quietly. The 30-day figure
was drafted the same day, ratified by nothing, and was a proxy for
"has it stopped moving" — a question 7 unchanged releases answers
directly. Sixteen of the 17 date to v0.9.x; `workspace_action_contract`
is the youngest at v0.12.0 and was promoted with them so the action
contract is not half-promised.

If the soak figure is wrong for this project's cadence, amend it. What
the policy cannot survive is being quietly ignored.

## Deprecation

A deprecation is a commitment, so it carries one:

```python
Deprecation(
    name="form_to_askuserquestion",
    since="0.16.0",        # the changelog that announced it
    not_before="0.18.0",   # earliest version that may remove it
    replacement="form_to_host_question",
    reason="...",          # why, not just what
)
```

**Windows.** Before 1.0: at least **two minor releases and 30 days**
between `since` and removal. After 1.0: removal only in a major, and
never sooner than **two minors and 90 days**.

**What a deprecation must do**, in the release that declares it:

1. Add the `Deprecation` record to `attune_forms.stability`.
2. Emit `DeprecationWarning` from the deprecated path, naming the
   replacement — with internal callers moved to a private alias first,
   so the warning fires for consumers and not for our own code. A test
   fails the moment the running version reaches `since` with the warning
   unwired, so this cannot be forgotten under release pressure. When the
   deprecated name is a registry target, keep the target pointing at the
   PUBLIC name so `record_digest` and any compatibility contract hold,
   and allowlist the private body.
3. Name the replacement in the warning text and the changelog.
4. Add a `### Deprecated` changelog section. The changelog has never had
   one; the first deprecation creates it.

**What it must not do.** Change behavior at the same time. A deprecated
name keeps working exactly as it did until it is removed.

## Promotion: provisional → stable

Requires all four:

1. **Soak** — no signature or documented-behavior change for **three
   minor releases and 30 days**.
2. **Round-trip evidence** — a canonical fixture exercising it, in the
   registry where one applies.
3. **A consumer** — at least one caller outside this repository has used
   it across a release boundary without a change.
4. **Chair ratification**, recorded in the changelog alongside the new
   `RATIFIED_STABLE_DIGEST`.

Promotion is one-way in practice: demotion is a breaking change.

A criterion may be waived only by a chair ruling recorded in the
changelog, naming which criterion and why. See the first promotion
above.

## Rollout: default-on, with one narrow exception

**attune-forms works by default. That is the design, not an oversight.**

The package has no feature flags. It reads six environment variables —
`ATTUNE_FORMS_KEYBOARD_MODE`, the telemetry opt-outs, and the data-home
resolution — and none of them gates a feature. New behavior is live the
moment the code loads. Installs are unpinned: the shipped `.mcp.json`,
the `codex mcp add` line and the generic-client JSON are all
`uvx --from 'attune-forms[mcp]' attune-forms-mcp`, so hosts take the
newest release on re-resolution.

This is deliberate. The consumer is usually an agent or a host, not a
person reading release notes; a flag most callers never flip is surface
that costs everyone and helps nobody, and it doubles the tested paths
for every behavior it guards. Install-to-working in one step is worth
protecting.

**What this narrows.** Say it plainly rather than let a reader assume
otherwise: *stable* here guarantees the **name, signature and documented
contract** — not that observable behavior never improves. A stable
function may route differently, choose a different surface, or render
different bytes in a new release. Callers who need a frozen behavior pin
a version; that is what pinning is for.

**The one exception — irreversibility.** A behavior change to stable
surface needs an opt-in period only when a consumer cannot recover from
it by their own action:

- it writes or migrates persisted data in a shape older versions cannot
  read;
- it removes an output, field or event a caller could be reading;
- it causes an external effect that cannot be undone by pinning back.

A change that merely produces a *different but equally valid* result —
the 0.15.0 router flip is the worked example — ships on by default with
no flag. Different is not worse, and gating it would have kept the
better host integration away from nearly everyone.

**What every behavior change to stable surface owes instead**, in place
of a flag:

1. A `### Changed` entry naming the *observable* difference, not just the
   internal one, and stating explicitly whether action is required.
2. A pinned-install line in the README for consumers who need to hold a
   version (`attune-forms[mcp]==X.Y.Z`). The plugin default stays
   unpinned; the escape hatch exists for the caller who wants it. This
   landed in the README's "Pinning a version" section, and
   `test_readme_pinned_examples_match_pyproject` keeps the examples on
   the current release — a stale pin teaches a reader to hold the wrong
   version.

**A `<1.0` upper bound is not protection.** Pre-1.0 minors may change
provisional surface and may remove deprecated names, so a constraint like
`attune-forms>=0.15.0,<1.0` resolves a breaking 0.x release exactly as
happily as a safe one — it reads protective and is not. A consumer that
needs protection pins an exact version or a patch range (`~=0.17.0`).
Such a bound also will not resolve 1.0.0 when it arrives, so it has to
change for the 1.0 line regardless. attune-ai carries exactly this shape
today (2026-09-08).

Provisional surface owes only the changelog entry. That is what the tier
buys.

## Not covered by any tier

These may change in any release, including a patch:

- Exact prose of validation problem strings. Consumers needing structure
  use `FormValidationError.field_problems` / `.fields`.
- Rendered HTML and CSS bytes, and the theme size budgets.
- Any digest value (`registry_digest`, `fixture_digest`,
  `implementation_digest`, `stable_surface_digest`). Digests change when
  their content changes — that is their job.
- The telemetry file format and the contents of the data home.
- Any name beginning with `_`, and every module not re-exported from the
  package root.
- The MCP tool result payloads beyond the documented keys.

## Entry criteria for 1.0

Not yet met. In order:

- [ ] Finish AF-2: merge the consuming adapter, wire the MCP tools to the
      route-active `form.host_question` target, retire
      `form_to_askuserquestion`.
- [x] Resolve `escaping_verified` — trialled 2026-09-08 and the claim was
      DELETED, not confirmed: the host escapes nothing, so the profile now
      declares `escaping="none"` (verified as such). Evidence:
      `docs/probes/host-question-escaping-2026-09-08.md`.
- [ ] Run one deprecation end to end. Declared and warning as of
      0.16.0; the cycle is demonstrated only once a removal lands.
- [x] Document a pinned install — README "Pinning a version", gated
      against pyproject (2026-09-08). The observable-difference changelog
      rule for stable surface is adopted in this document; it is a
      practice, proved only by being followed.
- [ ] Soak: three consecutive releases and 30 days with no change to the
      stable surface digest.
- [x] Promote what has earned it — `workspace_*` promoted 2026-09-08.

Only then does `Development Status :: 5 - Production/Stable` describe
something true. Until then Beta is not underselling the library; it is
the accurate label for a surface that grew 241% last month.
