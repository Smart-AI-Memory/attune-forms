"""Which public names attune-forms promises, and how strongly.

The package exports 139 names. Promising all of them equally would be
a promise the project cannot keep: the form core has been unchanged
since v0.1.0, while the host-parity machinery grew by 40 names in the
two releases before this one. This module says which is which, and a
test fails closed if a new export is added without a tier.

Three tiers, defined in ``docs/stability.md``:

``STABLE``
    Signature and documented behavior change only through a deprecation
    cycle; removal only in a major version. Every name here first
    shipped on or before v0.10.0 and has not changed since.

``PROVISIONAL``
    Real, supported, and covered by tests, but the shape is still
    settling. May change or be removed in any minor release with a
    changelog entry and no deprecation cycle owed. New surface starts
    here, and is promoted only after a recorded soak.

``DEPRECATED``
    Scheduled for removal, with a named replacement and the earliest
    version that may remove it. Still works until then.

:func:`stability_report` is the gate: every name in the package's
``__all__`` carries exactly one tier, and every tiered name is actually
exported. :func:`stable_surface_digest` lets a release prove the stable
set did not move.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Deprecation:
    """One deprecated name, with the commitment attached to it."""

    name: str
    #: Version whose changelog announced the deprecation.
    since: str
    #: Earliest version that may remove it. Never earlier than the
    #: window in ``docs/stability.md``.
    not_before: str
    #: The name a caller should move to, or "" when there is none.
    replacement: str
    reason: str


#: Names whose signature and documented behavior are promised.
STABLE: tuple[str, ...] = (
    "FieldSlot",  # v0.1.0
    "FormQuestion",  # v0.1.0
    "FormResponse",  # v0.1.0
    "FormSchema",  # v0.1.0
    "FormTemplate",  # v0.1.0
    "FormValidationError",  # v0.1.0
    "ProviderContext",  # v0.1.0
    "QuestionType",  # v0.1.0
    "TemplateError",  # v0.1.0
    "build_form",  # v0.1.0
    "collect_form_response",  # v0.1.0
    "form_from_dict",  # v0.1.0
    "form_from_template",  # v0.1.0
    "form_response_summary",  # v0.1.0
    "form_to_elicitation_schema",  # v0.1.0
    "form_to_markdown",  # v0.5.0
    "form_to_widget_html",  # v0.1.0
    "inferred_field_count",  # v0.1.0
    "intake_form",  # v0.1.0
    "is_fully_inferred",  # v0.1.0
    "keyboard_mode_enabled",  # v0.1.0
    "list_templates",  # v0.1.0
    "markdown_to_answers",  # v0.5.0
    "problems_to_markdown",  # v0.5.0
    "ranking_slot_count",  # v0.6.0
    "set_keyboard_mode",  # v0.1.0
    "token",  # v0.9.0
    "triage_item_key",  # v0.5.0
    "validate_template",  # v0.1.0
)

#: Names that are supported but still settling. See the module docstring.
PROVISIONAL: tuple[str, ...] = (
    "ASKUSERQUESTION_HOST_QUESTION",  # v0.15.0
    "ASSUMPTION_RULINGS",  # v0.6.0
    "Admissibility",  # v0.15.0
    "AllowlistEntry",  # v0.14.0
    "CLAUDE_ASKUSERQUESTION",  # v0.15.0
    "ConformanceFinding",  # v0.12.0
    "ConformanceReceipt",  # v0.12.0
    "ConformanceReport",  # v0.12.0
    "ConformanceStatus",  # v0.12.0
    "EXAMPLE_ANSWERS",  # v0.1.0
    "HEADLESS_JSON",  # v0.12.0
    "HEADLESS_SCHEMA_VERSION",  # v0.14.0
    "HostCapabilities",  # v0.12.0
    "HostQuestionBatch",  # v0.15.0
    "HostQuestionDecoding",  # UNRELEASED
    "HostQuestionProfile",  # v0.15.0
    "HostQuestionReceipt",  # UNRELEASED
    "HostQuestionTurn",  # UNRELEASED
    "INTERACTION_PROFILES",  # v0.15.0
    "InteractionProfile",  # v0.12.0
    "LatencyBudget",  # v0.12.0
    "LatencyMode",  # v0.12.0
    "LatencyPhase",  # v0.12.0
    "LatencySample",  # v0.12.0
    "MCP_APPS_EXTENSION",  # v0.10.0
    "MCP_APP_MIME_TYPE",  # v0.10.0
    "MCP_APP_PROTOCOL_VERSION",  # v0.10.0
    "MCP_APP_RESOURCE_URI",  # v0.10.0
    "MultiSelectEncoding",  # v0.15.0
    "NATIVE_DIALOG_CONSTRAINED",  # v0.12.0
    "NORMALIZATION_RULES",  # v0.14.0
    "NavigationCapabilities",  # v0.12.0
    "NormalizationRule",  # v0.14.0
    "PORTABLE_MARKDOWN",  # v0.12.0
    "PROVIDERS",  # v0.1.0
    "Percentiles",  # v0.12.0
    "PhaseLatency",  # v0.12.0
    "ProjectionRenderers",  # v0.12.0
    "ProjectionSurface",  # v0.12.0
    "QuestionAnswerBinding",  # v0.15.0
    "RECOMMENDED_SUFFIX",  # v0.15.0
    "REFERENCE_FORM",  # v0.1.0
    "RENDERER_REGISTRY",  # v0.14.0
    "RICH_WIDGET_STANDARD",  # v0.12.0
    "RegistryError",  # v0.14.0
    "RendererRecord",  # v0.14.0
    "RendererTarget",  # v0.14.0
    "RetentionCapabilities",  # v0.12.0
    "SEMANTIC_TOKENS",  # v0.9.0
    "SWEEP_ALLOWLIST",  # v0.14.0
    "SweepReport",  # v0.14.0
    "TEMPLATES",  # v0.1.0
    "TURN_OUTCOMES",  # UNRELEASED
    "UnavailableReceipt",  # v0.12.0
    "ViewportClass",  # v0.12.0
    "WIDGET_RESPONSE_MARKER",  # v0.1.0
    "WorkspaceAction",  # v0.9.0
    "WorkspaceActionBinding",  # v0.9.1
    "WorkspaceActionIntent",  # v0.9.0
    "WorkspaceActionResponse",  # v0.9.1
    "WorkspaceBlock",  # v0.9.0
    "WorkspaceBlockKind",  # v0.9.0
    "WorkspaceFixture",  # v0.12.0
    "WorkspaceItem",  # v0.9.0
    "WorkspaceSection",  # v0.9.0
    "WorkspaceTone",  # v0.9.0
    "WorkspaceValidationError",  # v0.9.1
    "WorkspaceView",  # v0.9.0
    "WorkspaceViewId",  # v0.9.0
    "canonical_binding",  # v0.14.0
    "canonical_form",  # v0.14.0
    "canonical_form_answers",  # v0.14.0
    "canonical_host_question_answers",  # v0.15.0
    "canonical_host_question_form",  # v0.15.0
    "canonical_host_question_response",  # v0.15.0
    "canonical_workspace_response",  # v0.14.0
    "canonical_workspace_view",  # v0.14.0
    "client_supports_mcp_apps",  # v0.10.0
    "collect_workspace_action",  # v0.9.1
    "decode_host_question_response",  # UNRELEASED
    "fixture_digest",  # v0.14.0
    "form_to_host_question",  # v0.15.0
    "host_question_admissibility",  # v0.15.0
    "host_question_turn",  # UNRELEASED
    "implementation_digest",  # v0.14.0
    "installed_profile",  # v0.15.0
    "is_trivial_form",  # v0.1.0
    "iter_targets",  # v0.14.0
    "log_surface_decision",  # v0.1.0
    "mcp_app_resource",  # v0.10.0
    "mcp_app_result",  # v0.10.0
    "mcp_app_tool_meta",  # v0.10.0
    "measure_latency",  # v0.12.0
    "needs_widget",  # v0.1.0
    "projection_output_types",  # v0.14.0
    "record_digest",  # v0.14.0
    "registry_digest",  # v0.14.0
    "render_fixture",  # v0.15.0
    "run_workspace_conformance",  # v0.12.0
    "select_form_surface",  # v0.1.0
    "summarize_latency",  # v0.12.0
    "sweep_production_renderers",  # v0.14.0
    "template_example_slots",  # v0.13.0
    "validate_registry",  # v0.14.0
    "workspace_action_contract",  # v0.12.0
    "workspace_from_dict",  # v0.9.1
    "workspace_to_headless",  # v0.14.0
    "workspace_to_markdown",  # v0.9.0
    "workspace_to_widget_html",  # v0.9.0
)

#: Names scheduled for removal.
DEPRECATED: tuple[Deprecation, ...] = (
    Deprecation(
        name="form_to_askuserquestion",
        since="0.16.0",
        not_before="0.18.0",
        replacement="form_to_host_question",
        reason=(
            "The compatibility-only projection predates the host-question "
            "profile. It flattens a form against a fixed contract id instead "
            "of a declared profile, and cannot report admissibility or retain "
            "answer bindings. The registry already marks it "
            "compatibility_only; this schedules the removal while it is still "
            "a minor-version change."
        ),
    ),
)

TIERS: tuple[str, ...] = ("stable", "provisional", "deprecated")


def _deprecated_names() -> frozenset[str]:
    return frozenset(entry.name for entry in DEPRECATED)


def classify(name: str) -> str | None:
    """The tier of one public name, or ``None`` when it carries no tier."""
    if name in _deprecated_names():
        return "deprecated"
    if name in STABLE:
        return "stable"
    if name in PROVISIONAL:
        return "provisional"
    return None


@dataclass(frozen=True)
class StabilityReport:
    """Whether the manifest and the package's ``__all__`` agree."""

    problems: tuple[str, ...]
    stable: int
    provisional: int
    deprecated: int

    @property
    def ok(self) -> bool:
        """True when every export carries exactly one tier."""
        return not self.problems


