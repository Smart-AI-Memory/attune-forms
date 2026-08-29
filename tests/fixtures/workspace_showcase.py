"""The generated all-construct command-workspace showcase fixture."""

from __future__ import annotations

from attune_forms import (
    WorkspaceAction,
    WorkspaceActionIntent,
    WorkspaceBlock,
    WorkspaceBlockKind,
    WorkspaceItem,
    WorkspaceSection,
    WorkspaceTone,
    WorkspaceView,
    WorkspaceViewId,
    form_from_dict,
)
from attune_forms.reference_form import REFERENCE_FORM


def showcase_views() -> tuple[WorkspaceView, ...]:
    """Return all four Fix views and every display-block kind."""
    intake = WorkspaceView(
        id=WorkspaceViewId.INTAKE,
        title="Fix",
        summary="Define the repair contract.",
        form=form_from_dict(REFERENCE_FORM),
        actions=(
            WorkspaceAction(
                id="preview_fix",
                label="Preview fix",
                intent=WorkspaceActionIntent.PRIMARY,
            ),
        ),
    )
    preview = WorkspaceView(
        id=WorkspaceViewId.PREVIEW,
        title="Review fix contract",
        sections=(
            WorkspaceSection(
                heading="Contract",
                tone=WorkspaceTone.ACTION,
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.KEY_VALUE,
                        items=(
                            WorkspaceItem("Outcome", "Tests pass after the rename"),
                            WorkspaceItem("Scope", "src/attune/forms.py"),
                        ),
                    ),
                    WorkspaceBlock(
                        WorkspaceBlockKind.CODE,
                        body="attune fix 'Tests pass' --scope src/attune/forms.py",
                        language="bash",
                    ),
                    WorkspaceBlock(
                        WorkspaceBlockKind.DISCLOSURE,
                        title="Advanced settings",
                        body="Provider: default; timeout: default",
                    ),
                ),
            ),
        ),
        actions=(
            WorkspaceAction(
                id="run_fix",
                label="Run Fix",
                intent=WorkspaceActionIntent.PRIMARY,
                consequence="Execute the previewed contract.",
                requires_explicit_choice=True,
            ),
            WorkspaceAction(id="edit_contract", label="Back to edit"),
        ),
    )
    execution = WorkspaceView(
        id=WorkspaceViewId.EXECUTION,
        title="Fix in progress",
        sections=(
            WorkspaceSection(
                heading="Progress",
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.TIMELINE,
                        items=(
                            WorkspaceItem("Diagnose", status="done"),
                            WorkspaceItem("Plan", status="done"),
                            WorkspaceItem("Edit", status="in flight"),
                            WorkspaceItem("Verify", status="waiting"),
                        ),
                    ),
                    WorkspaceBlock(
                        WorkspaceBlockKind.ACTION_LIST,
                        items=(WorkspaceItem("Inspect current log", detail="On demand"),),
                    ),
                ),
            ),
        ),
    )
    receipt = WorkspaceView(
        id=WorkspaceViewId.RECEIPT,
        title="Fix receipt",
        sections=(
            WorkspaceSection(
                heading="Changes",
                tone=WorkspaceTone.SUCCESS,
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.CHANGE_SUMMARY,
                        items=(WorkspaceItem("src/attune/forms.py", "+4 −2"),),
                    ),
                    WorkspaceBlock(
                        WorkspaceBlockKind.EVIDENCE,
                        items=(WorkspaceItem("pytest tests/test_forms.py", "0", status="passed"),),
                    ),
                ),
            ),
        ),
        actions=(WorkspaceAction(id="inspect_diff", label="Inspect attributed diff"),),
    )
    return intake, preview, execution, receipt
