"""Shared form theme (workflow-intake-forms Task 3): budget,
projection byte-equality, fallback coverage, shared-by-source."""

from __future__ import annotations

import re

from attune_forms import theme
from attune_forms import widget as widget_mod

#: Chair-ruled cap (workflow-intake-forms decisions.md D1: 4 KB -> 6 KB
#: with the 5,574 B measurement; 6 KB -> 8 KB with the grammar-expansion
#: merge, 8,158 B; 8 KB -> 10 KB ratified 2026-08-15, ranking-construct
#: decisions.md D2-a — a consolidation pass was offered and NOT chosen,
#: so the cap is not a ratchet: the next raise needs its own ruling).
_BUDGET_BYTES = 12288

#: ``var(--name)`` with NO fallback value — the pattern the theme
#: must never contain (host-token fallbacks are the design).
_NO_FALLBACK_RE = re.compile(r"var\(--[a-zA-Z0-9-]+\)")


def test_form_theme_budget() -> None:
    size = len(theme.FORM_THEME_CSS.encode("utf-8"))
    assert size <= _BUDGET_BYTES, (
        f"FORM_THEME_CSS is {size} B (> {_BUDGET_BYTES}); growing the "
        "theme past the cap is a design decision — see "
        "docs/specs/workflow-intake-forms/decisions.md D1"
    )


def test_forbidden_latency_constructs_absent() -> None:
    low = theme.FORM_THEME_CSS.lower()
    for banned in ("@import", "@font-face", "url("):
        assert banned not in low, f"{banned!r} is the latency regression the design forbids"


def test_every_var_reference_carries_a_fallback() -> None:
    bare = _NO_FALLBACK_RE.findall(theme.FORM_THEME_CSS)
    assert not bare, f"var() references without fallbacks: {sorted(set(bare))}"


def test_widget_css_is_theme_source_by_identity() -> None:
    """Shared-by-SOURCE: the widget's CSS objects ARE the theme's."""
    assert widget_mod._CSS_BASE is theme.CSS_BASE
    assert widget_mod._CSS_FAMILIES is theme.CSS_FAMILIES


def test_full_sheet_is_base_plus_all_families_in_order() -> None:
    expected = theme.CSS_BASE + "".join(css for _n, css in theme.CSS_FAMILIES)
    assert theme.FORM_THEME_CSS == expected


def test_semantic_state_matrix_is_present() -> None:
    css = theme.FORM_THEME_CSS
    for state in (
        ":hover",
        ":focus-visible",
        ":disabled",
        ":checked",
        ".ae-field-missing",
        "prefers-reduced-motion",
    ):
        assert state in css
    for role in (
        "--ae-action",
        "--ae-success",
        "--ae-warning",
        "--ae-danger",
        "--ae-recommendation",
        "--ae-focus",
    ):
        assert role in css


#: A selector's STYLED class: the last ``.class`` token before the rule
#: body (pseudo-classes stripped). ``.ae-card .ae-prog-tag`` styles
#: ``ae-prog-tag``; ``.ae-card:hover`` styles ``ae-card``.
_SELECTOR_RE = re.compile(r"([^{}]+)\{")
_CLASS_RE = re.compile(r"\.([A-Za-z0-9_-]+)")


def _styled_classes(block: str) -> set[str]:
    styled: set[str] = set()
    for match in _SELECTOR_RE.finditer(block):
        selector = match.group(1).split(":")[0]
        classes = _CLASS_RE.findall(selector)
        if classes:
            styled.add(classes[-1])
    return styled


def test_no_class_is_styled_in_two_blocks() -> None:
    """Same-name collision guard (confirm-construct D3).

    The coverage guard in test_widget_css_families only catches
    UNSTYLED classes; it is structurally blind to two blocks styling
    the same class name — which is how the CONFIRM family's first
    wrapper (``.ae-confirm``) silently inherited the BASE
    fully-inferred banner's accent border. Every class may be styled
    by exactly one block (contextual restyling of ANOTHER family's
    class counts as a collision too — a family must not reach into
    a sibling's names).
    """
    blocks = [("BASE", theme.CSS_BASE), *theme.CSS_FAMILIES]
    owners: dict[str, str] = {}
    collisions: list[str] = []
    for name, css in blocks:
        for cls in _styled_classes(css):
            if cls in owners and owners[cls] != name:
                collisions.append(f"{cls!r} styled in both {owners[cls]} and {name}")
            owners.setdefault(cls, name)
    assert not collisions, "; ".join(collisions)
