"""Fix-first command workspace model and renderer receipts."""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from attune_forms import (
    WorkspaceAction,
    WorkspaceActionIntent,
    WorkspaceBlock,
    WorkspaceBlockKind,
    WorkspaceItem,
    WorkspaceSection,
    WorkspaceView,
    WorkspaceViewId,
    form_from_dict,
    form_to_widget_html,
    workspace_to_markdown,
    workspace_to_widget_html,
)
from attune_forms.models import QuestionType
from attune_forms.tokens import SEMANTIC_TOKENS, token
from tests.fixtures.workspace_showcase import showcase_views


def test_semantic_token_artifact_is_versioned_and_scalar_lookup_works() -> None:
    assert SEMANTIC_TOKENS["version"] == 1
    assert token("color.light.action") == "#004ac6"
    with pytest.raises(KeyError, match="mapping"):
        token("color.light")
    with pytest.raises(TypeError):
        SEMANTIC_TOKENS["color"]["light"]["action"] = "#f00"


def test_workspace_rejects_executable_shape_and_ambiguous_authority() -> None:
    with pytest.raises(ValueError, match="action id"):
        WorkspaceAction(id="alert(1)", label="Bad")
    with pytest.raises(ValueError, match="consequence"):
        WorkspaceAction(id="run", label="Run", requires_explicit_choice=True)
    with pytest.raises(ValueError, match="at most one primary"):
        WorkspaceView(
            id=WorkspaceViewId.PREVIEW,
            title="T",
            actions=(
                WorkspaceAction("a", "A", WorkspaceActionIntent.PRIMARY),
                WorkspaceAction("b", "B", WorkspaceActionIntent.PRIMARY),
            ),
        )
    with pytest.raises(ValueError, match="code block requires body"):
        WorkspaceBlock(WorkspaceBlockKind.CODE)
    with pytest.raises(ValueError, match="language identifier"):
        WorkspaceBlock(
            WorkspaceBlockKind.CODE,
            body="safe",
            language="text\n```\ninjected",
        )
    with pytest.raises(TypeError, match="block kind"):
        WorkspaceBlock("code", body="x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="section tone"):
        WorkspaceSection(blocks=(WorkspaceBlock(WorkspaceBlockKind.CODE, body="x"),), tone="x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="action intent"):
        WorkspaceAction("run", "Run", intent="primary")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="view id"):
        WorkspaceView(id="preview", title="T")  # type: ignore[arg-type]


def test_form_view_requires_exactly_one_submit_action() -> None:
    form = form_from_dict(
        {"title": "T", "fields": [{"id": "x", "text": "X?", "type": "text_input"}]}
    )
    with pytest.raises(ValueError, match="exactly one"):
        WorkspaceView(id=WorkspaceViewId.INTAKE, title="T", form=form)


def test_showcase_covers_every_view_construct_and_display_block() -> None:
    views = showcase_views()
    assert {view.id for view in views} == set(WorkspaceViewId)
    intake = views[0]
    assert intake.form is not None
    assert {q.type for q in intake.form.questions} == set(QuestionType)
    kinds = {block.kind for view in views for section in view.sections for block in section.blocks}
    assert kinds == set(WorkspaceBlockKind)


def test_widget_form_action_uses_specific_label_and_stable_id() -> None:
    html = workspace_to_widget_html(showcase_views()[0], instance_id="showcase")
    assert 'data-workspace-view="intake"' in html
    assert ">Preview fix</button>" in html
    assert "payload.action = submitAction" in html
    assert 'var submitAction = "preview_fix"' in html
    assert 'var submitView = "intake"' in html
    assert 'data-form-title="Fix"' in html
    assert html.count("<h2") == 1
    assert "<h3>All Constructs Reference</h3>" not in html
    assert "@import" not in html


def test_public_widget_context_rejects_script_values() -> None:
    form = showcase_views()[0].form
    assert form is not None
    with pytest.raises(ValueError, match="stable lowercase identifier"):
        form_to_widget_html(form, submit_action="</script><img src=x>")


def test_widget_display_actions_post_only_stable_action_id() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="preview")
    assert 'data-workspace-action="run_fix" data-explicit="1"' in html
    assert 'data-workspace-action="edit_contract"' in html
    assert "action:b.getAttribute('data-workspace-action')" in html
    assert "typeof sendPrompt==='function'" in html
    assert "window.confirm(consequence)" in html
    assert 'data-consequence="Execute the previewed contract."' in html
    assert "Workspace action submitted" in html
    assert "view:root.getAttribute('data-workspace-view')" in html
    assert 'role="status" aria-live="polite"' in html
    assert "x.disabled=true" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_widget_display_action_script_parses() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="parse")
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script is not None
    result = subprocess.run(
        ["node", "--check"],
        input=script.group(1),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_form_workspace_preserves_explicit_action_semantics() -> None:
    intake = showcase_views()[0]
    action = WorkspaceAction(
        "preview_fix",
        "Preview fix",
        WorkspaceActionIntent.PRIMARY,
        consequence="Build the deterministic preview.",
        requires_explicit_choice=True,
    )
    view = WorkspaceView(
        id=intake.id,
        title=intake.title,
        form=intake.form,
        actions=(action,),
    )
    html = workspace_to_widget_html(view, instance_id="explicit")
    assert "Build the deterministic preview." in html
    assert "window.confirm(form.getAttribute('data-submit-consequence'))" in html
    markdown = workspace_to_markdown(view)
    assert "**Explicit confirmation required:** Build the deterministic preview." in markdown
    assert "<script>alert" not in html


def test_workspace_markdown_preserves_sections_actions_and_form_state() -> None:
    intake_md = workspace_to_markdown(showcase_views()[0])
    skeleton = json.loads(intake_md.split("```json")[-1].split("```")[0])
    assert skeleton["action"] == "preview_fix"
    assert skeleton["view"] == "intake"
    assert set(skeleton["answers"])
    assert intake_md.count("## Fix") == 1
    preview_md = workspace_to_markdown(showcase_views()[1])
    assert "### Contract" in preview_md
    assert "`run_fix` — Run Fix" in preview_md
    assert "Execute the previewed contract" in preview_md
    action_skeleton = json.loads(preview_md.split("```json")[-1].split("```")[0])
    assert action_skeleton["view"] == "preview"
    assert action_skeleton["action"] is None


def test_workspace_markdown_escapes_evidence_table_cells() -> None:
    receipt = showcase_views()[-1]
    evidence = receipt.sections[0].blocks[-1]
    unsafe = WorkspaceBlock(
        WorkspaceBlockKind.EVIDENCE,
        items=(WorkspaceItem("lint | test", "a | b", detail="line 1\nline 2"),),
    )
    view = WorkspaceView(
        id=receipt.id,
        title=receipt.title,
        sections=(WorkspaceSection(blocks=(evidence, unsafe)),),
    )
    markdown = workspace_to_markdown(view)
    assert "lint \\| test" in markdown
    assert "a \\| b" in markdown
    assert "line 1<br>line 2" in markdown


def test_workspace_markdown_contains_multiline_author_text() -> None:
    view = WorkspaceView(
        id=WorkspaceViewId.EXECUTION,
        title="Run *fix*",
        sections=(
            WorkspaceSection(
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.TIMELINE,
                        items=(WorkspaceItem("Edit", "one\ntwo", "three\nfour"),),
                    ),
                ),
            ),
        ),
    )
    markdown = workspace_to_markdown(view)
    assert "Run \\*fix\\*" in markdown
    assert "one<br>two" in markdown
    assert "three<br>four" in markdown


def test_workspace_escapes_all_author_text() -> None:
    view = WorkspaceView(
        id=WorkspaceViewId.RECEIPT,
        title="<img src=x onerror=alert(1)>",
        sections=(
            WorkspaceSection(
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.KEY_VALUE,
                        items=(WorkspaceItem("<script>", "<b>unsafe</b>"),),
                    ),
                ),
            ),
        ),
        actions=(WorkspaceAction(id="inspect", label="Inspect"),),
    )
    html = workspace_to_widget_html(view, instance_id="escape")
    assert "<img" not in html and "<b>unsafe" not in html and "<script></script>" not in html
    assert "&lt;script&gt;" in html
    assert "</script><img" not in html
    assert "title:root.getAttribute('data-workspace-title')" in html


def test_workspace_instance_suffix_is_ascii_only() -> None:
    html = workspace_to_widget_html(showcase_views()[2], instance_id="fooｓ²")
    assert 'id="attune-workspace-foo"' in html
    hyphenated = workspace_to_widget_html(showcase_views()[2], instance_id="fix-1")
    compact = workspace_to_widget_html(showcase_views()[2], instance_id="fix1")
    assert 'id="attune-workspace-fix-1"' in hyphenated
    assert 'id="attune-workspace-fix1"' in compact
