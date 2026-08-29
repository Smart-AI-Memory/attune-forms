"""Shared form theme — the ONE tracked CSS source for intake forms.

workflow-intake-forms Task 3 (design.md "The shared look"): every
form surface renders from this module's CSS, projected — never
hand-copied:

- **Widgets** (claude.ai): ``form_to_widget_html`` injects the
  needed family blocks inline (the widget sandbox's CSP forbids
  external stylesheet fetches, so shared means shared-by-SOURCE).
- **Ops dashboard**: the full ``FORM_THEME_CSS`` string is served
  as ``/static/form-theme.css`` from a projected file that a drift
  test keeps byte-equal to the constant.

Every ``var()`` reference carries a literal fallback, so one
stylesheet renders native on claude.ai (host tokens win,
light/dark follows the host) and standalone (fallbacks win).

Budget: ``FORM_THEME_CSS`` is capped at 12 KB raw by
``test_form_theme_budget`` (4 KB → 6 KB by chair ruling 2026-07-31;
6 KB → 8 KB ratified with the grammar-expansion merge 2026-08-14 —
TRIAGE + CONFIRM families + deliberation seat chips, 8,158 B; 8 KB →
10 KB ratified 2026-08-15 for the 0.6.0 constructs, ranking-construct
spec D2-a — the RANK family did not fit under 8 KB; a CSS
consolidation pass was offered and not chosen, so the cap is NOT a
ratchet: growth past it is a design decision, not a drift; 10 KB →
12 KB chair-ruled 2026-08-28 for the shared ``ae-detail-block`` rule
in CSS_BASE, which lets a MULTI-LINE item detail — a diff hunk, a log
excerpt — keep its newlines instead of collapsing inside a flex row,
across triage / assumption_review / progress / confirm at once; a
trim to fit under 10 KB was offered and declined) — no fonts, no icon
fonts, no images, no @import. Bar for the next raise (chair-ruled at
the 2026-08-28 retro): raises buy FAMILIES, not rules — a single rule
that fits after a trim does not clear it.

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

from attune_forms.tokens import token

CSS_SEMANTIC_TOKENS = (
    "#attune-elicit-form {\n"
    f"  --ae-action:var(--primary,{token('color.light.action')}); "
    f"--ae-action-hover:var(--primary-dark,{token('color.light.action_hover')});\n"
    f"  --ae-success:var(--text-success,{token('color.light.success')}); "
    f"--ae-warning:var(--text-accent,{token('color.light.warning')});\n"
    f"  --ae-danger:var(--text-danger,{token('color.light.danger')}); "
    f"--ae-recommendation:var(--accent,{token('color.light.recommendation')});\n"
    f"  --ae-text:var(--text-primary,{token('color.light.neutral_text')}); "
    f"--ae-muted:var(--text-muted,{token('color.light.neutral_muted')});\n"
    f"  --ae-surface:var(--surface-1,{token('color.light.surface')}); "
    f"--ae-surface-raised:var(--surface-2,{token('color.light.surface_raised')});\n"
    f"  --ae-border:var(--border,{token('color.light.border')}); "
    f"--ae-focus:var(--focus-ring,{token('color.light.focus')});\n"
    f"  --ae-radius-control:{token('radius.control')}; "
    f"--ae-radius-panel:{token('radius.panel')};\n"
    f"  --ae-space-md:{token('spacing.md')};\n"
    f"  --ae-motion-fast:{token('motion.fast')}; "
    f"--ae-motion-normal:{token('motion.normal')}; "
    f"--ae-target-min:{token('control.minimum_target')};\n"
    f"  --ae-font-body:{token('typography.body')}; "
    f"--ae-font-heading:{token('typography.heading')}; "
    f"--ae-font-mono:{token('typography.mono')}; }}\n"
)

#: Base rules every form emits (scoped under ``#attune-elicit-form``;
#: the widget renderer rewrites the id per instance).
CSS_BASE = (
    CSS_SEMANTIC_TOKENS
    + """#attune-elicit-form { display:block; width:100%; padding:1rem 0;
  color:var(--ae-text,#0b1c30); line-height:1.5; font-family:var(--ae-font-body,system-ui); }
#attune-elicit-form .sr-only { position:absolute; width:1px; height:1px;
  overflow:hidden; clip:rect(0 0 0 0); }
