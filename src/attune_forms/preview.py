"""Authoring preview for stored form templates (spec R5.4).

Renders every stored template — cast with its ``example_slots`` (R5.3)
through :func:`~attune_forms.template_store.form_from_template` — into
ONE standalone HTML page via the PRODUCTION widget renderer,
:func:`~attune_forms.widget.form_to_widget_html`. Nothing is re-drawn
here: the page is the renderer's own output inside a small host shell
that supplies the design-system variables a live host would (light and
dark), plus a ``sendPrompt`` stub that prints the payload the widget
posts. A template edit is therefore seen exactly as users will see it —
the ratified preview discipline (a preview that duplicates render logic
drifts from the real surface and proves nothing).

Preview casts are NOT adoption signal: form telemetry is suppressed for
the duration of the render so the ``form_build`` meter keeps counting
real forms only.

Usage::

    python -m attune_forms.preview --open            # every template
    python -m attune_forms.preview session-contract  # named ones
    attune-forms-preview --out docs/preview.html     # console script

Copyright 2026 Smart-AI-Memory
Licensed under Apache 2.0
"""

from __future__ import annotations

import argparse
import html
import os
import sys
import webbrowser
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from attune_forms.bridge import FormValidationError
from attune_forms.template_store import (
    form_from_template,
    list_templates,
    template_example_slots,
)
from attune_forms.theme import token
from attune_forms.widget import form_to_widget_html

#: Host variables the widget reads (each ``--ae-*`` token falls back to
#: ``var(--<host>, <default>)``), so the shell defines the host names for
#: both schemes and the renderer's own fallbacks stay untouched.
_HOST_VARS = {
    "--primary": "action",
    "--primary-dark": "action_hover",
    "--text-success": "success",
    "--text-accent": "warning",
    "--text-danger": "danger",
    "--accent": "recommendation",
    "--text-primary": "neutral_text",
    "--text-muted": "neutral_muted",
    "--surface-1": "surface",
    "--surface-2": "surface_raised",
    "--border": "border",
    "--focus-ring": "focus",
}


def _host_vars(scheme: str) -> str:
    return " ".join(f"{name}:{token(f'color.{scheme}.{key}')};" for name, key in _HOST_VARS.items())


@contextmanager
def _telemetry_off() -> Iterator[None]:
    """Suppress form telemetry while preview casts run (restored after)."""
    previous = os.environ.get("ATTUNE_FORMS_TELEMETRY")
    os.environ["ATTUNE_FORMS_TELEMETRY"] = "0"
    try:
        yield
    finally:
        if previous is None:
            del os.environ["ATTUNE_FORMS_TELEMETRY"]
        else:
            os.environ["ATTUNE_FORMS_TELEMETRY"] = previous


def _section(name: str, message: str) -> str:
    slots = template_example_slots(name)
    form = form_from_template(name, slots)
    widget = form_to_widget_html(form, message)
    slot_rows = "".join(
        f"<li><code>{{{html.escape(k)}}}</code> = {html.escape(v)}</li>"
        for k, v in sorted(slots.items())
    )
    return (
        f'<section class="afp-section" id="tpl-{html.escape(name)}">\n'
        f"<header><h2><code>{html.escape(name)}</code></h2>"
        f"<p>{len(form.questions)} field(s) · example slots:</p>"
        f'<ul class="afp-slots">{slot_rows or "<li>(none)</li>"}</ul></header>\n'
        f'<div class="afp-widget">{widget}</div>\n'
        '<details class="afp-payload"><summary>Posted payload (submit the form)</summary>'
        "<pre data-payload>— nothing posted yet —</pre></details>\n"
        "</section>\n"
    )


