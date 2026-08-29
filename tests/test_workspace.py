"""Fix-first command workspace model and renderer receipts."""

from __future__ import annotations

import json

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
    assert "@import" not in html


def test_widget_display_actions_post_only_stable_action_id() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="preview")
    assert 'data-workspace-action="run_fix" data-explicit="1"' in html
    assert 'data-workspace-action="edit_contract"' in html
    assert "action:b.getAttribute('data-workspace-action')" in html
    assert "<script>alert" not in html


def test_workspace_markdown_preserves_sections_actions_and_form_state() -> None:
    intake_md = workspace_to_markdown(showcase_views()[0])
    skeleton = json.loads(intake_md.split("```json")[-1].split("```")[0])
    assert skeleton["action"] == "preview_fix"
    assert set(skeleton["answers"])
    preview_md = workspace_to_markdown(showcase_views()[1])
    assert "### Contract" in preview_md
    assert "`run_fix` — Run Fix" in preview_md
    assert "Execute the previewed contract" in preview_md


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
    )
    html = workspace_to_widget_html(view, instance_id="escape")
    assert "<img" not in html and "<b>unsafe" not in html and "<script></script>" not in html
    assert "&lt;script&gt;" in html
