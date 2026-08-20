"""Intake template layer (workflow-intake-forms Phase 2a): the
structural-equality migration gate, ruled build-time boundaries,
and the template-less demand fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from attune_forms.intake_template import (
    PROVIDERS,
    TEMPLATES,
    FieldSlot,
    FormTemplate,
    ProviderContext,
    TemplateError,
    build_form,
    intake_form,
    validate_template,
)

_CTX = ProviderContext(repo_root=Path("/nonexistent"))


# ---------------------------------------------------------------


def test_unknown_provider_rejected() -> None:
    t = FormTemplate("T", "d", [FieldSlot(key="x", text="x?", provider="nope")])
    with pytest.raises(TemplateError, match="unknown provider"):
        validate_template(t)


def test_other_or_fallback_without_provider_rejected() -> None:
    t = FormTemplate("T", "d", [FieldSlot(key="x", text="x?", other="other")])
    with pytest.raises(TemplateError, match="require a provider"):
        validate_template(t)


@dataclass
class _FakeSchema:
    required_fields: dict
    optional_fields: dict


class _FakeWorkflow:
    input_schema = _FakeSchema(
        required_fields={"goal": str},
        optional_fields={"paths": list},
    )


def test_bound_template_tighten_only_and_list_rules(monkeypatch) -> None:
    from attune_forms import intake_template as it

    monkeypatch.setattr(it, "WORKFLOW_SCHEMA_RESOLVER", lambda name: _FakeWorkflow.input_schema)
    loosened = FormTemplate(
        "T", "d", [FieldSlot(key="goal", text="g?", required=False)], workflow="fake"
    )
    with pytest.raises(TemplateError, match="tighten-only"):
        validate_template(loosened)
    unprovided_list = FormTemplate("T", "d", [FieldSlot(key="paths", text="p?")], workflow="fake")
    with pytest.raises(TemplateError, match="no provider"):
        validate_template(unprovided_list)
    tightened = FormTemplate(
        "T",
        "d",
        [FieldSlot(key="goal", text="g?", required=True)],
        workflow="fake",
    )
    validate_template(tightened)


# ---------------------------------------------------------------
# Overrides, prefill, and the template-less demand fallback
# ---------------------------------------------------------------


def test_override_bypasses_provider_and_provider_runs_otherwise() -> None:
    calls: list[str] = []

    def _prov(ctx: ProviderContext) -> list[str]:
        calls.append("ran")
        return ["a", "b"]

    PROVIDERS["_test_prov"] = _prov
    try:
        t = FormTemplate("T", "d", [FieldSlot(key="x", text="x?", provider="_test_prov")])
        overridden = build_form(t, _CTX, candidates_override={"x": ["z"]})
        assert overridden.questions[0].options == ["z"]
        assert calls == []
        live = build_form(t, _CTX)
        assert live.questions[0].options == ["a", "b"]
        assert calls == ["ran"]
    finally:
        del PROVIDERS["_test_prov"]


def test_prefill_is_exact_key_match_only() -> None:
    t = FormTemplate("T", "d", [FieldSlot(key="goal", text="g?")])
    ctx = ProviderContext(repo_root=Path("/nonexistent"), answered={"goal": "fix the boundary"})
    form = build_form(t, ctx)
    assert form.questions[0].default == "fix the boundary"
    unrelated = ProviderContext(repo_root=Path("/nonexistent"), answered={"goal_hint": "not this"})
    assert build_form(t, unrelated).questions[0].default is None


def test_template_less_intake_returns_none_and_marks_demand() -> None:
    assert "no-such-intake" not in TEMPLATES
    assert intake_form("no-such-intake", invocation_text="do a thing") is None


def test_template_loaders_run_before_lookup() -> None:
    """The loader seam: a host-registered loader populates the registry
    before a lookup, so a cold caller never sees a false miss."""
    from attune_forms import intake_template as it

    name = "_loader_seam_intake"
    template = FormTemplate(name, "d", [FieldSlot(key="q", text="q?")])

    def _loader() -> None:
        TEMPLATES.setdefault(name, template)

    it.TEMPLATE_LOADERS.append(_loader)
    try:
        form = intake_form(name)
        assert form is not None
        assert form.questions[0].id == "q"
    finally:
        it.TEMPLATE_LOADERS.remove(_loader)
        TEMPLATES.pop(name, None)


def test_bound_template_without_resolver_rejects() -> None:
    """A workflow-bound template must reject loudly when the host never
    registered a schema resolver — never silently skip validation."""
    from attune_forms import intake_template as it

    assert it.WORKFLOW_SCHEMA_RESOLVER is None
    t = FormTemplate("T", "d", [FieldSlot(key="goal", text="g?")], workflow="fake")
    with pytest.raises(TemplateError, match="no workflow schema resolver"):
        validate_template(t)


def test_non_string_prefill_never_repr_coerced() -> None:
    """Discovery-sweep finding (2026-08-20): a non-string prior answer
    (e.g. a multi-select's list) was str()-coerced into the slot's
    default, presenting junk like "['src/', 'tests/']" as a settled
    value. Non-string prefill is now skipped; the slot's own default
    survives."""
    t = FormTemplate(
        "T",
        "d",
        [FieldSlot(key="scope", text="s?", default="everything")],
    )
    ctx = ProviderContext(repo_root=Path("/nonexistent"), answered={"scope": ["src/", "tests/"]})
    form = build_form(t, ctx)
    assert form.questions[0].default == "everything"

    no_default = FormTemplate("T", "d", [FieldSlot(key="scope", text="s?")])
    form2 = build_form(no_default, ctx)
    assert form2.questions[0].default is None