def preview_page(names: Iterable[str] | None = None, *, message: str = "") -> str:
    """Return one standalone HTML page previewing the stored templates.

    Args:
        names: Template names to include (default: every stored template,
            in :func:`list_templates` order).
        message: Optional prompt rendered above each form, as an agent
            would pass it.

    Raises:
        FormValidationError: An unknown name, a template without
            ``example_slots``, or a cast that fails validation — every
            problem listed, exactly as the MCP tools would report it.
    """
    selected = list(names) if names is not None else list_templates()
    if not selected:
        raise FormValidationError(["no templates to preview"])
    with _telemetry_off():
        sections = "".join(_section(name, message) for name in selected)
    nav = "".join(
        f'<li><a href="#tpl-{html.escape(n)}"><code>{html.escape(n)}</code></a></li>'
        for n in selected
    )
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>attune-forms template preview</title>
<style>
:root {{ color-scheme: light; {_host_vars("light")} }}
:root[data-theme="dark"] {{ color-scheme: dark; {_host_vars("dark")} }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ color-scheme: dark; {_host_vars("dark")} }} }}
body {{ margin:0; font-family:system-ui,sans-serif; color:var(--text-primary); background:var(--surface-1); }}
.afp-top {{ display:flex; align-items:baseline; gap:1rem; flex-wrap:wrap; padding:1rem 1.5rem; border-bottom:1px solid var(--border); }}
.afp-top h1 {{ font-size:18px; margin:0; }}
.afp-top nav ul {{ display:flex; gap:.75rem; list-style:none; margin:0; padding:0; flex-wrap:wrap; }}
.afp-top .afp-meta {{ margin-left:auto; color:var(--text-muted); font-size:13px; }}
.afp-section {{ max-width:720px; margin:0 auto; padding:1.5rem; border-bottom:1px solid var(--border); }}
.afp-section h2 {{ font-size:16px; margin:0 0 .25rem; }}
.afp-section header p {{ margin:0; color:var(--text-muted); font-size:13px; }}
.afp-slots {{ margin:.25rem 0 0; padding-left:1.25rem; font-size:13px; color:var(--text-muted); }}
.afp-widget {{ background:var(--surface-2); border:1px solid var(--border); border-radius:12px; padding:0 1rem; margin:1rem 0; }}
.afp-payload pre {{ white-space:pre-wrap; word-break:break-word; font-size:12px; background:var(--surface-2); border:1px solid var(--border); border-radius:8px; padding:.75rem; }}
button.afp-theme {{ font:inherit; font-size:13px; padding:.25rem .6rem; border:1px solid var(--border); border-radius:8px; background:var(--surface-2); color:inherit; cursor:pointer; }}
</style>
</head>
<body>
<div class="afp-top">
<h1>attune-forms template preview</h1>
<nav aria-label="Templates"><ul>{nav}</ul></nav>
<span class="afp-meta">{len(selected)} template(s) · generated {stamp} · production renderer</span>
<button type="button" class="afp-theme" id="afp-theme">Toggle dark</button>
</div>
{sections}
<script>
(function () {{
  var root = document.documentElement;
  document.getElementById("afp-theme").addEventListener("click", function () {{
    var dark = root.getAttribute("data-theme") === "dark" ||
      (!root.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
    root.setAttribute("data-theme", dark ? "light" : "dark");
  }});
  // The widget posts its answers through the host's global sendPrompt;
  // here it lands in the nearest section's payload pane instead.
  window.sendPrompt = function (text) {{
    var active = document.activeElement;
    var section = active && active.closest ? active.closest(".afp-section") : null;
    var pane = (section || document).querySelector("[data-payload]");
    if (pane) {{ pane.textContent = text; pane.closest("details").open = true; }}
  }};
}})();
</script>
</body>
</html>
"""


def write_preview(path: str | os.PathLike[str], names: Iterable[str] | None = None) -> Path:
    """Write :func:`preview_page` to ``path`` and return the resolved path.

    The path must end in ``.html`` and its parent must be an existing
    directory (no directory creation, no other suffixes — the only thing
    this writes is the preview page).
    """
    target = Path(path).expanduser().resolve()
    if target.suffix.lower() != ".html":
        raise ValueError(f"preview path must end in .html: {target}")
    if not target.parent.is_dir():
        raise ValueError(f"preview directory does not exist: {target.parent}")
    if target.exists() and not target.is_file():
        raise ValueError(f"preview path is not a file: {target}")
    target.write_text(preview_page(names), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    """Console-script entry point (``attune-forms-preview``)."""
    parser = argparse.ArgumentParser(
        prog="attune-forms-preview",
        description="Render stored form templates through the production widget renderer.",
    )
    parser.add_argument("names", nargs="*", help="template names (default: all)")
    parser.add_argument("--out", default="attune-forms-preview.html", help="output .html path")
    parser.add_argument("--open", action="store_true", help="open the page in a browser")
    parser.add_argument("--list", action="store_true", help="list stored templates and exit")
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(list_templates()))
        return 0
    try:
        target = write_preview(args.out, args.names or None)
    except (FormValidationError, ValueError, OSError) as exc:
        problems = getattr(exc, "problems", [str(exc)])
        print("preview failed:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 1
    print(target)
    if args.open:
        webbrowser.open(target.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
