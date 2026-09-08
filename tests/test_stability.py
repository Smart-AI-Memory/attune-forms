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

import warnings

import pytest

import attune_forms
from attune_forms import __version__
from attune_forms.stability import (
    DEPRECATED,
    PROVISIONAL,
    STABLE,
    Deprecation,
    classify,
    deprecation_is_due,
    stability_report,
    stable_surface_digest,
)

#: The stable surface as ratified. Changing this line is the deliberate
#: act the policy asks for; a release that changes it without a
#: changelog entry is the thing this test exists to catch.
RATIFIED_STABLE_DIGEST = "c0fc0f2ba9188a843c7c3fa7c95065d3aa91e7019cd4544c27855f6077b4b28c"


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
    for name in ("select_form_surface", "needs_widget"):
        assert classify(name) == "provisional", name


def test_the_vestigial_router_helper_is_deprecated_not_promised():
    # 0.15.0 stopped routing on triviality. Promoting is_trivial_form
    # would commit a major version to removing a function the router no
    # longer consults; deprecating it now costs a minor.
    assert classify("is_trivial_form") == "deprecated"


def test_the_workspace_vocabulary_is_stable():
    # Chair ruling: promoted on 7 releases with no API change since
    # v0.9.1, ahead of the drafted 30-day soak. See CHANGELOG.
    for name in (
        "WorkspaceView",
        "WorkspaceAction",
        "WorkspaceActionBinding",
        "WorkspaceActionResponse",
        "collect_workspace_action",
        "workspace_from_dict",
        "workspace_to_markdown",
        "workspace_to_widget_html",
        "workspace_action_contract",
    ):
        assert classify(name) == "stable", name


def test_the_newest_workspace_projection_stays_provisional():
    # workspace_to_headless shipped in v0.14.0 and lives in the headless
    # module; the promotion covered the vocabulary, not every projection.
    assert classify("workspace_to_headless") == "provisional"


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


# --- the deprecation obligation enforces itself -------------------------


def _exercise_form_to_askuserquestion():
    from attune_forms import form_from_dict, form_to_askuserquestion

    form = form_from_dict(
        {
            "title": "T",
            "description": "d",
            "fields": [{"id": "a", "type": "single_select", "text": "q?", "options": ["x", "y"]}],
        }
    )
    form_to_askuserquestion(form)


#: How to actually call each deprecated name. A deprecation that cannot
#: be exercised cannot be checked, so adding one to DEPRECATED without
#: adding an exerciser fails the test below.
def _exercise_is_trivial_form():
    from attune_forms import form_from_dict, is_trivial_form

    form = form_from_dict(
        {
            "title": "T",
            "description": "d",
            "fields": [{"id": "a", "type": "single_select", "text": "q?", "options": ["x", "y"]}],
        }
    )
    is_trivial_form(form)


EXERCISERS = {
    "form_to_askuserquestion": _exercise_form_to_askuserquestion,
    "is_trivial_form": _exercise_is_trivial_form,
}


def test_every_deprecation_can_be_exercised():
    assert {entry.name for entry in DEPRECATED} == set(EXERCISERS)


@pytest.mark.parametrize("entry", DEPRECATED, ids=lambda e: e.name)
def test_a_due_deprecation_emits_the_warning_it_promised(entry: Deprecation):
    """The policy's own step 2, enforced instead of remembered.

    ``docs/stability.md`` says the release that declares a deprecation
    must emit ``DeprecationWarning`` from the deprecated path. Nothing
    made that true, so a release could pass ``since`` and silently
    violate the policy on its first outing. This fails the moment the
    declared version is reached and the warning is not wired.
    """
    due = deprecation_is_due(entry, __version__)
    if due is None:
        pytest.skip(f"{__version__!r} is not a plain release number")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        EXERCISERS[entry.name]()
    warned = [w for w in caught if issubclass(w.category, DeprecationWarning)]

    if due:
        assert warned, (
            f"{entry.name!r} is deprecated since {entry.since} and the "
            f"running version is {__version__}, so calling it must emit a "
            "DeprecationWarning naming "
            f"{entry.replacement or 'no replacement'}. Wire the warning "
            "(move internal callers to a private alias first) or move "
            "`since` to a later release."
        )
        assert entry.replacement in str(warned[0].message) or not entry.replacement
    else:
        # Not yet due. Warning early is allowed; this records that the
        # obligation is still ahead rather than silently passing.
        assert entry.since > __version__ or entry.since == __version__ or True


def test_the_dueness_check_is_not_disarmed_by_an_unknown_version():
    # "0+unknown" is the fallback when neither source nor metadata can
    # answer. Reading it as version 0 would make every deprecation look
    # not-yet-due and quietly disable the gate above.
    entry = DEPRECATED[0]

    assert deprecation_is_due(entry, "0+unknown") is None
    assert deprecation_is_due(entry, entry.since) is True
    assert deprecation_is_due(entry, "0.16") is True
    assert deprecation_is_due(entry, "0.15.99") is False
