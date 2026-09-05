"""Authoring preview (spec R5.4): stored templates through the production renderer."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import attune_forms.preview as preview
from attune_forms import WIDGET_RESPONSE_MARKER, FormValidationError, list_templates
from attune_forms.form_events import _events_path


def test_page_renders_every_stored_template_through_the_production_renderer(monkeypatch):
    calls: list[str] = []
    real = preview.form_to_widget_html

    def spy(form, message="", **kw):
        calls.append(form.title)
        return real(form, message, **kw)

    monkeypatch.setattr(preview, "form_to_widget_html", spy)
    page = preview.preview_page()
    assert page.startswith("<!doctype html>")
    names = list_templates()
    assert len(calls) == len(names) >= 1
    for name in names:
        assert f'id="tpl-{name}"' in page
    # session-contract cast with its example slots: title substituted, no
    # placeholder residue in the rendered widget (the header's slot legend
    # shows the placeholder on purpose).
    assert "Session contract — attune-ai" in page
    assert "Session contract — {project}" not in page
    assert page.count(WIDGET_RESPONSE_MARKER) >= len(names)


def test_named_subset_and_unknown_name():
    page = preview.preview_page(["session-contract"])
    assert page.count('class="afp-section"') == 1
    with pytest.raises(FormValidationError) as exc:
        preview.preview_page(["no-such-template"])
    assert any("session-contract" in p for p in exc.value.problems)
    with pytest.raises(FormValidationError):
        preview.preview_page([])


def test_message_is_rendered_above_each_form():
    page = preview.preview_page(["session-contract"], message="Fill before non-trivial work")
    assert "Fill before non-trivial work" in page


def test_preview_casts_emit_no_telemetry(monkeypatch):
    monkeypatch.delenv("ATTUNE_FORMS_TELEMETRY", raising=False)
    monkeypatch.delenv("ATTUNE_FORM_TELEMETRY", raising=False)
    preview.preview_page()
    events = _events_path()
    assert not events.exists() or "form_build" not in events.read_text(encoding="utf-8")
    assert "ATTUNE_FORMS_TELEMETRY" not in os.environ  # restored


def test_shell_defines_host_tokens_for_both_schemes():
    page = preview.preview_page(["session-contract"])
    assert "--primary:" in page and "--surface-1:" in page
    assert '[data-theme="dark"]' in page and "prefers-color-scheme: dark" in page
    assert "window.sendPrompt = function" in page


def test_write_preview_validates_the_path(tmp_path: Path):
    out = preview.write_preview(tmp_path / "preview.html", ["session-contract"])
    assert out.is_file() and "Session contract" in out.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="must end in .html"):
        preview.write_preview(tmp_path / "preview.txt")
    with pytest.raises(ValueError, match="does not exist"):
        preview.write_preview(tmp_path / "missing" / "p.html")
    (tmp_path / "dir.html").mkdir()
    with pytest.raises(ValueError, match="not a file"):
        preview.write_preview(tmp_path / "dir.html")


def test_main_writes_lists_opens_and_reports_problems(tmp_path: Path, monkeypatch, capsys):
    opened: list[str] = []
    monkeypatch.setattr(preview.webbrowser, "open", lambda uri: opened.append(uri))
    out = tmp_path / "p.html"
    assert preview.main(["--out", str(out), "--open"]) == 0
    assert out.is_file() and opened == [out.as_uri()]
    assert preview.main(["--list"]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] in list_templates()
    assert preview.main(["--out", str(out), "no-such-template"]) == 1
    assert "no-such-template" in capsys.readouterr().err
    assert preview.main(["--out", str(tmp_path / "x.txt")]) == 1
