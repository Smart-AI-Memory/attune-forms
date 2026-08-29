"""Validated command-workspace views built from the form grammar.

This is deliberately Fix-first: a view may carry the existing
``FormSchema`` plus a small closed set of display blocks and stable
actions. Blocks are data, never executable HTML or callbacks.
"""

from __future__ import annotations

import hmac
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from html import escape
from typing import Any

from attune_forms.bridge import FormValidationError, form_from_dict
from attune_forms.markdown_surface import form_to_markdown
from attune_forms.models import FormSchema
from attune_forms.theme import CSS_WORKSPACE
from attune_forms.widget import WIDGET_RESPONSE_MARKER, form_to_widget_html

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_LANG_RE = re.compile(r"^[A-Za-z0-9_+-]{1,32}$")
_WORKSPACE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ACTION_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_CONTRACT_HASH_RE = re.compile(r"^[0-9a-f]{64}$")

_WORKSPACE_KEYS = frozenset({"id", "title", "sections", "actions", "summary", "form"})
_SECTION_KEYS = frozenset({"blocks", "heading", "tone"})
_BLOCK_KEYS = frozenset({"kind", "title", "body", "items", "language"})
_ITEM_KEYS = frozenset({"label", "value", "detail", "status"})
_ACTION_KEYS = frozenset({"id", "label", "intent", "consequence", "requires_explicit_choice"})
_ACTION_RESPONSE_KEYS = frozenset(
    {
        WIDGET_RESPONSE_MARKER,
        "title",
        "workspace_id",
        "revision",
        "view",
        "action",
        "action_nonce",
        "contract_hash",
        "confirmed",
    }
)