#attune-elicit-form h3 { font-family:var(--ae-font-heading,system-ui); font-size:18px;
  font-weight:650; letter-spacing:-.015em; margin:0 0 .25rem; }
#attune-elicit-form .ae-msg { margin:0 0 .5rem; color:var(--text-secondary,#5f5e59); }
#attune-elicit-form .ae-desc { margin:0 0 1rem; color:var(--text-muted,#8a887f);
  font-size:15px; }
#attune-elicit-form .ae-field { margin:0 0 1rem; }
#attune-elicit-form .ae-label { display:block; font-weight:500;
  margin:0 0 .35rem; }
#attune-elicit-form .ae-req { color:var(--text-accent,#a1571c); margin-left:2px; }
#attune-elicit-form .ae-confirm { font-size:14px; color:var(--text-secondary,#5f5e59);
  border-left:3px solid var(--border-accent,#d8b89a); border-radius:0;
  padding:.35rem .6rem; margin:0 0 1rem; }
#attune-elicit-form .ae-inferred { font-size:13px; color:var(--text-muted,#8a887f);
  margin:0 0 .35rem; }
#attune-elicit-form .ae-inferred-b { display:inline-block; font-size:11px;
  font-weight:500; text-transform:uppercase; letter-spacing:.04em;
  color:var(--text-accent,#a1571c); background:var(--bg-accent,#f3ece4);
  border:1px solid var(--border-accent,#d8b89a); border-radius:var(--radius,8px);
  padding:0 .35rem; margin-right:.4rem; }
#attune-elicit-form .ae-help { font-size:13px; color:var(--text-muted,#8a887f);
  margin:0 0 .35rem; }
#attune-elicit-form .ae-submit { margin-top:.5rem; padding:.55rem 1.1rem;
  min-height:var(--ae-target-min,2.5rem); font-size:15px; font-weight:600; cursor:pointer;
  color:#fff; background:var(--ae-action,#004ac6); border:1px solid var(--ae-action,#004ac6);
  border-radius:var(--ae-radius-control,8px); transition:background var(--ae-motion-fast,120ms); }
#attune-elicit-form .ae-submit:hover { background:var(--ae-action-hover,#003ea8); }
#attune-elicit-form .ae-submit:disabled { opacity:.6; cursor:default; }
#attune-elicit-form .ae-error { margin-top:.5rem; font-size:14px;
  color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-field-missing { border-left:3px solid
  var(--ae-danger,#ba1a1a); padding-left:.6rem; }
#attune-elicit-form :is(input,select,textarea,button):focus-visible {
  outline:3px solid var(--ae-focus,#2563eb); outline-offset:2px; }
#attune-elicit-form :is(input,select,textarea,button):disabled { opacity:.6; cursor:not-allowed; }
#attune-elicit-form .ae-detail-block { flex-basis:100%; white-space:pre-wrap;
  font-family:var(--ae-font-mono,ui-monospace);
  overflow-x:auto; }
@media (prefers-reduced-motion:reduce) { #attune-elicit-form * {
  scroll-behavior:auto!important; transition-duration:0ms!important;
  animation-duration:0ms!important; } }
"""
)

#: INPUT — text_input, textarea, number, date, boolean, non-list single_select.
CSS_INPUT = """#attune-elicit-form .ae-input { width:100%; box-sizing:border-box;
  min-height:var(--ae-target-min,2.5rem); padding:.5rem .6rem;
  font-size:15px; color:var(--text-primary,#2c2c2a);
  background:var(--surface-1,#f7f6f3); border:1px solid var(--border,#e3e1dc);
  border-radius:var(--radius,8px); }
#attune-elicit-form .ae-textarea { resize:vertical; min-height:3.5rem; }
"""

#: CHECKS — non-list multi_select (checkbox rows).
CSS_CHECKS = """#attune-elicit-form .ae-checks { display:flex; flex-direction:column;
  gap:.35rem; }
#attune-elicit-form .ae-check { display:flex; align-items:center; gap:.5rem;
  font-weight:400; }
"""

#: LIST — any select rendered with ``list_style``.
CSS_LIST = """#attune-elicit-form .ae-list { margin:0; padding-left:1.6rem;
  display:flex; flex-direction:column; gap:.3rem; }
#attune-elicit-form .ae-list-item label { display:inline-flex;
  align-items:baseline; gap:.45rem; cursor:pointer; font-weight:400; }
