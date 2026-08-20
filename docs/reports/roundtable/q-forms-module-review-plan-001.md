# Round table — repo review/cleanup plan (q-forms-module-review-plan-001)

Curated stub — chair-promoted sections only. Full transcript:
`~/.attune/reports/roundtable/q-forms-module-review-plan-001.md`
(machine-local, TTL-exempt). Board thread: `q-forms-module-review-plan-001`
(2026-08-19, 1 round, 3/3 seats: Claude, Antigravity, Codex).

## Ratified plan (chair ruling, board msg 9)

Reuse existing workflows as a funnel; no new repo-wide cleanup
orchestrator. Order:

1. **clean-run baseline** — prove v0.6.0 green (preflight + unit
   suite) before anything else; reliability failures outrank cleanup.
2. **verify pass on plugin/ skill surfaces** — skill markdown rots by
   contract drift (claims about tools/schemas/defaults vs. src), the
   one gap existing code audits don't cover. Run `attune-ai:verify`
   with a target list; minting a named "surface-contract audit"
   workflow is **evidence-gated** — only if this pass proves clumsy.
3. **discovery-sweep** across src — one triaged ledger
   (act-now / needs-a-look / dismissed). Downstream work draws only
   from the act-now bucket; no manufactured findings.
4. **Pilot: bridge.py** (chair-ruled, 2–1 table majority) — worked
   example run as code-quality → refactor-plan, immediate callers and
   tests included. Discussed with the chair **before any code
   changes**.
5. Remainder per act-now bucket: refactor-plan restricted to the two
   outliers (bridge.py, widget.py), targeted security-audit at input/
   MCP boundaries (mcp_server.py, markdown_ingestion.py, bridge.py),
   smart-test gap map, then a test-suite quality pass (brittle mocks,
   duplicated fixtures).

## Decision rule (chair-adopted, answers msgs 3/5/7)

All three seats converged on the same follow-up: what counts as pilot
success? Ruling:

- A validated **"leave intact except for these seams"** verdict is a
  full success, not a null result.
- **LOC alone never triggers decomposition** — only a nameable
  concrete cost (bug rate, merge friction, onboarding) or an
  isolatable failure domain / untestable state machine.

## Dissent preserved

- Claude seat nominated widget.py as pilot (holdable in one
  discussion; ratified pattern transfers to bridge.py as precedent) —
  overruled by majority, preserved here as the fallback if the
  bridge.py example proves too large to discuss whole.
- Codex ranked plugin skills as the highest user-ease surface and
  placed them 2nd; adopted (step 2 above) over the other seats'
  skills-last ordering.