class WorkspaceValidationError(ValueError):
    """A malformed workspace definition or action response.

    ``problems`` is deliberately compatible with
    :class:`~attune_forms.bridge.FormValidationError` so MCP callers can
    repair the exact invalid fields instead of handling a raw exception.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


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
class WorkspaceActionBinding:
    """Opaque host authority context copied into an action response.

    The renderer never interprets or grants this authority. The host
    supplies a binding for one rendered state revision and validates the
    returned values before dispatching the stable action id.
    """

    workspace_id: str
    revision: int
    action_nonce: str
    contract_hash: str

    def __post_init__(self) -> None:
        if not _WORKSPACE_ID_RE.fullmatch(self.workspace_id):
            raise ValueError("workspace id must be a 1-128 char stable identifier")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int):
            raise TypeError("workspace revision must be an integer")
        if self.revision < 0:
            raise ValueError("workspace revision must not be negative")
        if not _ACTION_NONCE_RE.fullmatch(self.action_nonce):
            raise ValueError("workspace action nonce must be a 16-128 char URL-safe token")
        if not _CONTRACT_HASH_RE.fullmatch(self.contract_hash):
            raise ValueError("workspace contract hash must be a lowercase SHA-256 digest")

    def to_payload(self) -> dict[str, str | int]:
        """Return the serializable response fields for this binding."""
        return {
            "workspace_id": self.workspace_id,
            "revision": self.revision,
            "action_nonce": self.action_nonce,
            "contract_hash": self.contract_hash,
        }


@dataclass(frozen=True)
class WorkspaceActionResponse:
    """One structurally validated action returned by a workspace view."""

    view: WorkspaceViewId
    action: str
    confirmed: bool
    workspace_id: str = ""
    revision: int | None = None
    action_nonce: str = ""
    contract_hash: str = ""


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


def _unknown_keys(where: str, raw: Mapping[str, Any], allowed: frozenset[str]) -> list[str]:
    return [f"{where} has unknown definition key {key!r}" for key in raw if key not in allowed]


def _string_value(
    where: str,
    raw: Mapping[str, Any],
    key: str,
    problems: list[str],
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str):
        problems.append(f"{where} '{key}' must be a string")
        return default
    if required and not value.strip():
        problems.append(f"{where} '{key}' is required and must not be empty")
    return value


def _enum_value(
    where: str,
    raw: Mapping[str, Any],
    key: str,
    enum_type: type[Enum],
    problems: list[str],
    *,
    default: str | None = None,
) -> Any:
    value = raw.get(key, default)
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        allowed = ", ".join(member.value for member in enum_type)
        problems.append(f"{where} '{key}' must be one of: {allowed}")
        return None


def _items_from_data(raw_items: Any, where: str, problems: list[str]) -> list[WorkspaceItem]:
    if not isinstance(raw_items, list):
        problems.append(f"{where} 'items' must be a list")
        return []
    items: list[WorkspaceItem] = []
    for index, raw_item in enumerate(raw_items):
        item_where = f"{where}.items[{index}]"
        if not isinstance(raw_item, Mapping):
            problems.append(f"{item_where} must be a mapping")
            continue
        item_problems = _unknown_keys(item_where, raw_item, _ITEM_KEYS)
        label = _string_value(item_where, raw_item, "label", item_problems, required=True)
        value = _string_value(item_where, raw_item, "value", item_problems)
        detail = _string_value(item_where, raw_item, "detail", item_problems)
        status = _string_value(item_where, raw_item, "status", item_problems)
        if not item_problems:
            items.append(WorkspaceItem(label, value, detail, status))
        problems.extend(item_problems)
    return items


def _blocks_from_data(raw_blocks: Any, where: str, problems: list[str]) -> list[WorkspaceBlock]:
    if not isinstance(raw_blocks, list):
        problems.append(f"{where} 'blocks' must be a list")
        return []
    blocks: list[WorkspaceBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        block_where = f"{where}.blocks[{index}]"
        if not isinstance(raw_block, Mapping):
            problems.append(f"{block_where} must be a mapping")
            continue
        block_problems = _unknown_keys(block_where, raw_block, _BLOCK_KEYS)
        kind = _enum_value(block_where, raw_block, "kind", WorkspaceBlockKind, block_problems)
        title = _string_value(block_where, raw_block, "title", block_problems)
        body = _string_value(block_where, raw_block, "body", block_problems)
        language = _string_value(block_where, raw_block, "language", block_problems, default="text")
        items = _items_from_data(raw_block.get("items", []), block_where, block_problems)
        if kind is not None and not block_problems:
            try:
                blocks.append(WorkspaceBlock(kind, title, body, tuple(items), language))
            except (TypeError, ValueError) as exc:
                block_problems.append(f"{block_where}: {exc}")
        problems.extend(block_problems)
    return blocks


def _sections_from_data(
    raw_sections: Any, where: str, problems: list[str]
) -> list[WorkspaceSection]:
    if not isinstance(raw_sections, list):
        problems.append(f"{where} 'sections' must be a list")
        return []
    sections: list[WorkspaceSection] = []
    for index, raw_section in enumerate(raw_sections):
        section_where = f"{where}.sections[{index}]"
        if not isinstance(raw_section, Mapping):
            problems.append(f"{section_where} must be a mapping")
            continue
        section_problems = _unknown_keys(section_where, raw_section, _SECTION_KEYS)
        heading = _string_value(section_where, raw_section, "heading", section_problems)
        tone = _enum_value(
            section_where,
            raw_section,
            "tone",
            WorkspaceTone,
            section_problems,
            default=WorkspaceTone.NEUTRAL.value,
        )
        blocks = _blocks_from_data(raw_section.get("blocks"), section_where, section_problems)
        if tone is not None and not section_problems:
            try:
                sections.append(WorkspaceSection(tuple(blocks), heading, tone))
            except (TypeError, ValueError) as exc:
                section_problems.append(f"{section_where}: {exc}")
        problems.extend(section_problems)
    return sections


def _actions_from_data(raw_actions: Any, where: str, problems: list[str]) -> list[WorkspaceAction]:
    if not isinstance(raw_actions, list):
        problems.append(f"{where} 'actions' must be a list")
        return []
    actions: list[WorkspaceAction] = []
    for index, raw_action in enumerate(raw_actions):
        action_where = f"{where}.actions[{index}]"
        if not isinstance(raw_action, Mapping):
            problems.append(f"{action_where} must be a mapping")
            continue
        action_problems = _unknown_keys(action_where, raw_action, _ACTION_KEYS)
        action_id = _string_value(action_where, raw_action, "id", action_problems, required=True)
        label = _string_value(action_where, raw_action, "label", action_problems, required=True)
        intent = _enum_value(
            action_where,
            raw_action,
            "intent",
            WorkspaceActionIntent,
            action_problems,
            default=WorkspaceActionIntent.SECONDARY.value,
        )
        consequence = _string_value(action_where, raw_action, "consequence", action_problems)
        explicit = raw_action.get("requires_explicit_choice", False)
        if not isinstance(explicit, bool):
            action_problems.append(f"{action_where} 'requires_explicit_choice' must be a boolean")
        if intent is not None and not action_problems:
            try:
                actions.append(WorkspaceAction(action_id, label, intent, consequence, explicit))
            except (TypeError, ValueError) as exc:
                action_problems.append(f"{action_where}: {exc}")
        problems.extend(action_problems)
    return actions


def workspace_from_dict(data: dict[str, Any]) -> WorkspaceView:
    """Build a strict :class:`WorkspaceView` from serializable data.

    Every definition key is consumed or rejected. This is the workspace
    twin of :func:`attune_forms.form_from_dict` and is the safe boundary
    for MCP/tool-authored view documents.
    """
    if not isinstance(data, dict):
        raise WorkspaceValidationError(["workspace must be a mapping"])

    where = "workspace"
    problems = _unknown_keys(where, data, _WORKSPACE_KEYS)
    view_id = _enum_value(where, data, "id", WorkspaceViewId, problems)
    title = _string_value(where, data, "title", problems, required=True)
    summary = _string_value(where, data, "summary", problems)
    sections = _sections_from_data(data.get("sections", []), where, problems)
    actions = _actions_from_data(data.get("actions", []), where, problems)

    form: FormSchema | None = None
    raw_form = data.get("form")
    if raw_form is not None:
        if not isinstance(raw_form, dict):
            problems.append("workspace 'form' must be a mapping")
        else:
            try:
                form = form_from_dict(raw_form, source="workspace")
            except FormValidationError as exc:
                problems.extend(f"workspace form: {problem}" for problem in exc.problems)

    if view_id is not None and not problems:
        try:
            return WorkspaceView(view_id, title, tuple(sections), tuple(actions), summary, form)
        except (TypeError, ValueError) as exc:
            problems.append(f"workspace: {exc}")
    raise WorkspaceValidationError(problems)


def collect_workspace_action(
    view: WorkspaceView,
    payload: Mapping[str, Any],
    binding: WorkspaceActionBinding | None = None,
) -> WorkspaceActionResponse:
    """Validate a returned action against its exact rendered view.

    This validates structure and an optional host-supplied binding. It
    does not authorize or execute the action; the host must still compare
    the binding with canonical state and consume the nonce once.
    """
    if not isinstance(payload, Mapping):
        raise WorkspaceValidationError(["workspace action response must be a mapping"])

    problems = [
        f"workspace action response has unknown key {key!r}"
        for key in payload
        if key not in _ACTION_RESPONSE_KEYS
    ]
    if payload.get(WIDGET_RESPONSE_MARKER) is not True:
        problems.append(f"workspace action response requires {WIDGET_RESPONSE_MARKER}=true")
    if payload.get("title") != view.title:
        problems.append("workspace action response title does not match the rendered view")
    if payload.get("view") != view.id.value:
        problems.append("workspace action response view does not match the rendered view")

    action_id = payload.get("action")
    action = next((candidate for candidate in view.actions if candidate.id == action_id), None)
    if not isinstance(action_id, str):
        problems.append("workspace action response 'action' must be a string")
    elif action is None:
        problems.append(f"workspace action {action_id!r} is not allowed by the rendered view")

    confirmed = payload.get("confirmed")
    if not isinstance(confirmed, bool):
        problems.append("workspace action response 'confirmed' must be a boolean")
    elif action is not None and action.requires_explicit_choice and not confirmed:
        problems.append(f"workspace action {action.id!r} requires explicit confirmation")

    binding_keys = ("workspace_id", "revision", "action_nonce", "contract_hash")
    if binding is None:
        unexpected = [key for key in binding_keys if key in payload]
        if unexpected:
            problems.append(
                "workspace action response supplied an unexpected binding: " + ", ".join(unexpected)
            )
    else:
        if payload.get("workspace_id") != binding.workspace_id:
            problems.append("workspace action response workspace id does not match")
        revision = payload.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            problems.append("workspace action response revision must be an integer")
        elif revision != binding.revision:
            problems.append("workspace action response revision does not match")
        nonce = payload.get("action_nonce")
        if not isinstance(nonce, str) or not hmac.compare_digest(nonce, binding.action_nonce):
            problems.append("workspace action response nonce does not match")
        contract_hash = payload.get("contract_hash")
        if not isinstance(contract_hash, str) or not hmac.compare_digest(
            contract_hash, binding.contract_hash
        ):
            problems.append("workspace action response contract hash does not match")

    if problems:
        raise WorkspaceValidationError(problems)
    return WorkspaceActionResponse(
        view=view.id,
        action=action_id,
        confirmed=confirmed,
        workspace_id=binding.workspace_id if binding else "",
        revision=binding.revision if binding else None,
        action_nonce=binding.action_nonce if binding else "",
        contract_hash=binding.contract_hash if binding else "",
    )


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


def workspace_to_widget_html(
    view: WorkspaceView,
    instance_id: str | None = None,
    *,
    binding: WorkspaceActionBinding | None = None,
) -> str:
    """Render one workspace view as self-contained widget HTML.

    ``binding`` is allowed only on display/action views. Intake answers
    continue through the existing form collector; consequential preview
    actions use this separate, state-bound response path.
    """
    if view.form is not None and binding is not None:
        raise ValueError("workspace action binding is not valid on a form view")
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
        binding_json = json.dumps(
            binding.to_payload() if binding else {},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        script = f"""<script>(function(){{
  var root=document.getElementById('{root_id}'); if(!root)return;
  root.addEventListener('click',function(e){{
    var b=e.target.closest?e.target.closest('[data-workspace-action]'):null;
    if(!b||!root.contains(b))return;
    var consequence=b.getAttribute('data-consequence');
    var explicit=b.getAttribute('data-explicit')==='1';
    if(explicit&&!window.confirm(consequence))return;
    var payload={{{json.dumps(WIDGET_RESPONSE_MARKER)}:true,
      title:root.getAttribute('data-workspace-title'),
      view:root.getAttribute('data-workspace-view'),
      action:b.getAttribute('data-workspace-action'),confirmed:explicit}};
    Object.assign(payload,{binding_json});
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


def workspace_to_markdown(
    view: WorkspaceView, *, binding: WorkspaceActionBinding | None = None
) -> str:
    """Render a workspace view to the portable markdown surface."""
    if view.form is not None and binding is not None:
        raise ValueError("workspace action binding is not valid on a form view")
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
                    "confirmed": False,
                    **(binding.to_payload() if binding else {}),
                },
                indent=2,
                ensure_ascii=False,
            ),
            "```",
        ]
    return "\n".join(lines)
