"""Validated command-workspace views built from the form grammar.

This is deliberately Fix-first: a view may carry the existing
``FormSchema`` plus a small closed set of display blocks and stable
actions. Blocks are data, never executable HTML or callbacks.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from html import escape

from attune_forms.markdown_surface import form_to_markdown
from attune_forms.models import FormSchema
from attune_forms.theme import CSS_WORKSPACE
from attune_forms.widget import WIDGET_RESPONSE_MARKER, form_to_widget_html

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_LANG_RE = re.compile(r"^[A-Za-z0-9_+-]{1,32}$")


class WorkspaceViewId(str, Enum):
    """The four portable Fix workspace views."""

    INTAKE = "intake"
    PREVIEW = "preview"
    EXECUTION = "execution"
    RECEIPT = "receipt"


class WorkspaceTone(str, Enum):
    """Semantic section tones shared with the design-token contract."""

    NEUTRAL = "neutral"
    ACTION = "action"
    RECOMMENDATION = "recommendation"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"


class WorkspaceBlockKind(str, Enum):
    """Closed Fix-proven display vocabulary."""

    KEY_VALUE = "key_value"
    CODE = "code"
    TIMELINE = "timeline"
    CHANGE_SUMMARY = "change_summary"
    EVIDENCE = "evidence"
    DISCLOSURE = "disclosure"
    ACTION_LIST = "action_list"


class WorkspaceActionIntent(str, Enum):
    """Visual/action hierarchy; execution authority stays with the host."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    DANGER = "danger"


@dataclass(frozen=True)
class WorkspaceItem:
    """One row in a structured display block."""

    label: str
    value: str = ""
    detail: str = ""
    status: str = ""

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("workspace item label must not be empty")


@dataclass(frozen=True)
class WorkspaceBlock:
    """A validated, non-executable display block."""

    kind: WorkspaceBlockKind
    title: str = ""
    body: str = ""
    items: tuple[WorkspaceItem, ...] = field(default_factory=tuple)
    language: str = "text"

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        if not isinstance(self.kind, WorkspaceBlockKind):
            raise TypeError("workspace block kind must be WorkspaceBlockKind")
        if self.kind is WorkspaceBlockKind.CODE and not self.body:
            raise ValueError("code block requires body")
        if self.kind is WorkspaceBlockKind.CODE and not _LANG_RE.fullmatch(self.language):
            raise ValueError("code block language must be a short language identifier")
        if self.kind is WorkspaceBlockKind.DISCLOSURE and not (self.title and self.body):
            raise ValueError("disclosure block requires title and body")
        item_kinds = {
            WorkspaceBlockKind.KEY_VALUE,
            WorkspaceBlockKind.TIMELINE,
            WorkspaceBlockKind.CHANGE_SUMMARY,
            WorkspaceBlockKind.EVIDENCE,
            WorkspaceBlockKind.ACTION_LIST,
        }
        if self.kind in item_kinds and not self.items:
            raise ValueError(f"{self.kind.value} block requires items")


@dataclass(frozen=True)
class WorkspaceSection:
    """An ordered group of display blocks."""

    blocks: tuple[WorkspaceBlock, ...]
    heading: str = ""
    tone: WorkspaceTone = WorkspaceTone.NEUTRAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocks", tuple(self.blocks))
        if not isinstance(self.tone, WorkspaceTone):
            raise TypeError("workspace section tone must be WorkspaceTone")
        if not self.blocks:
            raise ValueError("workspace section requires at least one block")


@dataclass(frozen=True)
class WorkspaceAction:
    """A stable host-dispatched action; never an executable callback."""

    id: str
    label: str
    intent: WorkspaceActionIntent = WorkspaceActionIntent.SECONDARY
    consequence: str = ""
    requires_explicit_choice: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.intent, WorkspaceActionIntent):
            raise TypeError("workspace action intent must be WorkspaceActionIntent")
        if not _ID_RE.fullmatch(self.id):
            raise ValueError("workspace action id must match [a-z][a-z0-9_-]{0,63}")
        if not self.label.strip():
            raise ValueError("workspace action label must not be empty")
        if self.requires_explicit_choice and not self.consequence.strip():
            raise ValueError("explicit workspace action requires a consequence")


@dataclass(frozen=True)
class WorkspaceView:
    """One portable state view of a command workspace."""

    id: WorkspaceViewId
    title: str
    sections: tuple[WorkspaceSection, ...] = field(default_factory=tuple)
    actions: tuple[WorkspaceAction, ...] = field(default_factory=tuple)
    summary: str = ""
    form: FormSchema | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sections", tuple(self.sections))
        object.__setattr__(self, "actions", tuple(self.actions))
        if not isinstance(self.id, WorkspaceViewId):
            raise TypeError("workspace view id must be WorkspaceViewId")
        if not self.title.strip():
            raise ValueError("workspace title must not be empty")
        ids = [action.id for action in self.actions]
        if len(ids) != len(set(ids)):
            raise ValueError("workspace action ids must be unique")
        primary = [a for a in self.actions if a.intent is WorkspaceActionIntent.PRIMARY]
        if len(primary) > 1:
            raise ValueError("workspace view permits at most one primary action")
        if self.form is not None and len(self.actions) != 1:
            raise ValueError("a form workspace view requires exactly one submit action")


