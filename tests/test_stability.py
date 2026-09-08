"""The stability manifest is a gate, not a document.

``docs/stability.md`` says what each tier promises. These tests make the
promise checkable: every public name carries exactly one tier, a new
export cannot be added without choosing one, and the stable surface has
a digest a release can compare against.

The digest test is the one that will fail on you. That is the point —
changing the stable set should require deleting a recorded value and
writing a changelog entry, not slipping through review.
"""

from __future__ import annotations

import pytest

import attune_forms
from attune_forms.stability import (
    DEPRECATED,
    PROVISIONAL,
    STABLE,
    Deprecation,
    classify,
    stability_report,
    stable_surface_digest,
)

#: The stable surface as ratified. Changing this line is the deliberate
#: act the policy asks for; a release that changes it without a
#: changelog entry is the thing this test exists to catch.
RATIFIED_STABLE_DIGEST = "c6b5126d5188ff594aa8d5b138d52277e702a3dda25d03eddc5b2bfc200acd99"


def test_every_export_carries_exactly_one_tier():
    report = stability_report()

    assert report.ok, report.problems


def test_the_manifest_covers_the_whole_public_surface():
    tiered = set(STABLE) | set(PROVISIONAL) | {entry.name for entry in DEPRECATED}

    assert tiered == set(attune_forms.__all__)


def test_a_new_export_without_a_tier_is_a_problem():
    report = stability_report(frozenset(attune_forms.__all__) | {"brand_new_thing"})

    assert not report.ok
    assert any("carries no stability tier" in problem for problem in report.problems)


def test_a_tiered_name_that_is_not_exported_is_a_problem():
    report = stability_report(frozenset(attune_forms.__all__) - {"form_from_dict"})

    assert not report.ok
    assert any("not exported" in problem for problem in report.problems)


def test_the_tiers_do_not_overlap():
    assert not set(STABLE) & set(PROVISIONAL)
    assert not set(STABLE) & {entry.name for entry in DEPRECATED}
    assert not set(PROVISIONAL) & {entry.name for entry in DEPRECATED}


def test_the_stable_surface_has_not_moved():
    assert stable_surface_digest() == RATIFIED_STABLE_DIGEST, (
        "The stable surface changed. That is allowed, but it is a "
        "deliberate act: record the new digest here and say what moved "
        "in the changelog."
    )


def test_the_form_core_is_stable():
    # The names a consumer building forms actually depends on. Every one
    # of these first shipped in v0.1.0 and has not changed since.
    for name in (
        "FormSchema",
        "FormQuestion",
        "FormResponse",
        "QuestionType",
        "form_from_dict",
        "collect_form_response",
        "FormValidationError",
        "form_to_widget_html",
        "form_to_elicitation_schema",
    ):
        assert classify(name) == "stable", name


def test_the_host_parity_machinery_is_provisional():
    # Forty of these names arrived in the two releases before 0.15.0.
    for name in (
        "form_to_host_question",
        "host_question_turn",
        "HostQuestionProfile",
        "RENDERER_REGISTRY",
        "sweep_production_renderers",
        "CLAUDE_ASKUSERQUESTION",
        "InteractionProfile",
    ):
        assert classify(name) == "provisional", name


def test_the_router_is_provisional_until_its_default_settles():
    # select_form_surface changed its default in 0.15.0; it cannot be
    # promised while the behavior is one release old.
    for name in ("select_form_surface", "needs_widget", "is_trivial_form"):
        assert classify(name) == "provisional", name


def test_an_unknown_name_carries_no_tier():
    assert classify("not_a_real_export") is None


# --- deprecations --------------------------------------------------------


@pytest.mark.parametrize("entry", DEPRECATED, ids=lambda e: e.name)
def test_every_deprecation_names_a_removal_window_and_a_reason(entry: Deprecation):
    assert entry.since
    assert entry.not_before > entry.since
    assert entry.reason.strip()


@pytest.mark.parametrize("entry", DEPRECATED, ids=lambda e: e.name)
def test_a_deprecated_name_still_works(entry: Deprecation):
    # Deprecated is a schedule, not a removal. Until not_before, the
    # name must still be importable and callable.
    assert hasattr(attune_forms, entry.name)


@pytest.mark.parametrize("entry", DEPRECATED, ids=lambda e: e.name)
def test_a_named_replacement_is_itself_exported(entry: Deprecation):
    if entry.replacement:
        assert entry.replacement in attune_forms.__all__


def test_a_deprecation_with_a_backwards_window_is_a_problem(monkeypatch):
    bad = (
        Deprecation(
            name="form_to_askuserquestion",
            since="0.18.0",
            not_before="0.16.0",
            replacement="form_to_host_question",
            reason="backwards on purpose",
        ),
    )
    monkeypatch.setattr("attune_forms.stability.DEPRECATED", bad)

    report = stability_report()

    assert not report.ok
    assert any("does not follow" in problem for problem in report.problems)
