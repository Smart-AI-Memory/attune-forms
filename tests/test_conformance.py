"""Behavioral contract for the generic interaction-conformance harness."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest

from attune_forms import (
    HEADLESS_JSON,
    NATIVE_DIALOG_CONSTRAINED,
    PORTABLE_MARKDOWN,
    RICH_WIDGET_STANDARD,
    ConformanceReceipt,
    ConformanceStatus,
    InteractionProfile,
    LatencyBudget,
    LatencyMode,
    LatencyPhase,
    LatencySample,
    ProjectionRenderers,
    ProjectionSurface,
    UnavailableReceipt,
    ViewportClass,
    WorkspaceAction,
    WorkspaceFixture,
    WorkspaceView,
    WorkspaceViewId,
    measure_latency,
    run_workspace_conformance,
    summarize_latency,
    workspace_to_markdown,
)

_ACTION_IDS = tuple(f"candidate_{index}" for index in range(1, 8))


def _view(*action_ids: str, title: str = "Promotion review") -> WorkspaceView:
    return WorkspaceView(
        id=WorkspaceViewId.PREVIEW,
        title=title,
        actions=tuple(
            WorkspaceAction(id=action_id, label=f"Rule {action_id.replace('_', ' ')}")
            for action_id in action_ids
        ),
    )


def _fixture(*pages: WorkspaceView) -> WorkspaceFixture:
    return WorkspaceFixture(
        owner="shared-command-workspaces",
        pages=pages,
        expected_action_ids=_ACTION_IDS,
        submitted_summary="Seven rulings recorded; no candidate was lost.",
        interaction_rounds=len(pages),
    )


def _complete_samples(profile: InteractionProfile) -> tuple[LatencySample, ...]:
    samples = []
    for phase in profile.required_latency_phases:
        for mode in LatencyMode:
            samples.extend(
                LatencySample(phase=phase, mode=mode, duration_ms=value)
                for value in (0.5, 0.75, 1.0, 1.25, 1.5)
            )
    return tuple(samples)


def _renderers(**overrides: object) -> ProjectionRenderers:
    defaults = ProjectionRenderers()
    values = {
        "rich": defaults.rich,
        "portable": defaults.portable,
        "headless": defaults.headless,
        "retained": lambda fixture: f"<p>{fixture.submitted_summary}</p>",
    }
    values.update(overrides)
    return ProjectionRenderers(**values)  # type: ignore[arg-type]


def test_ratified_profiles_are_capability_only_and_contain_no_authority_fields() -> None:
    profiles = (
        RICH_WIDGET_STANDARD,
        NATIVE_DIALOG_CONSTRAINED,
        PORTABLE_MARKDOWN,
        HEADLESS_JSON,
    )
    assert {profile.id for profile in profiles} == {
        "rich-widget-standard",
        "native-dialog-constrained",
        "portable-markdown",
        "headless-json",
    }
    serialized_names = {
        field.name
        for profile in profiles
        for model in (profile, profile.capabilities, profile.navigation, profile.retention)
        for field in fields(model)
    }
    forbidden = {
        "workspace_id",
        "revision",
        "action_nonce",
        "contract_hash",
        "transition",
        "legal_actions",
    }
    assert serialized_names.isdisjoint(forbidden)


def test_original_seven_action_native_shape_fails_constrained_viewport() -> None:
    report = run_workspace_conformance(
        _fixture(_view(*_ACTION_IDS)),
        NATIVE_DIALOG_CONSTRAINED,
        latency_samples=_complete_samples(NATIVE_DIALOG_CONSTRAINED),
    )
    assert report.status is ConformanceStatus.FAILING
    finding = next(item for item in report.findings if item.receipt is ConformanceReceipt.VIEWPORT)
    assert finding.owner == "shared-command-workspaces"
    assert finding.property == "viewport.action_reachability"
    assert "7 actions exceed" in finding.evidence
    assert finding.viewport_id == "native-compact-three"


def test_one_candidate_pages_pass_the_rich_profile_with_structural_receipts() -> None:
    fixture = _fixture(
        *(
            _view(action_id, title=f"Candidate {index}")
            for index, action_id in enumerate(_ACTION_IDS, 1)
        )
    )
    report = run_workspace_conformance(
        fixture,
        RICH_WIDGET_STANDARD,
        renderers=_renderers(),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert report.status is ConformanceStatus.PASSING
    assert report.passed
    assert set(report.passed_receipts) == set(RICH_WIDGET_STANDARD.required_receipts)
    assert report.interaction_rounds == 7
    assert report.submitted_summary == fixture.submitted_summary


def test_compact_batches_pass_portable_and_native_profiles() -> None:
    fixture = _fixture(
        _view(*_ACTION_IDS[:3], title="Batch 1"),
        _view(*_ACTION_IDS[3:6], title="Batch 2"),
        _view(*_ACTION_IDS[6:], title="Batch 3"),
    )
    for profile in (PORTABLE_MARKDOWN, NATIVE_DIALOG_CONSTRAINED):
        report = run_workspace_conformance(
            fixture,
            profile,
            renderers=_renderers(),
            latency_samples=_complete_samples(profile),
        )
        assert report.status is ConformanceStatus.PASSING, report.findings


def test_button_substring_without_dom_semantics_cannot_pass() -> None:
    renderers = ProjectionRenderers(
        rich=lambda view: "screenshot text: <button>Rule candidate 1</button>",
        portable=workspace_to_markdown,
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        RICH_WIDGET_STANDARD,
        renderers=renderers,
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert report.status is ConformanceStatus.FAILING
    receipts = {finding.receipt for finding in report.findings}
    assert ConformanceReceipt.DOM in receipts
    assert ConformanceReceipt.PARITY in receipts


def test_keyboard_receipt_requires_native_ordered_controls_and_visible_focus() -> None:
    def div_renderer(view: WorkspaceView) -> str:
        controls = "".join(
            f'<div data-workspace-action="{action.id}">{action.label}</div>'
            for action in view.actions
        )
        return f'<div data-workspace-view="{view.id.value}">{controls}</div>'

    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        RICH_WIDGET_STANDARD,
        renderers=ProjectionRenderers(rich=div_renderer, portable=workspace_to_markdown),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    keyboard = [
        finding for finding in report.findings if finding.receipt is ConformanceReceipt.KEYBOARD
    ]
    assert keyboard
    assert any("native button" in finding.evidence for finding in keyboard)
    assert any("focus-visible" in finding.evidence for finding in keyboard)


def test_projection_parity_detects_a_portable_action_drop() -> None:
    def dropping_markdown(view: WorkspaceView) -> str:
        text = workspace_to_markdown(view)
        if not view.actions:
            return text
        action_id = view.actions[-1].id
        return "\n".join(line for line in text.splitlines() if f"`{action_id}`" not in line)

    fixture = _fixture(
        _view(*_ACTION_IDS[:3]),
        _view(*_ACTION_IDS[3:6]),
        _view(*_ACTION_IDS[6:]),
    )
    report = run_workspace_conformance(
        fixture,
        PORTABLE_MARKDOWN,
        renderers=ProjectionRenderers(portable=dropping_markdown),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    parity = [
        finding for finding in report.findings if finding.receipt is ConformanceReceipt.PARITY
    ]
    assert parity
    assert any("portable" in finding.evidence for finding in parity)


def test_renderer_only_timing_cannot_produce_latency_pass() -> None:
    render_only = tuple(
        LatencySample(
            phase=LatencyPhase.FIRST_ACTIONABLE_RENDER,
            mode=mode,
            duration_ms=1.0,
        )
        for mode in LatencyMode
        for _ in range(5)
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        PORTABLE_MARKDOWN,
        latency_samples=render_only,
    )
    assert report.status is ConformanceStatus.FAILING
    latency_findings = [
        finding for finding in report.findings if finding.receipt is ConformanceReceipt.LATENCY
    ]
    assert latency_findings
    assert any("action_acknowledged" in finding.evidence for finding in latency_findings)
    assert LatencyPhase.FIRST_ACTIONABLE_RENDER in {item.phase for item in report.latency}


def test_latency_summary_emits_cold_and_warm_p50_p95_p99() -> None:
    samples = tuple(
        LatencySample(LatencyPhase.ACTION_ACKNOWLEDGED, mode, value)
        for mode in LatencyMode
        for value in (1.0, 2.0, 3.0, 4.0, 100.0)
    )
    (summary,) = summarize_latency(samples)
    assert summary.phase is LatencyPhase.ACTION_ACKNOWLEDGED
    for aggregate in (summary.cold, summary.warm):
        assert aggregate is not None
        assert aggregate.n == 5
        assert aggregate.p50 == 3.0
        assert aggregate.p95 == 100.0
        assert aggregate.p99 == 100.0


def test_measure_latency_uses_injected_clock_and_preserves_raw_samples() -> None:
    ticks = iter((0, 1_000_000, 2_000_000, 5_000_000, 8_000_000, 12_000_000))
    calls = []
    samples = measure_latency(
        lambda: calls.append("called"),
        phase=LatencyPhase.SCHEMA_READY,
        mode=LatencyMode.COLD,
        sample_count=3,
        clock_ns=lambda: next(ticks),
    )
    assert calls == ["called"] * 3
    assert [sample.duration_ms for sample in samples] == [1.0, 3.0, 4.0]


def test_missing_submitted_summary_fails_retention_receipt() -> None:
    fixture = WorkspaceFixture(
        owner="shared-command-workspaces",
        pages=tuple(_view(action_id) for action_id in _ACTION_IDS),
        expected_action_ids=_ACTION_IDS,
        submitted_summary="",
        interaction_rounds=7,
    )
    report = run_workspace_conformance(
        fixture,
        RICH_WIDGET_STANDARD,
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert any(finding.receipt is ConformanceReceipt.RETENTION for finding in report.findings)


def test_explicit_unavailable_receipt_never_counts_as_passing() -> None:
    profile = replace(
        PORTABLE_MARKDOWN,
        unavailable_receipts=(
            UnavailableReceipt(ConformanceReceipt.PARITY, "portable transport is offline"),
        ),
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        profile,
        renderers=_renderers(),
        latency_samples=_complete_samples(profile),
    )
    assert report.status is ConformanceStatus.UNAVAILABLE
    assert not report.passed
    assert ConformanceReceipt.PARITY not in report.passed_receipts
    assert report.unavailable_receipts[0].reason == "portable transport is offline"


def test_latency_budget_is_mode_specific_and_tail_sensitive() -> None:
    profile = replace(
        PORTABLE_MARKDOWN,
        capabilities=replace(PORTABLE_MARKDOWN.capabilities, forms=False, postback=False),
        required_latency_phases=(LatencyPhase.FIRST_ACTIONABLE_RENDER,),
        latency_budgets=(
            LatencyBudget(
                LatencyPhase.FIRST_ACTIONABLE_RENDER,
                cold_p95_ms=250.0,
                warm_p95_ms=10.0,
            ),
        ),
    )
    samples = tuple(
        LatencySample(
            LatencyPhase.FIRST_ACTIONABLE_RENDER,
            mode,
            value,
        )
        for mode, values in (
            (LatencyMode.COLD, (100.0, 120.0, 200.0)),
            (LatencyMode.WARM, (1.0, 2.0, 11.0)),
        )
        for value in values
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        profile,
        renderers=_renderers(),
        latency_samples=samples,
    )
    findings = [item for item in report.findings if item.property == "latency.p95_budget"]
    assert len(findings) == 1
    assert "warm first_actionable_render p95 11 ms exceeds 10 ms" in findings[0].evidence


def test_malformed_portable_return_path_fails_even_when_action_text_is_present() -> None:
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        PORTABLE_MARKDOWN,
        renderers=ProjectionRenderers(
            portable=lambda view: "### Actions\n"
            + "\n".join(f"- `{action.id}` — {action.label}" for action in view.actions)
        ),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert any(
        item.property == "projection.return_path" and "JSON response contract" in item.evidence
        for item in report.findings
    )


def test_dom_and_keyboard_negative_receipts_name_each_missing_property() -> None:
    def inaccessible(view: WorkspaceView) -> str:
        return "".join(
            f'<button data-workspace-action="{action.id}" disabled tabindex="-1"></button>'
            for action in view.actions
        )

    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        RICH_WIDGET_STANDARD,
        renderers=ProjectionRenderers(rich=inaccessible),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    properties = {item.property for item in report.findings}
    assert {
        "dom.workspace_structure",
        "dom.action_acknowledgement",
        "dom.programmatic_name",
        "keyboard.reachability",
        "keyboard.visible_focus",
    }.issubset(properties)


def test_profile_rejects_a_required_viewport_without_a_fixture() -> None:
    with pytest.raises(ValueError, match="viewport receipt requires"):
        replace(NATIVE_DIALOG_CONSTRAINED, viewport=None)


def test_viewport_receipt_rejects_missing_pagination_and_actions() -> None:
    fixture = WorkspaceFixture(
        owner="shared-command-workspaces",
        pages=(_view(_ACTION_IDS[0]), _view(_ACTION_IDS[1])),
        expected_action_ids=_ACTION_IDS,
        submitted_summary="Two of seven shown.",
        interaction_rounds=2,
    )
    no_pagination = replace(
        NATIVE_DIALOG_CONSTRAINED,
        navigation=replace(NATIVE_DIALOG_CONSTRAINED.navigation, pagination=False),
        viewport=ViewportClass("two-actions", max_actions_per_view=3),
    )
    report = run_workspace_conformance(
        fixture,
        no_pagination,
        latency_samples=_complete_samples(no_pagination),
    )
    properties = {item.property for item in report.findings}
    assert "viewport.pagination" in properties
    assert "viewport.action_discovery" in properties
    assert "projection.expected_actions" in properties


def test_void_elements_inside_action_controls_do_not_drop_later_controls() -> None:
    fixture = _fixture(*(_view(action_id) for action_id in _ACTION_IDS))

    def rich(view: WorkspaceView) -> str:
        controls = "".join(
            f'<button data-workspace-action="{action.id}">{action.label}<br></button>'
            for action in view.actions
        )
        return (
            '<section data-workspace-view="preview">'
            "<style>button:focus-visible{outline:3px solid blue}</style>"
            '<p role="status" aria-live="polite"></p>'
            f"{controls}</section>"
        )

    report = run_workspace_conformance(
        fixture,
        RICH_WIDGET_STANDARD,
        renderers=_renderers(rich=rich),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert report.status is ConformanceStatus.PASSING, report.findings


def test_retention_requires_an_observed_compacted_projection() -> None:
    fixture = _fixture(*(_view(action_id) for action_id in _ACTION_IDS))
    missing = run_workspace_conformance(
        fixture,
        PORTABLE_MARKDOWN,
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert any(item.property == "retention.observed_projection" for item in missing.findings)

    hidden = run_workspace_conformance(
        fixture,
        PORTABLE_MARKDOWN,
        renderers=_renderers(retained=lambda item: f"<script>{item.submitted_summary}</script>"),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert any(item.property == "retention.completion_meaning" for item in hidden.findings)

    repeated_actions = "".join(
        f'<button data-workspace-action="{action_id}">{action_id}</button>'
        for action_id in _ACTION_IDS
    )
    uncompact = run_workspace_conformance(
        fixture,
        PORTABLE_MARKDOWN,
        renderers=_renderers(
            retained=lambda item: f"<p>{item.submitted_summary}</p>{repeated_actions}"
        ),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert any(item.property == "retention.compaction" for item in uncompact.findings)


def test_focus_receipt_requires_a_control_rule_with_visible_declarations() -> None:
    fixture = _fixture(*(_view(action_id) for action_id in _ACTION_IDS))

    def decoy_focus(view: WorkspaceView) -> str:
        controls = "".join(
            f'<button data-workspace-action="{action.id}">{action.label}</button>'
            for action in view.actions
        )
        return (
            '<section data-workspace-view="preview">'
            "<style>/* button:focus-visible{outline:3px solid blue} */"
            ":focus-visible{}</style>"
            '<p role="status" aria-live="polite"></p>'
            f"{controls}</section>"
        )

    report = run_workspace_conformance(
        fixture,
        RICH_WIDGET_STANDARD,
        renderers=_renderers(rich=decoy_focus),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert any(item.property == "keyboard.visible_focus" for item in report.findings)


@pytest.mark.parametrize(
    "profile, message",
    [
        (
            lambda: replace(
                RICH_WIDGET_STANDARD,
                projection_surfaces=(ProjectionSurface.PORTABLE,),
            ),
            "rich projection",
        ),
        (
            lambda: replace(
                PORTABLE_MARKDOWN,
                required_latency_phases=tuple(
                    phase
                    for phase in PORTABLE_MARKDOWN.required_latency_phases
                    if phase is not LatencyPhase.TERMINAL_RECEIPT
                ),
                latency_budgets=(LatencyBudget(LatencyPhase.TERMINAL_RECEIPT, warm_p95_ms=1.0),),
            ),
            "required latency phases",
        ),
        (
            lambda: replace(
                RICH_WIDGET_STANDARD,
                required_latency_phases=tuple(
                    phase
                    for phase in RICH_WIDGET_STANDARD.required_latency_phases
                    if phase
                    not in {
                        LatencyPhase.FIRST_PROGRESS,
                        LatencyPhase.PROGRESS_FRESHNESS,
                    }
                ),
                latency_budgets=tuple(
                    budget
                    for budget in RICH_WIDGET_STANDARD.latency_budgets
                    if budget.phase
                    not in {
                        LatencyPhase.FIRST_PROGRESS,
                        LatencyPhase.PROGRESS_FRESHNESS,
                    }
                ),
            ),
            "live-update phases",
        ),
    ],
)
def test_profile_rejects_inconsistent_capability_contracts(profile, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        profile()


def test_renderer_exceptions_become_fail_closed_findings() -> None:
    def unavailable_renderer(_view: WorkspaceView) -> str:
        raise RuntimeError("renderer offline")

    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        PORTABLE_MARKDOWN,
        renderers=_renderers(portable=unavailable_renderer),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert any(
        item.property == "projection.return_path" and "RuntimeError" in item.evidence
        for item in report.findings
    )


def test_unavailable_parity_does_not_run_or_fail_its_projection() -> None:
    calls: list[str] = []

    def unavailable_renderer(_view: WorkspaceView) -> str:
        calls.append("called")
        raise RuntimeError("transport unavailable")

    profile = replace(
        PORTABLE_MARKDOWN,
        unavailable_receipts=(
            UnavailableReceipt(ConformanceReceipt.PARITY, "portable transport is offline"),
        ),
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        profile,
        renderers=_renderers(portable=unavailable_renderer),
        latency_samples=_complete_samples(profile),
    )
    assert report.status is ConformanceStatus.UNAVAILABLE
    assert calls == []


def test_positive_tabindex_fails_source_order_receipt() -> None:
    fixture = _fixture(*(_view(action_id) for action_id in _ACTION_IDS))

    def reordered(view: WorkspaceView) -> str:
        controls = "".join(
            f'<button data-workspace-action="{action.id}" tabindex="3">' f"{action.label}</button>"
            for action in view.actions
        )
        return (
            '<section data-workspace-view="preview">'
            "<style>button:focus-visible{outline:3px solid blue}</style>"
            '<p role="status" aria-live="polite"></p>'
            f"{controls}</section>"
        )

    report = run_workspace_conformance(
        fixture,
        RICH_WIDGET_STANDARD,
        renderers=_renderers(rich=reordered),
        latency_samples=_complete_samples(RICH_WIDGET_STANDARD),
    )
    assert any(
        item.property == "keyboard.tab_order" and item.control_id for item in report.findings
    )


def test_portable_parser_ignores_decoy_actions_and_trailing_json() -> None:
    fixture = _fixture(*(_view(action_id) for action_id in _ACTION_IDS))

    def decorated(view: WorkspaceView) -> str:
        return (
            "Evidence:\n- `decoy` — not an action\n\n"
            f'{workspace_to_markdown(view)}\n\n```json\n{{"code": true}}\n```'
        )

    report = run_workspace_conformance(
        fixture,
        PORTABLE_MARKDOWN,
        renderers=_renderers(portable=decorated),
        latency_samples=_complete_samples(PORTABLE_MARKDOWN),
    )
    assert report.status is ConformanceStatus.PASSING, report.findings


def test_latency_budget_compares_unrounded_percentile() -> None:
    profile = replace(
        PORTABLE_MARKDOWN,
        capabilities=replace(PORTABLE_MARKDOWN.capabilities, forms=False, postback=False),
        required_latency_phases=(LatencyPhase.FIRST_ACTIONABLE_RENDER,),
        latency_budgets=(
            LatencyBudget(
                LatencyPhase.FIRST_ACTIONABLE_RENDER,
                cold_p95_ms=10.0,
                warm_p95_ms=10.0,
            ),
        ),
    )
    samples = tuple(
        LatencySample(LatencyPhase.FIRST_ACTIONABLE_RENDER, mode, 10.0004) for mode in LatencyMode
    )
    report = run_workspace_conformance(
        _fixture(*(_view(action_id) for action_id in _ACTION_IDS)),
        profile,
        renderers=_renderers(),
        latency_samples=samples,
    )
    assert [item.property for item in report.findings].count("latency.p95_budget") == 2


def test_measure_latency_runs_warmups_and_rejects_backwards_clock() -> None:
    calls = []
    ticks = iter((5, 4))
    with pytest.raises(ValueError, match="clock moved backwards"):
        measure_latency(
            lambda: calls.append("called"),
            phase=LatencyPhase.SCHEMA_READY,
            mode=LatencyMode.WARM,
            sample_count=1,
            warmup_count=2,
            clock_ns=lambda: next(ticks),
        )
    assert calls == ["called"] * 3


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ViewportClass(""),
        lambda: ViewportClass("bad", width_px=0),
        lambda: LatencyBudget("schema_ready", warm_p95_ms=1.0),
        lambda: LatencyBudget(LatencyPhase.SCHEMA_READY),
        lambda: LatencyBudget(LatencyPhase.SCHEMA_READY, warm_p95_ms=True),
        lambda: UnavailableReceipt("dom", "reason"),
        lambda: UnavailableReceipt(ConformanceReceipt.DOM, ""),
    ],
)
def test_profile_value_objects_reject_malformed_contracts(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


@pytest.mark.parametrize("value", [0, -1, True])
def test_measure_latency_rejects_invalid_sample_counts(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="sample_count"):
        measure_latency(
            lambda: None,
            phase=LatencyPhase.SCHEMA_READY,
            mode=LatencyMode.WARM,
            sample_count=value,  # type: ignore[arg-type]
        )