"""

#: CARDS — decision / pushback option cards + the rationale callout (also
#: reused by the progress blocked-picker).
CSS_CARDS = """#attune-elicit-form .ae-cards { display:flex; flex-direction:column; gap:.5rem; }
#attune-elicit-form .ae-card { position:relative; display:flex;
  flex-direction:column; gap:.15rem; padding:.6rem 1.9rem .6rem .75rem;
  border:1px solid var(--border,#e3e1dc); border-radius:var(--radius,8px);
  cursor:pointer; }
#attune-elicit-form .ae-card:hover { border-color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-card-rec { border-color:var(--ae-recommendation,#7c3aed); }
#attune-elicit-form .ae-card:has(input:checked) { border-color:var(--ae-action,#004ac6);
  background:var(--ae-surface-raised,#eff4ff); }
#attune-elicit-form .ae-card input { position:absolute; top:.7rem; right:.6rem; }
#attune-elicit-form .ae-card-title { font-weight:500; }
#attune-elicit-form .ae-card-note { font-size:13px; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-rec-badge { font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-yours-tag { font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-rationale { margin:.6rem 0 0; padding:.4rem 0 .4rem .75rem;
  font-size:13px; color:var(--text-secondary,#5f5e59);
  border-left:2px solid var(--border-accent,#d8b89a); }
#attune-elicit-form .ae-rationale-h { display:block; font-weight:600;
  font-size:11px; text-transform:uppercase; letter-spacing:.03em;
  color:var(--text-accent,#a1571c); margin-bottom:.15rem; }
#attune-elicit-form .ae-seats { display:flex; gap:.3rem; flex-wrap:wrap; }
#attune-elicit-form .ae-seat { font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em;
  color:var(--text-secondary,#5f5e59); background:var(--surface-1,#f7f6f3);
  border:1px solid var(--border,#e3e1dc); border-radius:3px; padding:0 .35em; }
"""

#: PROGRESS — the done/in_flight/blocked status rows (pulls CARDS too).
CSS_PROGRESS = """#attune-elicit-form .ae-progress { display:flex; flex-direction:column; gap:.5rem; }
#attune-elicit-form .ae-prog-rows { display:flex; flex-direction:column; gap:.25rem; }
#attune-elicit-form .ae-prog-row { display:flex; align-items:baseline; gap:.5rem;
  flex-wrap:wrap; font-size:14px; color:var(--text-secondary,#5f5e59); }
#attune-elicit-form .ae-prog-icon { flex:none; font-weight:700; width:1.1em;
  text-align:center; }
#attune-elicit-form .ae-prog-done .ae-prog-icon { color:var(--text-success,#3fb950); }
#attune-elicit-form .ae-prog-in_flight .ae-prog-icon { color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-prog-blocked { color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-prog-detail { font-size:13px; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-prog-label { color:var(--text-primary,#2c2c2a); }
#attune-elicit-form .ae-prog-done .ae-prog-label { text-decoration:line-through;
  color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-prog-blocked-h { font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-prog-tag { flex:none; font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-muted,#8a887f);
  border:1px solid var(--border,#e3e1dc); border-radius:3px; padding:0 .3em; }
#attune-elicit-form .ae-card .ae-prog-tag { align-self:flex-start; }
#attune-elicit-form .ae-card .ae-prog-icon { margin-right:.15rem; }
"""

#: TRIAGE — the per-item ruling board (self-contained; no CARDS pull).
CSS_TRIAGE = """#attune-elicit-form .ae-triage { display:flex; flex-direction:column; gap:.6rem; }
#attune-elicit-form .ae-triage-row { display:flex; flex-direction:column;
  gap:.35rem; padding:.5rem .75rem; border:1px solid var(--border,#e3e1dc);
  border-radius:var(--radius,8px); }
#attune-elicit-form .ae-triage-head { display:flex; align-items:baseline;
  gap:.5rem; flex-wrap:wrap; }
#attune-elicit-form .ae-triage-label { font-weight:500;
  color:var(--text-primary,#2c2c2a); }
#attune-elicit-form .ae-triage-detail { font-size:13px;
  color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-triage-tag { flex:none; font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-muted,#8a887f);
  border:1px solid var(--border,#e3e1dc); border-radius:3px; padding:0 .3em; }
#attune-elicit-form .ae-triage-opts { display:flex; gap:.75rem; flex-wrap:wrap; }
#attune-elicit-form .ae-triage-opt { display:inline-flex; align-items:center;
  gap:.35rem; font-weight:400; cursor:pointer; }
#attune-elicit-form .ae-triage-sug { font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-accent,#a1571c); }
"""

#: CONFIRM — the consequences preview + two-way approve/abort gate.
CSS_CONFIRM = """#attune-elicit-form .ae-gate { display:flex; flex-direction:column; gap:.35rem; }
#attune-elicit-form .ae-gate-h { font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-gate-row { display:flex; align-items:baseline; gap:.5rem;
  flex-wrap:wrap; font-size:14px; color:var(--text-secondary,#5f5e59); }
#attune-elicit-form .ae-gate-label { color:var(--text-primary,#2c2c2a); }
#attune-elicit-form .ae-gate-detail { font-size:13px; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-gate-tag { flex:none; font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-accent,#a1571c);
  border:1px solid var(--border-accent,#d8b89a); border-radius:3px; padding:0 .3em; }
#attune-elicit-form .ae-gate-opts { display:flex; gap:1rem; flex-wrap:wrap;
  margin-top:.25rem; }
#attune-elicit-form .ae-gate-opt { font-weight:500; cursor:pointer; }
"""

#: RANK — the ranking list: a ranked <ol> + an unranked pool, moved by
#: buttons (no drag dependency). Button visibility follows the container:
#: pool rows show only "add", ranked rows only up / down / remove.
CSS_RANK = """#attune-elicit-form .ae-rank { display:flex; flex-direction:column; gap:.35rem; }
#attune-elicit-form .ae-rank-h { font-size:11px; font-weight:600;
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-rank-count { color:var(--text-primary,#2c2c2a); }
#attune-elicit-form .ae-rank-sug { margin-left:.5rem; font-size:10px; font-weight:600;
  text-transform:uppercase; letter-spacing:.04em; color:var(--text-accent,#a1571c); }
#attune-elicit-form .ae-rank-ranked, #attune-elicit-form .ae-rank-pool { margin:0;
  list-style:none; padding:.25rem .75rem; min-height:1.4rem;
  border:1px dashed var(--border,#e3e1dc); border-radius:var(--radius,8px); }
#attune-elicit-form .ae-rank-ranked { counter-reset:ae-rank; }
#attune-elicit-form .ae-rank-row { display:flex; align-items:center; gap:.5rem;
  padding:.15rem 0; }
#attune-elicit-form .ae-rank-ranked .ae-rank-row::before { counter-increment:ae-rank;
  content:counter(ae-rank) "."; min-width:1.4rem; color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-rank-label { flex:1; }
#attune-elicit-form .ae-rank-btns { display:inline-flex; gap:.25rem; }
#attune-elicit-form .ae-rank-btn { font-size:13px; line-height:1; padding:.1rem .45rem;
  cursor:pointer; color:var(--text-primary,#2c2c2a); background:var(--bg-accent,#f3ece4);
  border:1px solid var(--border-accent,#d8b89a); border-radius:var(--radius,8px); }
#attune-elicit-form .ae-rank-pool [data-rank="up"],
#attune-elicit-form .ae-rank-pool [data-rank="down"],
#attune-elicit-form .ae-rank-pool [data-rank="drop"],
#attune-elicit-form .ae-rank-ranked [data-rank="add"] { display:none; }
"""

#: ASSUME — the assumption review's additions to the triage row family:
#: the muted "from <source>" note and the replacement-text box, hidden
#: until the row's ruling is "edit" (the script toggles the class).
CSS_ASSUME = """#attune-elicit-form .ae-assume-src { font-size:12px; font-style:italic;
  color:var(--text-muted,#8a887f); }
#attune-elicit-form .ae-assume-edit { display:none; margin-top:.25rem; }
#attune-elicit-form .ae-assume-editing .ae-assume-edit { display:block; }
"""

#: Named family blocks in cascade-emission order (BASE is always first).
CSS_FAMILIES: list[tuple[str, str]] = [
    ("INPUT", CSS_INPUT),
    ("CHECKS", CSS_CHECKS),
    ("LIST", CSS_LIST),
    ("CARDS", CSS_CARDS),
    ("PROGRESS", CSS_PROGRESS),
    ("TRIAGE", CSS_TRIAGE),
    ("CONFIRM", CSS_CONFIRM),
    ("RANK", CSS_RANK),
    ("ASSUME", CSS_ASSUME),
]

#: The full theme: base + every family, in cascade order. This exact
#: string is what the ops dashboard serves at ``/static/form-theme.css``
#: (byte-equal by drift test) and what the 4 KB budget test measures.
FORM_THEME_CSS = CSS_BASE + "".join(css for _name, css in CSS_FAMILIES)

#: Workspace chrome is separate from ``FORM_THEME_CSS``: ordinary forms
#: never pay for command-workspace styles. It shares the exact semantic
#: token source and remains scoped/rewriteable like the form sheet.
CSS_WORKSPACE = (
    CSS_SEMANTIC_TOKENS.replace("#attune-elicit-form", "#attune-workspace")
    + """#attune-workspace { color:var(--ae-text,#0b1c30);
  font-family:var(--ae-font-body,system-ui); line-height:1.5; }
#attune-workspace .ae-ws-head { margin-bottom:var(--ae-space-md,1rem); }
#attune-workspace .ae-ws-title { font-family:var(--ae-font-heading,system-ui);
  font-size:20px; font-weight:650; letter-spacing:-.015em; margin:0; }
#attune-workspace .ae-ws-summary { color:var(--ae-muted,#5f6470); margin:.25rem 0 0; }
#attune-workspace .ae-ws-section { border-top:1px solid var(--ae-border,#c3c6d7);
  padding:1rem 0; }
#attune-workspace .ae-ws-section:first-of-type { border-top:0; }
#attune-workspace .ae-ws-section h4 { margin:0 0 .5rem; font-size:14px; font-weight:650; }
#attune-workspace .ae-ws-action { min-height:var(--ae-target-min,2.5rem);
  padding:.55rem 1rem; border-radius:var(--ae-radius-control,8px); cursor:pointer;
  border:1px solid var(--ae-border,#c3c6d7); background:transparent;
  color:var(--ae-text,#0b1c30); font-weight:600; }
#attune-workspace .ae-ws-action-primary { color:#fff;
  background:var(--ae-action,#004ac6); border-color:var(--ae-action,#004ac6); }
#attune-workspace .ae-ws-action-danger { color:var(--ae-danger,#ba1a1a);
  border-color:var(--ae-danger,#ba1a1a); }
#attune-workspace .ae-ws-actions { display:flex; flex-wrap:wrap; gap:.5rem; margin-top:1rem; }
#attune-workspace :is(button,summary):focus-visible { outline:3px solid
  var(--ae-focus,#2563eb); outline-offset:2px; }
#attune-workspace .ae-ws-kv { display:grid; grid-template-columns:minmax(7rem,auto) 1fr;
  gap:.35rem 1rem; margin:0; }
#attune-workspace .ae-ws-kv dt { color:var(--ae-muted,#5f6470); }
#attune-workspace .ae-ws-kv dd { margin:0; }
#attune-workspace .ae-ws-code { white-space:pre-wrap; overflow-x:auto;
  background:var(--ae-surface-raised,#eff4ff); border-radius:var(--ae-radius-control,8px);
  padding:.75rem; font-family:var(--ae-font-mono,ui-monospace); }
#attune-workspace .ae-ws-list { display:grid; gap:.4rem; padding-left:1.25rem; }
#attune-workspace .ae-ws-status { font-size:11px; font-weight:650;
  text-transform:uppercase; letter-spacing:.04em; color:var(--ae-muted,#5f6470); }
#attune-workspace .ae-ws-evidence { width:100%; border-collapse:collapse; font-size:14px; }
#attune-workspace .ae-ws-evidence :is(th,td) { padding:.4rem; text-align:left;
  border-bottom:1px solid var(--ae-border,#c3c6d7); }
#attune-workspace details { border:1px solid var(--ae-border,#c3c6d7);
  border-radius:var(--ae-radius-control,8px); padding:.5rem .75rem; }
@media (max-width:32rem) { #attune-workspace .ae-ws-kv { grid-template-columns:1fr; }
  #attune-workspace .ae-ws-kv dd { margin-bottom:.4rem; } }
@media (prefers-reduced-motion:reduce) { #attune-workspace * {
  transition-duration:0ms!important; animation-duration:0ms!important; } }
"""
)