def stability_report(exports: frozenset[str] | None = None) -> StabilityReport:
    """Check the manifest against the package's public surface.

    Fails closed in both directions: a new export with no tier is a
    problem (the author must choose one), and a tiered name that is not
    exported is a problem (the manifest is stale). A name may not appear
    in two tiers.

    Args:
        exports: The package's ``__all__``; defaults to the live package.
    """
    if exports is None:
        import attune_forms

        exports = frozenset(attune_forms.__all__)
    problems: list[str] = []
    deprecated = _deprecated_names()
    tiers = {
        "stable": frozenset(STABLE),
        "provisional": frozenset(PROVISIONAL),
        "deprecated": deprecated,
    }
    for left in TIERS:
        for right in TIERS:
            if left < right:
                both = tiers[left] & tiers[right]
                if both:
                    problems.append(f"{sorted(both)} appear in both {left} and {right}")
    tiered = tiers["stable"] | tiers["provisional"] | deprecated
    for name in sorted(exports - tiered):
        problems.append(
            f"{name!r} is exported but carries no stability tier; "
            "add it to PROVISIONAL unless it is a promotion"
        )
    for name in sorted(tiered - exports):
        problems.append(f"{name!r} carries a stability tier but is not exported")
    for entry in DEPRECATED:
        if entry.since >= entry.not_before:
            problems.append(
                f"{entry.name!r}: not_before {entry.not_before} does not follow "
                f"since {entry.since}"
            )
        if not entry.reason.strip():
            problems.append(f"{entry.name!r}: a deprecation needs a reason")
    return StabilityReport(
        problems=tuple(problems),
        stable=len(STABLE),
        provisional=len(PROVISIONAL),
        deprecated=len(deprecated),
    )


def stable_surface_digest() -> str:
    """SHA-256 of the stable names, so a release can prove they did not move.

    Only the stable tier feeds the digest. Provisional names are
    expected to change; that is what the tier means.
    """
    payload = json.dumps(sorted(STABLE), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "DEPRECATED",
    "PROVISIONAL",
    "STABLE",
    "TIERS",
    "Deprecation",
    "StabilityReport",
    "classify",
    "stability_report",
    "stable_surface_digest",
]