def _item_text(item: WorkspaceItem) -> str:
    suffix = f" — {escape(item.detail)}" if item.detail else ""
    status = f'<span class="ae-ws-status">{escape(item.status)}</span> ' if item.status else ""
    value = f": {escape(item.value)}" if item.value else ""
    return f"{status}<strong>{escape(item.label)}</strong>{value}{suffix}"


def _block_html(block: WorkspaceBlock) -> str:
    if block.kind is WorkspaceBlockKind.KEY_VALUE:
        rows = "".join(
            f"<dt>{escape(item.label)}</dt><dd>{escape(item.value or item.detail)}</dd>"
            for item in block.items
        )
        return f'<dl class="ae-ws-block ae-ws-kv">{rows}</dl>'
    if block.kind is WorkspaceBlockKind.CODE:
        return (
            '<pre class="ae-ws-block ae-ws-code">'
            f'<code class="language-{escape(block.language)}">{escape(block.body)}</code></pre>'
        )
    if block.kind is WorkspaceBlockKind.EVIDENCE:
        rows = "".join(
            f'<tr><th scope="row">{escape(item.label)}</th><td>{escape(item.value)}</td>'
            f"<td>{escape(item.status or item.detail)}</td></tr>"
            for item in block.items
        )
        return (
            '<table class="ae-ws-block ae-ws-evidence"><thead><tr>'
            '<th scope="col">Evidence</th><th scope="col">Result</th>'
            f'<th scope="col">Status</th></tr></thead><tbody>{rows}</tbody></table>'
        )
    if block.kind is WorkspaceBlockKind.DISCLOSURE:
        return (
            '<details class="ae-ws-block ae-ws-disclosure">'
            f"<summary>{escape(block.title)}</summary><p>{escape(block.body)}</p></details>"
        )
    tag = "ol" if block.kind is WorkspaceBlockKind.TIMELINE else "ul"
    rows = "".join(f"<li>{_item_text(item)}</li>" for item in block.items)
    return f'<{tag} class="ae-ws-block ae-ws-list ae-ws-{block.kind.value}">{rows}</{tag}>'


def _sections_html(sections: tuple[WorkspaceSection, ...]) -> str:
    rendered = []
    for section in sections:
        heading = f"<h3>{escape(section.heading)}</h3>" if section.heading else ""
        blocks = "".join(_block_html(block) for block in section.blocks)
        rendered.append(
            f'<section class="ae-ws-section" data-tone="{section.tone.value}">'
            f"{heading}{blocks}</section>"
        )
    return "".join(rendered)


