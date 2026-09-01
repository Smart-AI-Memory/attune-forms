"""Capability-based interaction conformance for forms and workspaces.

The harness evaluates observable projection properties.  Profiles never enter
workspace authority, and a conformance report never authorizes an action.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from html.parser import HTMLParser
from typing import Any

from attune_forms.workspace import (
    WorkspaceView,
    workspace_to_markdown,
    workspace_to_widget_html,
)

logger = logging.getLogger(__name__)


class ConformanceReceipt(str, Enum):
    """Deterministic receipt classes produced by the harness."""

    DOM = "dom"
    KEYBOARD = "keyboard"
    VIEWPORT = "viewport"
    PARITY = "parity"
    RETENTION = "retention"
    LATENCY = "latency"


class ConformanceStatus(str, Enum):
    """Overall result without treating unavailability as passing."""

    PASSING = "passing"
    FAILING = "failing"
    UNAVAILABLE = "unavailable"


class ProjectionSurface(str, Enum):
    """Projection surfaces whose action sets can be compared."""

    RICH = "rich"
    PORTABLE = "portable"
    HEADLESS = "headless"


class LatencyMode(str, Enum):
    """Cold and warm measurement cohorts remain distinct."""

    COLD = "cold"
    WARM = "warm"


class LatencyPhase(str, Enum):
    """System-owned interaction phases, kept separate for attribution."""

    SCHEMA_READY = "schema_ready"
    FIRST_ACTIONABLE_RENDER = "first_actionable_render"
    ACTION_ACKNOWLEDGED = "action_acknowledged"
    FIRST_PROGRESS = "first_progress"
    PROGRESS_FRESHNESS = "progress_freshness"
    TERMINAL_RECEIPT = "terminal_receipt"


@dataclass(frozen=True)
class HostCapabilities:
    """Observable rendering and return-path capabilities."""

    rich_markup: bool = False
    forms: bool = False
    multi_select: bool = False
    live_updates: bool = False
    postback: bool = False


@dataclass(frozen=True)
class NavigationCapabilities:
    """Observable navigation affordances for one host profile."""

    keyboard: bool = False
    pointer: bool = False
    scroll: bool = False
    pagination: bool = False


@dataclass(frozen=True)
class RetentionCapabilities:
    """Whether a host retains output and supports submitted compaction."""

    prior_output_retained: bool = False
    submitted_view_collapsible: bool = False


@dataclass(frozen=True)
class ViewportClass:
    """A measured host fixture or a deterministic control-capacity fixture."""

    id: str
    width_px: int | None = None
    height_px: int | None = None
    max_actions_per_view: int | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("viewport id must not be empty")
        for name in ("width_px", "height_px", "max_actions_per_view"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"viewport {name} must be a positive integer or None")


@dataclass(frozen=True)
class LatencyBudget:
    """Ratified cold/warm p95 budgets in milliseconds."""

    phase: LatencyPhase
    cold_p95_ms: float | None = None
    warm_p95_ms: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.phase, LatencyPhase):
            raise TypeError("latency budget phase must be LatencyPhase")
        if self.cold_p95_ms is None and self.warm_p95_ms is None:
            raise ValueError("latency budget requires a cold or warm p95 value")
        for name in ("cold_p95_ms", "warm_p95_ms"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise TypeError(f"latency {name} must be numeric or None")
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"latency {name} must be finite and positive")


@dataclass(frozen=True)
class UnavailableReceipt:
    """An explicit unavailable result; it never enters passed receipts."""

    receipt: ConformanceReceipt
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, ConformanceReceipt):
            raise TypeError("unavailable receipt must name ConformanceReceipt")
        if not self.reason.strip():
            raise ValueError("unavailable receipt requires a reason")


@dataclass(frozen=True)
class InteractionProfile:
    """Capability-only conformance input with no command authority fields."""

    id: str
    capabilities: HostCapabilities
    navigation: NavigationCapabilities
    retention: RetentionCapabilities
    viewport: ViewportClass | None
    required_receipts: tuple[ConformanceReceipt, ...]
    projection_surfaces: tuple[ProjectionSurface, ...]
    required_latency_phases: tuple[LatencyPhase, ...]
    latency_budgets: tuple[LatencyBudget, ...] = field(default_factory=tuple)
    unavailable_receipts: tuple[UnavailableReceipt, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for name in (
            "required_receipts",
            "projection_surfaces",
            "required_latency_phases",
            "latency_budgets",
            "unavailable_receipts",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not self.id.strip():
            raise ValueError("interaction profile id must not be empty")
        if not isinstance(self.capabilities, HostCapabilities):
            raise TypeError("profile capabilities must be HostCapabilities")
        if not isinstance(self.navigation, NavigationCapabilities):
            raise TypeError("profile navigation must be NavigationCapabilities")
        if not isinstance(self.retention, RetentionCapabilities):
            raise TypeError("profile retention must be RetentionCapabilities")
        if self.viewport is not None and not isinstance(self.viewport, ViewportClass):
            raise TypeError("profile viewport must be ViewportClass or None")
        _require_instances("required receipts", self.required_receipts, ConformanceReceipt)
        _require_instances("projection surfaces", self.projection_surfaces, ProjectionSurface)
        _require_instances("required latency phases", self.required_latency_phases, LatencyPhase)
        _require_instances("latency budgets", self.latency_budgets, LatencyBudget)
        _require_instances("unavailable receipts", self.unavailable_receipts, UnavailableReceipt)
        if not self.required_receipts:
            raise ValueError("interaction profile requires at least one receipt")
        _require_unique("required receipts", self.required_receipts)
        _require_unique("projection surfaces", self.projection_surfaces)
        _require_unique("required latency phases", self.required_latency_phases)
        _require_unique("latency budget phases", tuple(item.phase for item in self.latency_budgets))
        unavailable = tuple(item.receipt for item in self.unavailable_receipts)
        _require_unique("unavailable receipts", unavailable)
        if not set(unavailable).issubset(self.required_receipts):
            raise ValueError("unavailable receipts must also be required receipts")
        budget_phases = {item.phase for item in self.latency_budgets}
        if not budget_phases.issubset(self.required_latency_phases):
            raise ValueError("latency budgets must name required latency phases")
        rich_surface = ProjectionSurface.RICH in self.projection_surfaces
        if self.capabilities.rich_markup != rich_surface:
            raise ValueError("rich projection surface must match rich_markup capability")
        if self.capabilities.multi_select and not self.capabilities.forms:
            raise ValueError("multi-select capability requires forms capability")
        rich_receipts = {ConformanceReceipt.DOM, ConformanceReceipt.KEYBOARD}
        if rich_receipts.intersection(self.required_receipts) and not rich_surface:
            raise ValueError("DOM and keyboard receipts require a rich projection")
        if ConformanceReceipt.KEYBOARD in self.required_receipts and not self.navigation.keyboard:
            raise ValueError("keyboard receipt requires keyboard navigation capability")
        if ConformanceReceipt.VIEWPORT in self.required_receipts and self.viewport is None:
            raise ValueError("viewport receipt requires a viewport fixture")
        if ConformanceReceipt.RETENTION in self.required_receipts and not (
            self.retention.prior_output_retained or self.retention.submitted_view_collapsible
        ):
            raise ValueError("retention receipt requires a retention capability")
        latency_required = ConformanceReceipt.LATENCY in self.required_receipts
        if latency_required:
            if not self.required_latency_phases:
                raise ValueError("latency receipt requires attributed phases")
            if (
                self.capabilities.forms
                and LatencyPhase.SCHEMA_READY not in self.required_latency_phases
            ):
                raise ValueError("forms capability requires the schema-ready phase")
            live_phases = {
                LatencyPhase.FIRST_PROGRESS,
                LatencyPhase.PROGRESS_FRESHNESS,
            }
            if self.capabilities.live_updates and not live_phases.issubset(
                self.required_latency_phases
            ):
                raise ValueError("live-update phases are required when live updates are supported")
            if (
                self.capabilities.postback
                and LatencyPhase.ACTION_ACKNOWLEDGED not in self.required_latency_phases
            ):
                raise ValueError("postback capability requires the acknowledgement phase")
        elif self.required_latency_phases or self.latency_budgets:
            raise ValueError("latency phases and budgets require the latency receipt")


@dataclass(frozen=True)
class WorkspaceFixture:
    """Domain-neutral workspace pages and the action ids they must expose."""

    owner: str
    pages: tuple[WorkspaceView, ...]
    expected_action_ids: tuple[str, ...]
    submitted_summary: str = ""
    interaction_rounds: int = 1
    observed_user_dwell_ms: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "pages", tuple(self.pages))
        object.__setattr__(self, "expected_action_ids", tuple(self.expected_action_ids))
        if not self.owner.strip():
            raise ValueError("workspace fixture owner must not be empty")
        if not self.pages:
            raise ValueError("workspace fixture requires at least one page")
        _require_unique("expected action ids", self.expected_action_ids)
        if isinstance(self.interaction_rounds, bool) or not isinstance(
            self.interaction_rounds, int
        ):
            raise TypeError("interaction_rounds must be an integer")
        if self.interaction_rounds < 0:
            raise ValueError("interaction_rounds must not be negative")
        dwell = self.observed_user_dwell_ms
        if dwell is not None and (
            isinstance(dwell, bool)
            or not isinstance(dwell, int | float)
            or not math.isfinite(float(dwell))
            or dwell < 0
        ):
            raise ValueError("observed_user_dwell_ms must be finite and non-negative")


def _default_rich(view: WorkspaceView) -> str:
    return workspace_to_widget_html(view, instance_id="conformance")


def _default_headless(view: WorkspaceView) -> tuple[str, ...]:
    return tuple(action.id for action in view.actions)


@dataclass(frozen=True)
class ProjectionRenderers:
    """Injectable projection functions used by deterministic host fixtures."""

    rich: Callable[[WorkspaceView], str] = _default_rich
    portable: Callable[[WorkspaceView], str] = workspace_to_markdown
    headless: Callable[[WorkspaceView], Iterable[str]] = _default_headless
    retained: Callable[[WorkspaceFixture], str] | None = None


@dataclass(frozen=True)
class LatencySample:
    """One raw phase measurement retained for reproducibility."""

    phase: LatencyPhase
    mode: LatencyMode
    duration_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.phase, LatencyPhase):
            raise TypeError("latency sample phase must be LatencyPhase")
        if not isinstance(self.mode, LatencyMode):
            raise TypeError("latency sample mode must be LatencyMode")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int | float):
            raise TypeError("latency duration must be numeric")
        if not math.isfinite(float(self.duration_ms)) or self.duration_ms < 0:
            raise ValueError("latency duration must be finite and non-negative")


@dataclass(frozen=True)
class Percentiles:
    """Nearest-rank p50, p95, and p99 for one cohort."""

    p50: float
    p95: float
    p99: float
    n: int


@dataclass(frozen=True)
class PhaseLatency:
    """Cold and warm aggregates for one attributed interaction phase."""

    phase: LatencyPhase
    cold: Percentiles | None
    warm: Percentiles | None


@dataclass(frozen=True)
class ConformanceFinding:
    """One owner-scoped failure with structural evidence."""

    owner: str
    profile_id: str
    receipt: ConformanceReceipt
    property: str
    evidence: str
    viewport_id: str = ""
    control_id: str = ""
    page_index: int | None = None


@dataclass(frozen=True)
class ConformanceReport:
    """Structured conformance result; unavailable receipts never pass."""

    profile_id: str
    owner: str
    status: ConformanceStatus
    passed_receipts: tuple[ConformanceReceipt, ...]
    unavailable_receipts: tuple[UnavailableReceipt, ...]
    findings: tuple[ConformanceFinding, ...]
    latency: tuple[PhaseLatency, ...]
    latency_samples: tuple[LatencySample, ...]
    interaction_rounds: int
    observed_user_dwell_ms: float | None
    submitted_summary: str

    @property
    def passed(self) -> bool:
        """True only for a complete deterministic pass."""
        return self.status is ConformanceStatus.PASSING


@dataclass(frozen=True)
class _DomControl:
    tag: str
    action_id: str
    label: str
    disabled: bool
    tabindex: str | None


_VOID_ELEMENTS = frozenset(
    {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
)


class _WorkspaceDomParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = False
        self.live_status = False
        self.controls: list[_DomControl] = []
        self.styles: list[str] = []
        self._control: dict[str, Any] | None = None
        self._control_depth = 0
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attributes = dict(attrs)
        if "data-workspace-view" in attributes:
            self.root = True
        if attributes.get("role") == "status" and attributes.get("aria-live"):
            self.live_status = True
        if tag == "style":
            self._in_style = True
        action_id = attributes.get("data-workspace-action")
        if action_id is not None:
            self._control = {
                "tag": tag,
                "action_id": action_id,
                "label": [],
                "disabled": "disabled" in attributes,
                "tabindex": attributes.get("tabindex"),
            }
            self._control_depth = 1
            if tag in _VOID_ELEMENTS:
                self._finish_control()
        elif self._control is not None and tag not in _VOID_ELEMENTS:
            self._control_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False
        if self._control is None:
            return
        if tag.lower() in _VOID_ELEMENTS:
            return
        self._control_depth -= 1
        if self._control_depth == 0:
            self._finish_control()

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)
        if self._control is not None:
            self._control["label"].append(data)

    def _finish_control(self) -> None:
        if self._control is None:
            return
        self.controls.append(
            _DomControl(
                tag=self._control["tag"],
                action_id=self._control["action_id"],
                label=" ".join("".join(self._control["label"]).split()),
                disabled=self._control["disabled"],
                tabindex=self._control["tabindex"],
            )
        )
        self._control = None
        self._control_depth = 0


class _VisibleTextParser(HTMLParser):
    """Extract user-visible text while excluding non-rendered containers."""

    _HIDDEN = frozenset({"head", "noscript", "script", "style", "template"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() in self._HIDDEN:
            self._hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._HIDDEN and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._hidden_depth:
            self.parts.append(data)

    def normalized(self) -> str:
        """Return whitespace-normalized visible text."""
        return " ".join("".join(self.parts).split())


@dataclass
class _PageEvidence:
    model: tuple[str, ...]
    rich: tuple[str, ...] | None = None
    portable: tuple[str, ...] | None = None
    headless: tuple[str, ...] | None = None
    dom: _WorkspaceDomParser | None = None


_PORTABLE_ACTION_RE = re.compile(r"^- `([a-z][a-z0-9_-]{0,63})` — ", re.MULTILINE)
_ACTION_HEADING_RE = re.compile(r"^### Actions\s*$", re.MULTILINE)
_REPLY_HEADING_RE = re.compile(
    r"^Reply with the selected `action` value in this payload:\s*$",
    re.MULTILINE,
)
_JSON_FENCE_RE = re.compile(r"```json\s*\n(?P<payload>.*?)\n```", re.DOTALL)
_CSS_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_CSS_RULE_RE = re.compile(r"(?P<selectors>[^{}]+)\{(?P<body>[^{}]*)\}")
_VISIBLE_FOCUS_PROPERTIES = frozenset({"outline", "box-shadow"})


def _require_unique(label: str, values: tuple[Any, ...]) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_instances(label: str, values: tuple[Any, ...], expected: type[Any]) -> None:
    if not all(isinstance(value, expected) for value in values):
        raise TypeError(f"{label} must contain only {expected.__name__} values")


def _percentiles(values: list[float]) -> Percentiles | None:
    if not values:
        return None
    ordered = sorted(values)

    def rank(quantile: float) -> float:
        index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
        return float(ordered[index])

    return Percentiles(rank(0.50), rank(0.95), rank(0.99), len(ordered))


def summarize_latency(samples: Iterable[LatencySample]) -> tuple[PhaseLatency, ...]:
    """Aggregate raw phase samples into cold/warm p50, p95, and p99."""
    grouped: dict[tuple[LatencyPhase, LatencyMode], list[float]] = defaultdict(list)
    for sample in samples:
        if not isinstance(sample, LatencySample):
            raise TypeError("latency samples must contain LatencySample values")
        grouped[(sample.phase, sample.mode)].append(float(sample.duration_ms))
    return tuple(
        PhaseLatency(
            phase=phase,
            cold=_percentiles(grouped[(phase, LatencyMode.COLD)]),
            warm=_percentiles(grouped[(phase, LatencyMode.WARM)]),
        )
        for phase in LatencyPhase
        if any((phase, mode) in grouped for mode in LatencyMode)
    )


def measure_latency(
    operation: Callable[[], Any],
    *,
    phase: LatencyPhase,
    mode: LatencyMode,
    sample_count: int = 30,
    warmup_count: int = 0,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> tuple[LatencySample, ...]:
    """Measure one attributed operation and retain every raw sample."""
    if not isinstance(phase, LatencyPhase):
        raise TypeError("phase must be LatencyPhase")
    if not isinstance(mode, LatencyMode):
        raise TypeError("mode must be LatencyMode")
    for name, value, allow_zero in (
        ("sample_count", sample_count, False),
        ("warmup_count", warmup_count, True),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < (0 if allow_zero else 1):
            qualifier = "non-negative" if allow_zero else "positive"
            raise ValueError(f"{name} must be {qualifier}")
    for _ in range(warmup_count):
        operation()
    measured = []
    for _ in range(sample_count):
        started = clock_ns()
        operation()
        ended = clock_ns()
        if ended < started:
            raise ValueError("latency clock moved backwards")
        measured.append(LatencySample(phase, mode, (ended - started) / 1_000_000))
    return tuple(measured)


def _finding(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    receipt: ConformanceReceipt,
    property_name: str,
    evidence: str,
    *,
    page_index: int | None = None,
    control_id: str = "",
) -> ConformanceFinding:
    return ConformanceFinding(
        owner=fixture.owner,
        profile_id=profile.id,
        receipt=receipt,
        property=property_name,
        evidence=evidence,
        viewport_id=profile.viewport.id if profile.viewport else "",
        control_id=control_id,
        page_index=page_index,
    )


def _portable_ids(markdown: str) -> tuple[str, ...]:
    action_headings = tuple(_ACTION_HEADING_RE.finditer(markdown))
    if not action_headings:
        raise ValueError("portable projection has no bounded Actions section")
    action_start = action_headings[-1].end()
    reply_heading = _REPLY_HEADING_RE.search(markdown, action_start)
    if reply_heading is None:
        raise ValueError("portable projection has no JSON response contract")
    action_section = markdown[action_start : reply_heading.start()]
    ids = tuple(_PORTABLE_ACTION_RE.findall(action_section))
    response = _JSON_FENCE_RE.search(markdown, reply_heading.end())
    if response is None:
        raise ValueError("portable projection has no JSON response contract")
    payload = json.loads(response.group("payload"))
    if not isinstance(payload, Mapping) or payload.get("__elicitation_response__") is not True:
        raise ValueError("portable projection has no validated response sentinel")
    return ids


def _projection_failure_receipt(
    profile: InteractionProfile,
    surface: ProjectionSurface,
    unavailable: set[ConformanceReceipt],
) -> ConformanceReceipt | None:
    candidates = [ConformanceReceipt.PARITY]
    if surface is ProjectionSurface.RICH:
        candidates = [
            ConformanceReceipt.DOM,
            ConformanceReceipt.KEYBOARD,
            ConformanceReceipt.PARITY,
        ]
    return next(
        (
            receipt
            for receipt in candidates
            if receipt in profile.required_receipts and receipt not in unavailable
        ),
        None,
    )


def _projection_evidence(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    renderers: ProjectionRenderers,
    findings: list[ConformanceFinding],
    unavailable: set[ConformanceReceipt],
) -> list[_PageEvidence]:
    pages: list[_PageEvidence] = []
    for index, view in enumerate(fixture.pages):
        evidence = _PageEvidence(model=tuple(action.id for action in view.actions))
        for surface in profile.projection_surfaces:
            failure_receipt = _projection_failure_receipt(profile, surface, unavailable)
            if failure_receipt is None:
                continue
            try:
                if surface is ProjectionSurface.RICH:
                    rendered = renderers.rich(view)
                    if not isinstance(rendered, str):
                        raise TypeError("rich renderer must return str")
                    parser = _WorkspaceDomParser()
                    parser.feed(rendered)
                    parser.close()
                    evidence.dom = parser
                    evidence.rich = tuple(control.action_id for control in parser.controls)
                elif surface is ProjectionSurface.PORTABLE:
                    rendered = renderers.portable(view)
                    if not isinstance(rendered, str):
                        raise TypeError("portable renderer must return str")
                    evidence.portable = _portable_ids(rendered)
                else:
                    evidence.headless = tuple(str(item) for item in renderers.headless(view))
            except Exception as exc:  # noqa: BLE001 - renderer plug-in boundary
                logger.warning(
                    "conformance %s projection failed with %s: %s",
                    surface.value,
                    type(exc).__name__,
                    exc,
                )
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        failure_receipt,
                        "projection.return_path",
                        f"page {index + 1} {surface.value} projection failed with "
                        f"{type(exc).__name__}: {exc}",
                        page_index=index,
                    )
                )
        pages.append(evidence)
    return pages


def _check_dom(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    pages: list[_PageEvidence],
    findings: list[ConformanceFinding],
) -> None:
    for index, page in enumerate(pages):
        dom = page.dom
        if dom is None:
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.DOM,
                    "dom.workspace_structure",
                    f"page {index + 1} has no parsed rich DOM",
                    page_index=index,
                )
            )
            continue
        if not dom.root:
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.DOM,
                    "dom.workspace_structure",
                    f"page {index + 1} has no workspace root attributes",
                    page_index=index,
                )
            )
        if page.model and not dom.live_status:
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.DOM,
                    "dom.action_acknowledgement",
                    f"page {index + 1} has no aria-live status region",
                    page_index=index,
                )
            )
        for control in dom.controls:
            if not control.label:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.DOM,
                        "dom.programmatic_name",
                        f"action {control.action_id!r} has no text name",
                        page_index=index,
                        control_id=control.action_id,
                    )
                )


def _check_keyboard(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    pages: list[_PageEvidence],
    findings: list[ConformanceFinding],
) -> None:
    for index, page in enumerate(pages):
        dom = page.dom
        if dom is None:
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.KEYBOARD,
                    "keyboard.traversal",
                    f"page {index + 1} has no parsed rich controls",
                    page_index=index,
                )
            )
            continue
        if tuple(control.action_id for control in dom.controls) != page.model:
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.KEYBOARD,
                    "keyboard.tab_order",
                    f"page {index + 1} control order differs from the declared action order",
                    page_index=index,
                )
            )
        for control in dom.controls:
            if control.tag != "button":
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.KEYBOARD,
                        "keyboard.native_control",
                        f"action {control.action_id!r} is not a native button",
                        page_index=index,
                        control_id=control.action_id,
                    )
                )
            if control.disabled:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.KEYBOARD,
                        "keyboard.reachability",
                        f"action {control.action_id!r} is removed from keyboard traversal",
                        page_index=index,
                        control_id=control.action_id,
                    )
                )
            if control.tabindex not in (None, "0"):
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.KEYBOARD,
                        "keyboard.tab_order",
                        f"action {control.action_id!r} uses tabindex "
                        f"{control.tabindex!r} instead of source order",
                        page_index=index,
                        control_id=control.action_id,
                    )
                )
        if not _has_visible_focus_style(dom.styles):
            findings.append(
                _finding(
                    fixture,
                    profile,
                    ConformanceReceipt.KEYBOARD,
                    "keyboard.visible_focus",
                    f"page {index + 1} has no focus-visible styling",
                    page_index=index,
                )
            )


def _has_visible_focus_style(styles: Iterable[str]) -> bool:
    css = _CSS_COMMENT_RE.sub("", "".join(styles))
    for match in _CSS_RULE_RE.finditer(css):
        selectors = match.group("selectors").lower()
        if ":focus-visible" not in selectors:
            continue
        if "button" not in selectors and "[data-workspace-action" not in selectors:
            continue
        declarations = {}
        for declaration in match.group("body").split(";"):
            name, separator, value = declaration.partition(":")
            if separator:
                declarations[name.strip().lower()] = value.strip().lower()
        for property_name in _VISIBLE_FOCUS_PROPERTIES:
            value = declarations.get(property_name, "")
            if value and value not in {"0", "none", "transparent"}:
                return True
    return False


def _check_viewport(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    pages: list[_PageEvidence],
    findings: list[ConformanceFinding],
) -> None:
    viewport = profile.viewport
    if viewport is None:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.VIEWPORT,
                "viewport.fixture",
                "profile requires viewport evidence but declares no viewport fixture",
            )
        )
        return
    if len(pages) > 1 and not profile.navigation.pagination:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.VIEWPORT,
                "viewport.pagination",
                f"{len(pages)} pages require pagination capability",
            )
        )
    capacity = viewport.max_actions_per_view
    if capacity is not None and not profile.navigation.scroll:
        for index, page in enumerate(pages):
            if len(page.model) > capacity:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.VIEWPORT,
                        "viewport.action_reachability",
                        f"{len(page.model)} actions exceed the non-scrolling capacity of {capacity}",
                        page_index=index,
                    )
                )
    discovered = tuple(action_id for page in pages for action_id in page.model)
    if discovered != fixture.expected_action_ids:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.VIEWPORT,
                "viewport.action_discovery",
                f"paged action sequence {discovered!r} does not match {fixture.expected_action_ids!r}",
            )
        )


def _check_parity(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    pages: list[_PageEvidence],
    findings: list[ConformanceFinding],
) -> None:
    for index, page in enumerate(pages):
        for surface in profile.projection_surfaces:
            actual = getattr(page, surface.value)
            if actual != page.model:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.PARITY,
                        "projection.action_parity",
                        f"page {index + 1} {surface.value} actions {actual!r} differ from {page.model!r}",
                        page_index=index,
                    )
                )
    discovered = tuple(action_id for page in pages for action_id in page.model)
    if discovered != fixture.expected_action_ids:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.PARITY,
                "projection.expected_actions",
                f"declared action sequence {discovered!r} does not match {fixture.expected_action_ids!r}",
            )
        )


def _check_retention(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    renderers: ProjectionRenderers,
    findings: list[ConformanceFinding],
) -> None:
    if not (
        profile.retention.prior_output_retained or profile.retention.submitted_view_collapsible
    ):
        return
    if not fixture.submitted_summary.strip():
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.RETENTION,
                "retention.submitted_summary",
                "retained/collapsible output requires a non-empty submitted summary",
            )
        )
        return
    if renderers.retained is None:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.RETENTION,
                "retention.observed_projection",
                "retention receipt requires an observed submitted projection",
            )
        )
        return
    try:
        observed = renderers.retained(fixture)
        if not isinstance(observed, str):
            raise TypeError("retained projection renderer must return str")
    except Exception as exc:  # noqa: BLE001 - renderer plug-in boundary
        logger.warning(
            "conformance retained projection failed with %s: %s",
            type(exc).__name__,
            exc,
        )
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.RETENTION,
                "retention.observed_projection",
                f"retained projection failed with {type(exc).__name__}: {exc}",
            )
        )
        return
    expected_text = " ".join(fixture.submitted_summary.split())
    visible = _VisibleTextParser()
    visible.feed(observed)
    visible.close()
    observed_text = visible.normalized()
    if expected_text not in observed_text:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.RETENTION,
                "retention.completion_meaning",
                "observed submitted projection does not preserve the expected summary",
            )
        )
    parser = _WorkspaceDomParser()
    parser.feed(observed)
    parser.close()
    retained_actions = max(
        len(parser.controls),
        len(_PORTABLE_ACTION_RE.findall(observed)),
    )
    original_actions = sum(len(page.actions) for page in fixture.pages)
    if original_actions and retained_actions >= original_actions:
        findings.append(
            _finding(
                fixture,
                profile,
                ConformanceReceipt.RETENTION,
                "retention.compaction",
                f"submitted projection retains {retained_actions} of "
                f"{original_actions} original action controls",
            )
        )


def _check_latency(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    latency: tuple[PhaseLatency, ...],
    findings: list[ConformanceFinding],
) -> None:
    by_phase = {item.phase: item for item in latency}
    budgets = {item.phase: item for item in profile.latency_budgets}
    for phase in profile.required_latency_phases:
        aggregate = by_phase.get(phase)
        for mode in LatencyMode:
            values = getattr(aggregate, mode.value) if aggregate else None
            if values is None:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.LATENCY,
                        "latency.phase_coverage",
                        f"missing {mode.value} samples for {phase.value}",
                    )
                )
                continue
            phase_budget = budgets.get(phase)
            budget = getattr(phase_budget, f"{mode.value}_p95_ms") if phase_budget else None
            if budget is not None and values.p95 > budget:
                findings.append(
                    _finding(
                        fixture,
                        profile,
                        ConformanceReceipt.LATENCY,
                        "latency.p95_budget",
                        f"{mode.value} {phase.value} p95 {values.p95:g} ms exceeds {budget:g} ms",
                    )
                )


def run_workspace_conformance(
    fixture: WorkspaceFixture,
    profile: InteractionProfile,
    *,
    renderers: ProjectionRenderers | None = None,
    latency_samples: Iterable[LatencySample] = (),
) -> ConformanceReport:
    """Run deterministic receipts without granting action authority."""
    if not isinstance(fixture, WorkspaceFixture):
        raise TypeError("fixture must be WorkspaceFixture")
    if not isinstance(profile, InteractionProfile):
        raise TypeError("profile must be InteractionProfile")
    renderers = renderers or ProjectionRenderers()
    if not isinstance(renderers, ProjectionRenderers):
        raise TypeError("renderers must be ProjectionRenderers")
    raw_samples = tuple(latency_samples)
    latency = summarize_latency(raw_samples)
    findings: list[ConformanceFinding] = []
    unavailable = {item.receipt: item for item in profile.unavailable_receipts}
    pages = _projection_evidence(fixture, profile, renderers, findings, set(unavailable))
    checks: dict[ConformanceReceipt, Callable[[], None]] = {
        ConformanceReceipt.DOM: lambda: _check_dom(fixture, profile, pages, findings),
        ConformanceReceipt.KEYBOARD: lambda: _check_keyboard(fixture, profile, pages, findings),
        ConformanceReceipt.VIEWPORT: lambda: _check_viewport(fixture, profile, pages, findings),
        ConformanceReceipt.PARITY: lambda: _check_parity(fixture, profile, pages, findings),
        ConformanceReceipt.RETENTION: lambda: _check_retention(
            fixture, profile, renderers, findings
        ),
        ConformanceReceipt.LATENCY: lambda: _check_latency(fixture, profile, latency, findings),
    }
    passed: list[ConformanceReceipt] = []
    for receipt in profile.required_receipts:
        if receipt in unavailable:
            continue
        before = len(findings)
        checks[receipt]()
        if not any(item.receipt is receipt for item in findings[before:]):
            passed.append(receipt)
    if findings:
        status = ConformanceStatus.FAILING
    elif unavailable:
        status = ConformanceStatus.UNAVAILABLE
    else:
        status = ConformanceStatus.PASSING
    return ConformanceReport(
        profile_id=profile.id,
        owner=fixture.owner,
        status=status,
        passed_receipts=tuple(passed),
        unavailable_receipts=tuple(profile.unavailable_receipts),
        findings=tuple(findings),
        latency=latency,
        latency_samples=raw_samples,
        interaction_rounds=fixture.interaction_rounds,
        observed_user_dwell_ms=fixture.observed_user_dwell_ms,
        submitted_summary=fixture.submitted_summary,
    )


_PHASES = tuple(LatencyPhase)
_BUDGETS = (
    LatencyBudget(LatencyPhase.SCHEMA_READY, cold_p95_ms=250.0, warm_p95_ms=10.0),
    LatencyBudget(
        LatencyPhase.FIRST_ACTIONABLE_RENDER,
        cold_p95_ms=250.0,
        warm_p95_ms=10.0,
    ),
    LatencyBudget(
        LatencyPhase.ACTION_ACKNOWLEDGED,
        cold_p95_ms=250.0,
        warm_p95_ms=250.0,
    ),
    LatencyBudget(
        LatencyPhase.FIRST_PROGRESS,
        cold_p95_ms=1_000.0,
        warm_p95_ms=1_000.0,
    ),
    LatencyBudget(
        LatencyPhase.PROGRESS_FRESHNESS,
        cold_p95_ms=2_000.0,
        warm_p95_ms=2_000.0,
    ),
)

RICH_WIDGET_STANDARD = InteractionProfile(
    id="rich-widget-standard",
    capabilities=HostCapabilities(True, True, True, True, True),
    navigation=NavigationCapabilities(True, True, True, True),
    retention=RetentionCapabilities(True, True),
    viewport=ViewportClass("rich-scroll", 1024, 768),
    required_receipts=tuple(ConformanceReceipt),
    projection_surfaces=tuple(ProjectionSurface),
    required_latency_phases=_PHASES,
    latency_budgets=_BUDGETS,
)

NATIVE_DIALOG_CONSTRAINED = InteractionProfile(
    id="native-dialog-constrained",
    capabilities=HostCapabilities(forms=True, multi_select=True, postback=True),
    navigation=NavigationCapabilities(True, True, False, True),
    retention=RetentionCapabilities(True, True),
    viewport=ViewportClass("native-compact-three", max_actions_per_view=3),
    required_receipts=(
        ConformanceReceipt.VIEWPORT,
        ConformanceReceipt.PARITY,
        ConformanceReceipt.RETENTION,
        ConformanceReceipt.LATENCY,
    ),
    projection_surfaces=(ProjectionSurface.PORTABLE, ProjectionSurface.HEADLESS),
    required_latency_phases=_PHASES,
    latency_budgets=_BUDGETS,
)

PORTABLE_MARKDOWN = InteractionProfile(
    id="portable-markdown",
    capabilities=HostCapabilities(forms=True, postback=True),
    navigation=NavigationCapabilities(keyboard=True, scroll=True, pagination=True),
    retention=RetentionCapabilities(True, True),
    viewport=None,
    required_receipts=(
        ConformanceReceipt.PARITY,
        ConformanceReceipt.RETENTION,
        ConformanceReceipt.LATENCY,
    ),
    projection_surfaces=(ProjectionSurface.PORTABLE, ProjectionSurface.HEADLESS),
    required_latency_phases=_PHASES,
    latency_budgets=_BUDGETS,
)

HEADLESS_JSON = InteractionProfile(
    id="headless-json",
    capabilities=HostCapabilities(forms=True, postback=True),
    navigation=NavigationCapabilities(pagination=True),
    retention=RetentionCapabilities(),
    viewport=None,
    required_receipts=(ConformanceReceipt.PARITY, ConformanceReceipt.LATENCY),
    projection_surfaces=(ProjectionSurface.HEADLESS,),
    required_latency_phases=_PHASES,
    latency_budgets=_BUDGETS,
)
