"""Shared form theme (workflow-intake-forms Task 3): budget,
projection byte-equality, fallback coverage, shared-by-source."""

from __future__ import annotations

import re
from attune_forms import theme
from attune_forms import widget as widget_mod

#: Chair-ruled cap (spec decisions.md D1: amended 4 KB -> 6 KB with
#: the 5,574 B full-sheet measurement on record).
_BUDGET_BYTES = 6144

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