def workspace_to_widget_html(view: WorkspaceView, instance_id: str | None = None) -> str:
    """Render one workspace view as self-contained widget HTML."""
    suffix = re.sub(r"[^A-Za-z0-9]+", "-", instance_id or "").strip("-")
    suffix = suffix or uuid.uuid4().hex[:8]
    root_id = f"attune-workspace-{suffix}"
    css = CSS_WORKSPACE.replace("#attune-workspace", f"#{root_id}")
    summary = f'<p class="ae-ws-summary">{escape(view.summary)}</p>' if view.summary else ""
    head = f'<header class="ae-ws-head"><h2 class="ae-ws-title">{escape(view.title)}</h2>{summary}</header>'
    sections = _sections_html(view.sections)
    if view.form is not None:
        action = view.actions[0]
        content = form_to_widget_html(
            view.form,
            instance_id=f"{suffix}form",
            submit_label=action.label,
            submit_action=action.id,
            submit_view=view.id.value,
            submit_title=view.title,
            include_title=False,
            submit_consequence=action.consequence,
            requires_explicit_choice=action.requires_explicit_choice,
        )
        actions = ""
    else:

        def action_button(action: WorkspaceAction) -> str:
            explicit = ' data-explicit="1"' if action.requires_explicit_choice else ""
            consequence = (
                f' data-consequence="{escape(action.consequence)}"' if action.consequence else ""
            )
            note = (
                f'<span class="ae-ws-consequence">{escape(action.consequence)}</span>'
                if action.requires_explicit_choice
                else ""
            )
            return (
                '<span class="ae-ws-action-group">'
                f'<button type="button" class="ae-ws-action '
                f'ae-ws-action-{action.intent.value}" '
                f'data-workspace-action="{escape(action.id)}"{explicit}{consequence}>'
                f"{escape(action.label)}</button>{note}</span>"
            )

        buttons = "".join(action_button(action) for action in view.actions)
        actions = (
            f'<div class="ae-ws-actions">{buttons}</div>'
            '<p class="ae-ws-dispatch" role="status" aria-live="polite"></p>'
            if buttons
            else ""
        )
        content = ""
    script = ""
    if view.form is None and view.actions:
        script = f"""<script>(function(){{
  var root=document.getElementById('{root_id}'); if(!root)return;
  root.addEventListener('click',function(e){{
    var b=e.target.closest?e.target.closest('[data-workspace-action]'):null;
    if(!b||!root.contains(b))return;
    var consequence=b.getAttribute('data-consequence');
    if(b.getAttribute('data-explicit')==='1'&&!window.confirm(consequence))return;
    var payload={{{json.dumps(WIDGET_RESPONSE_MARKER)}:true,
      title:root.getAttribute('data-workspace-title'),
      view:root.getAttribute('data-workspace-view'),
      action:b.getAttribute('data-workspace-action')}};
    if(typeof sendPrompt==='function'){{
      sendPrompt('Workspace action submitted — parse this response:\\n```json\\n'
        +JSON.stringify(payload)+'\\n```');
      root.querySelectorAll('[data-workspace-action]').forEach(function(x){{x.disabled=true;}});
      var status=root.querySelector('.ae-ws-dispatch');
      if(status)status.textContent='Action submitted.';
    }}
  }});
}})();</script>"""
    return (
        f'<div id="{root_id}" data-workspace-view="{view.id.value}" '
        f'data-workspace-title="{escape(view.title)}"><style>{css}</style>'
        f"{head}{sections}{content}{actions}{script}</div>"
    )


def _markdown_text(value: str) -> str:
    """Keep author text inside its current Markdown structural slot."""
    escaped = value.replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "<", ">", "|", "#"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped.replace("\n", "<br>")


def _block_markdown(block: WorkspaceBlock) -> list[str]:
    if block.kind is WorkspaceBlockKind.KEY_VALUE:
        return [
            f"- **{_markdown_text(item.label)}:** " f"{_markdown_text(item.value or item.detail)}"
            for item in block.items
        ]
    if block.kind is WorkspaceBlockKind.CODE:
        return [f"```{block.language}", block.body.replace("```", "` ` `"), "```"]
    if block.kind is WorkspaceBlockKind.EVIDENCE:

        def cell(value: str) -> str:
            return _markdown_text(value)

        rows = ["| Evidence | Result | Status |", "| --- | --- | --- |"]
        rows.extend(
            f"| {cell(item.label)} | {cell(item.value)} | " f"{cell(item.status or item.detail)} |"
            for item in block.items
        )
        return rows
    if block.kind is WorkspaceBlockKind.DISCLOSURE:
        return [f"**{_markdown_text(block.title)}**", "", _markdown_text(block.body)]
    return [
        f"- {f'[{_markdown_text(item.status)}] ' if item.status else ''}"
        f"**{_markdown_text(item.label)}**"
        f"{f': {_markdown_text(item.value)}' if item.value else ''}"
        f"{f' — {_markdown_text(item.detail)}' if item.detail else ''}"
        for item in block.items
    ]


def workspace_to_markdown(view: WorkspaceView) -> str:
    """Render a workspace view to the portable markdown surface."""
    lines = [f"## {_markdown_text(view.title)}"]
    if view.summary:
        lines += ["", _markdown_text(view.summary)]
    for section in view.sections:
        if section.heading:
            lines += ["", f"### {_markdown_text(section.heading)}"]
        for block in section.blocks:
            lines += ["", *_block_markdown(block)]
    if view.form is not None:
        action = view.actions[0]
        if action.requires_explicit_choice:
            lines += [
                "",
                f"**Explicit confirmation required:** {_markdown_text(action.consequence)}",
            ]
        lines += [
            "",
            form_to_markdown(
                view.form,
                action=action.id,
                submit_label=action.label,
                include_title=False,
                view=view.id.value,
            ),
        ]
    elif view.actions:
        lines += ["", "### Actions"]
        lines.extend(
            f"- `{action.id}` — {_markdown_text(action.label)}"
            f"{f' — {_markdown_text(action.consequence)}' if action.consequence else ''}"
            for action in view.actions
        )
        lines += [
            "",
            "Reply with the selected `action` value in this payload:",
            "",
            "```json",
            json.dumps(
                {
                    WIDGET_RESPONSE_MARKER: True,
                    "title": view.title,
                    "view": view.id.value,
                    "action": None,
                },
                indent=2,
                ensure_ascii=False,
            ),
            "```",
        ]
    return "\n".join(lines)
