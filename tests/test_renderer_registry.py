"""Renderer registry, no-escape sweep, digests and canonical fixtures (AF-1).

attune-ai host-surface-parity D10/D12: the registry is the public
inventory of every production projection; the sweep proves nothing
escapes it; the digests let the consuming gate (Task 1B) lock a
released artifact. Every acceptance receipt in the AF-1 handoff has a
test here that fails when the property it names is broken.
"""

from __future__ import annotations

import dataclasses
import importlib
import json
from pathlib import Path

import pytest

import attune_forms
from attune_forms import canonical_fixtures as cf
from attune_forms import renderer_registry as rr
from attune_forms.bridge import collect_form_response, form_to_askuserquestion
from attune_forms.elicitation_schema import form_to_elicitation_schema
from attune_forms.headless import (
    HEADLESS_SCHEMA_VERSION,
    RESPONSE_CONTRACT_KEYS,
    workspace_to_headless,
)
from attune_forms.markdown_ingestion import markdown_to_answers
from attune_forms.markdown_surface import form_to_markdown
from attune_forms.widget import WIDGET_RESPONSE_MARKER, form_to_widget_html
from attune_forms.workspace import (
    WorkspaceView,
    WorkspaceViewId,
    collect_workspace_action,
    workspace_to_markdown,
    workspace_to_widget_html,
)

FORM = rr.RENDERER_REGISTRY[0]
WORKSPACE = rr.RENDERER_REGISTRY[1]


# --- registry structure -----------------------------------------------------


def test_registry_is_public_non_empty_and_valid() -> None:
    assert rr.RENDERER_REGISTRY
    rr.validate_registry()
    assert {r.record_id for r in rr.RENDERER_REGISTRY} == {"standalone-form", "generic-workspace"}
    assert {r.family for r in rr.RENDERER_REGISTRY} == {"form", "workspace"}


def test_every_target_resolves_and_is_a_package_export() -> None:
    for target in rr.iter_targets():
        assert callable(target.resolve())
        assert target.name in attune_forms.__all__, target.qualname
        assert getattr(attune_forms, target.name) is target.resolve()


def test_target_ids_are_unique_and_stable() -> None:
    ids = [t.target_id for t in rr.iter_targets()]
    assert len(ids) == len(set(ids))
    assert ids == [
        "form.rich",
        "form.portable",
        "form.headless",
        "form.askuserquestion",
        "workspace.rich",
        "workspace.portable",
        "workspace.headless",
    ]


def test_records_map_the_design_surfaces() -> None:
    assert FORM.target("rich").name == "form_to_widget_html"
    assert FORM.target("portable").name == "form_to_markdown"
    assert FORM.target("headless").name == "form_to_elicitation_schema"
    assert WORKSPACE.target("rich").name == "workspace_to_widget_html"
    assert WORKSPACE.target("portable").name == "workspace_to_markdown"
    assert WORKSPACE.target("headless").name == "workspace_to_headless"
    with pytest.raises(KeyError):
        WORKSPACE.target("host_native")


def test_af1_ships_no_route_active_host_native_target() -> None:
    host_native = [t for t in rr.iter_targets() if t.surface == "host_native"]
    assert [t.target_id for t in host_native] == ["form.askuserquestion"]
    (ask,) = host_native
    assert ask.status == "compatibility_only"
    assert ask.evidence_mode == "compatibility_projection"
    assert ask.profile_id == ""
    assert ask.compatibility_contract_id == rr.ASKUSERQUESTION_CONTRACT_ID
    assert not any(t.status == "route_active" for t in rr.iter_targets())


def _records_with(record: rr.RendererRecord, targets: tuple[rr.RendererTarget, ...]):
    return (dataclasses.replace(record, targets=targets),)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda t: t[:2],  # drop headless
            "generic-workspace: missing required headless target",
        ),
        (
            lambda t: (t[0], t[2]),  # drop portable
            "generic-workspace: missing required portable target",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="workspace.rich"),),
            "duplicate target id 'workspace.rich'",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="x", surface="hologram"),),
            "x: unknown surface 'hologram'",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="x", status="maybe"),),
            "x: unknown status 'maybe'",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="x", status="route_active"),),
            "x: only host_native targets carry a host status",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="x", surface="host_native"),),
            "x: host_native targets must be route_active or compatibility_only",
        ),
        (
            lambda t: t
            + (
                dataclasses.replace(
                    t[0],
                    target_id="x",
                    surface="host_native",
                    status="route_active",
                    evidence_mode="projection",
                ),
            ),
            "x: status route_active requires evidence_mode 'route_roundtrip', got 'projection'",
        ),
        (
            lambda t: t
            + (
                dataclasses.replace(
                    t[0],
                    target_id="x",
                    surface="host_native",
                    status="route_active",
                    evidence_mode="route_roundtrip",
                ),
            ),
            "x: route_active target must name its profile_id",
        ),
        (
            lambda t: t
            + (
                dataclasses.replace(
                    t[0],
                    target_id="x",
                    surface="host_native",
                    status="compatibility_only",
                    evidence_mode="compatibility_projection",
                    profile_id="live",
                ),
            ),
            "x: compatibility_only target cannot name a live profile",
        ),
        (
            lambda t: t
            + (
                dataclasses.replace(
                    t[0],
                    target_id="x",
                    surface="host_native",
                    status="compatibility_only",
                    evidence_mode="compatibility_projection",
                ),
            ),
            "x: compatibility_only target needs a contract id and a sha256 shape digest",
        ),
        (
            lambda t: t + (dataclasses.replace(t[0], target_id="x", name="workspace_to_nowhere"),),
            "attune_forms.workspace.workspace_to_nowhere does not resolve",
        ),
    ],
)
def test_validate_registry_names_each_problem(mutate, expected) -> None:
    with pytest.raises(rr.RegistryError) as info:
        rr.validate_registry(_records_with(WORKSPACE, mutate(WORKSPACE.targets)))
    assert any(p.startswith(expected) for p in info.value.problems), info.value.problems


def test_validate_registry_rejects_two_route_active_targets_per_profile() -> None:
    active = dataclasses.replace(
        WORKSPACE.targets[0],
        surface="host_native",
        status="route_active",
        evidence_mode="route_roundtrip",
        profile_id="p",
    )
    records = _records_with(
        WORKSPACE,
        WORKSPACE.targets
        + (
            dataclasses.replace(active, target_id="a"),
            dataclasses.replace(active, target_id="b"),
        ),
    )
    with pytest.raises(rr.RegistryError, match="more than one route_active target for profile 'p'"):
        rr.validate_registry(records)


def test_validate_registry_rejects_empty_duplicate_and_foreign_input() -> None:
    with pytest.raises(rr.RegistryError, match="registry is empty"):
        rr.validate_registry(())
    with pytest.raises(rr.RegistryError, match="duplicate record id"):
        rr.validate_registry((WORKSPACE, WORKSPACE))
    with pytest.raises(rr.RegistryError, match="not a projection input"):
        rr.validate_registry((dataclasses.replace(WORKSPACE, input_type="Widget"),))


# --- digests ----------------------------------------------------------------


def test_record_digest_binds_status_and_evidence_mode() -> None:
    base = rr.record_digest(FORM)
    ask = FORM.targets[3]
    flipped = dataclasses.replace(ask, status="route_active", evidence_mode="route_roundtrip")
    mutated = dataclasses.replace(FORM, targets=FORM.targets[:3] + (flipped,))
    assert rr.record_digest(mutated) != base
    only_mode = dataclasses.replace(
        FORM, targets=FORM.targets[:3] + (dataclasses.replace(ask, evidence_mode="x"),)
    )
    assert rr.record_digest(only_mode) != base
    assert rr.record_digest(FORM) == base  # deterministic


def test_registry_digest_binds_vocabulary_and_allowlist_rationale(monkeypatch) -> None:
    base = rr.registry_digest()
    monkeypatch.setattr(rr, "projection_output_types", rr.projection_output_types + ("bytes",))
    assert rr.registry_digest() != base
    monkeypatch.setattr(rr, "projection_output_types", rr.projection_output_types[:-1])
    assert rr.registry_digest() == base
    edited = (dataclasses.replace(rr.SWEEP_ALLOWLIST[0], rationale="edited"),) + rr.SWEEP_ALLOWLIST[
        1:
    ]
    monkeypatch.setattr(rr, "SWEEP_ALLOWLIST", edited)
    assert rr.registry_digest() != base


def test_implementation_digest_is_deterministic_for_every_target() -> None:
    digests = {t.target_id: rr.implementation_digest(t) for t in rr.iter_targets()}
    assert all(len(d) == 64 for d in digests.values())
    assert digests == {t.target_id: rr.implementation_digest(t) for t in rr.iter_targets()}
    assert len(set(digests.values())) == len(digests)


def _write_package(root: Path, files: dict[str, str]) -> Path:
    pkg = root / "attune_forms"
    pkg.mkdir(exist_ok=True)
    (pkg / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    for name, body in files.items():
        (pkg / f"{name}.py").write_text(body, encoding="utf-8")
    return pkg


def test_implementation_digest_follows_helpers_across_modules_and_ignores_unrelated(
    tmp_path,
) -> None:
    helpers = (
        "LIMIT = 3\n\ndef helper(x):\n    return x * LIMIT\n\ndef unrelated():\n    return 1\n"
    )
    renderer = (
        "from attune_forms.helpers import helper\n\ndef render(view):\n    return helper(view)\n"
    )
    pkg = _write_package(tmp_path, {"helpers": helpers, "renderer": renderer})
    target = rr.RendererTarget("t", "rich", "attune_forms.renderer", "render")
    rr._module_index.cache_clear()
    before = rr.implementation_digest(target, root=pkg)

    (pkg / "helpers.py").write_text(helpers.replace("return 1", "return 2"), encoding="utf-8")
    rr._module_index.cache_clear()
    assert (
        rr.implementation_digest(target, root=pkg) == before
    ), "unrelated symbol must not move the digest"

    (pkg / "helpers.py").write_text(helpers.replace("LIMIT = 3", "LIMIT = 4"), encoding="utf-8")
    rr._module_index.cache_clear()
    assert (
        rr.implementation_digest(target, root=pkg) != before
    ), "a transitive constant must move the digest"
    rr._module_index.cache_clear()


def test_implementation_digest_terminates_on_cycles_and_relative_imports(tmp_path) -> None:
    a = "from .b import pong\n\ndef ping(n):\n    return pong(n)\n"
    b = "from .a import ping\n\ndef pong(n):\n    return ping(n) if n else 0\n"
    pkg = _write_package(tmp_path, {"a": a, "b": b})
    rr._module_index.cache_clear()
    digest = rr.implementation_digest(
        rr.RendererTarget("t", "rich", "attune_forms.a", "ping"), root=pkg
    )
    assert len(digest) == 64
    rr._module_index.cache_clear()


# --- no-escape sweep --------------------------------------------------------


def test_sweep_is_clean_on_the_live_package() -> None:
    report = rr.sweep_production_renderers()
    assert report.ok, report.problems
    found = {c.qualname for c in report.candidates}
    assert {t.qualname for t in rr.iter_targets()} <= found
    assert all(c.reason == "typed" for c in report.candidates)


def test_sweep_allowlist_is_small_fully_qualified_and_rationale_bearing() -> None:
    assert len(rr.SWEEP_ALLOWLIST) <= 6
    for entry in rr.SWEEP_ALLOWLIST:
        assert entry.qualname.startswith("attune_forms.") and entry.qualname.count(".") >= 2
        assert len(entry.rationale) > 20


def test_sweep_fails_when_an_allowlist_entry_is_removed_or_stale_or_unexplained() -> None:
    dropped = rr.sweep_production_renderers(allowlist=rr.SWEEP_ALLOWLIST[1:])
    assert any(
        p.startswith(f"{rr.SWEEP_ALLOWLIST[0].qualname}: projection-shaped callable")
        for p in dropped.problems
    )
    stale = rr.sweep_production_renderers(
        allowlist=rr.SWEEP_ALLOWLIST
        + (rr.AllowlistEntry("attune_forms.bridge.nothing_here", "why"),)
    )
    assert (
        "attune_forms.bridge.nothing_here: allowlist entry matches no projection-shaped callable (stale)"
        in stale.problems
    )
    blank = rr.sweep_production_renderers(
        allowlist=(dataclasses.replace(rr.SWEEP_ALLOWLIST[0], rationale=" "),)
        + rr.SWEEP_ALLOWLIST[1:]
    )
    assert f"{rr.SWEEP_ALLOWLIST[0].qualname}: allowlist entry has no rationale" in blank.problems


def test_sweep_fails_when_a_registered_target_is_hidden_from_it() -> None:
    hidden = dataclasses.replace(
        WORKSPACE.targets[2], module="attune_forms.workspace", name="_secret"
    )
    records = (FORM, dataclasses.replace(WORKSPACE, targets=WORKSPACE.targets[:2] + (hidden,)))
    report = rr.sweep_production_renderers(records=records)
    assert (
        "attune_forms.workspace._secret: registry target was not found by the sweep (moved, renamed, or unannotated)"
        in report.problems
    )
    assert any(
        "workspace_to_headless: projection-shaped callable is neither" in p for p in report.problems
    )


def test_sweep_requires_registry_targets_to_be_exported() -> None:
    report = rr.sweep_production_renderers(
        exports=frozenset(attune_forms.__all__) - {"workspace_to_headless"}
    )
    assert (
        "attune_forms.headless.workspace_to_headless: registry target is not exported from attune_forms.__all__"
        in report.problems
    )


def test_sweep_rejects_double_registration() -> None:
    twice = (
        FORM,
        dataclasses.replace(
            WORKSPACE,
            targets=WORKSPACE.targets
            + (dataclasses.replace(WORKSPACE.targets[2], target_id="dup"),),
        ),
    )
    report = rr.sweep_production_renderers(records=twice)
    assert (
        "attune_forms.headless.workspace_to_headless: registered 2 times; must be exactly once"
        in report.problems
    )


def test_sweep_classifies_synthetic_package_exactly(tmp_path) -> None:
    pkg = _write_package(
        tmp_path,
        {
            "renderers": (
                "from typing import Any, Optional\n"
                "from attune_forms.models import FormSchema\n"
                "from attune_forms.workspace import WorkspaceView\n"
                "def form_to_thing(form: FormSchema) -> str: ...\n"  # naming + typed, unregistered
                "def project(view: WorkspaceView) -> dict[str, Any]: ...\n"  # typed, unregistered
                "def maybe(form: Optional[FormSchema]) -> str | None: ...\n"  # optional stripped -> typed
                "def untyped(form: FormSchema): ...\n"  # no return annotation -> fails closed
                "def union(form: FormSchema) -> str | bytes: ...\n"  # unresolved union -> fails closed
                "def predicate(form: FormSchema) -> bool: ...\n"  # not a projection type -> ignored
                "def _private(form: FormSchema) -> str: ...\n"  # private, unused elsewhere -> ignored
                "def _shared(form: FormSchema) -> str: ...\n"  # private but imported across modules
                "def workspace_to_x(view): ...\n"  # naming guardrail, no annotations -> fails closed
                "def other(x: int) -> str: ...\n"  # no projection input -> ignored
            ),
            "consumer": "from attune_forms.renderers import _shared\n",
        },
    )
    report = rr.sweep_production_renderers(root=pkg, records=(), allowlist=(), exports=frozenset())
    names = {c.qualname.rsplit(".", 1)[1]: c.reason for c in report.candidates}
    assert names == {
        "form_to_thing": "typed",
        "project": "typed",
        "maybe": "typed",
        "untyped": "unresolved",
        "union": "unresolved",
        "_shared": "typed",
        "workspace_to_x": "unresolved",
    }
    assert (
        "attune_forms.renderers.untyped: accepts FormSchema but has no return annotation (fails closed)"
        in report.problems
    )
    assert (
        "attune_forms.renderers.union: return annotation 'str | bytes' is an unresolved union (fails closed)"
        in report.problems
    )
    assert (
        "attune_forms.renderers.form_to_thing: projection-shaped callable is neither a registry target nor allowlisted"
        in report.problems
    )
    assert (
        "attune_forms.renderers._shared: projection-shaped callable is neither a registry target nor allowlisted"
        in report.problems
    )
    assert not any("predicate" in p or "_private" in p or ".other" in p for p in report.problems)


def test_sweep_naming_guardrail_catches_non_projection_return_type(tmp_path) -> None:
    pkg = _write_package(
        tmp_path,
        {
            "r": "from attune_forms.models import FormSchema\ndef form_to_bytes(form: FormSchema) -> bytes: ...\n"
        },
    )
    report = rr.sweep_production_renderers(root=pkg, records=(), allowlist=(), exports=frozenset())
    assert [c.reason for c in report.candidates] == ["naming"]
    assert report.problems == (
        "attune_forms.r.form_to_bytes: projection-shaped callable is neither a registry target nor allowlisted",
    )


# --- canonical fixtures through every target ---------------------------------


def _resolve_fixture(record: rr.RendererRecord):
    module, name = record.fixture.rsplit(".", 1)
    return getattr(importlib.import_module(module), name)()


def test_fixtures_ship_in_the_package_and_execute_through_every_target() -> None:
    form = _resolve_fixture(FORM)
    view = _resolve_fixture(WORKSPACE)
    assert form.form_id == "canonical-form"
    assert isinstance(view, WorkspaceView)
    kwargs = {
        "form.rich": {"instance_id": cf.CANONICAL_INSTANCE_ID},
        "workspace.rich": {"instance_id": cf.CANONICAL_INSTANCE_ID},
    }
    for record, fixture in ((FORM, form), (WORKSPACE, view)):
        for target in record.targets:
            first = target.resolve()(fixture, **kwargs.get(target.target_id, {}))
            second = target.resolve()(fixture, **kwargs.get(target.target_id, {}))
            if isinstance(first, str):
                assert cf.normalize(first) == cf.normalize(
                    second
                ), f"{target.target_id} is not deterministic after closed normalization"
            else:
                assert first == second, f"{target.target_id} is not deterministic"
                json.dumps(first)  # JSON-safe


def test_normalization_rules_are_closed_and_fixture_digest_is_stable() -> None:
    assert [r.name for r in cf.NORMALIZATION_RULES] == ["widget-telemetry-instance"]
    assert all(r.rationale for r in cf.NORMALIZATION_RULES)
    assert cf.normalize("a1b2") == "a1b2"
    token = 'instance_id: "' + "0" * 32 + '"'
    assert cf.normalize(token) == 'instance_id: "<telemetry-instance>"'
    assert cf.normalize('revision: "' + "0" * 32 + '"') != 'revision: "<telemetry-instance>"'
    assert cf.fixture_digest() == cf.fixture_digest()
    assert len(cf.fixture_digest()) == 64
    assert cf.digest({"a": 1}) == cf.digest({"a": 1})


# --- headless workspace projection ------------------------------------------


def test_headless_preserves_the_complete_view_and_binding() -> None:
    view = cf.canonical_workspace_view()
    binding = cf.canonical_binding()
    out = workspace_to_headless(view, binding)
    assert out["schema_version"] == HEADLESS_SCHEMA_VERSION
    assert out["view"]["id"] == "preview" and out["view"]["title"] == view.title
    assert out["view"]["summary"] == view.summary
    assert len(out["view"]["sections"]) == 2
    assert out["view"]["sections"][0]["blocks"][0]["items"][0] == {
        "label": "files",
        "value": "2",
        "detail": "",
        "status": "ok",
    }
    assert out["view"]["sections"][1]["blocks"][0]["kind"] == "code"
    apply, dismiss = out["view"]["actions"]
    assert apply["id"] == "apply" and apply["requires_explicit_choice"] is True
    assert apply["response_fields"][0]["id"] == "ruling"
    assert apply["response_fields"][0]["options"] == ["apply", "defer"]
    assert dismiss["response_fields"] == []
    assert out["view"]["form"] is None
    assert out["binding"] == binding.to_payload()
    contract = out["response_contract"]
    assert contract["marker"] == WIDGET_RESPONSE_MARKER
    assert contract["keys"] == list(RESPONSE_CONTRACT_KEYS)
    assert contract["actions"] == {
        "apply": {"confirmed": True, "responses": ["ruling"]},
        "dismiss": {"confirmed": False, "responses": []},
    }
    assert contract["binding_fields"] == [
        "workspace_id",
        "revision",
        "action_nonce",
        "contract_hash",
    ]
    assert json.loads(json.dumps(out)) == out
    assert workspace_to_headless(view)["binding"] is None
    assert workspace_to_headless(view)["response_contract"]["binding_fields"] == []


def test_headless_is_not_the_action_id_stub() -> None:
    out = workspace_to_headless(cf.canonical_workspace_view())
    assert out != ("apply", "dismiss")
    assert set(out["view"]) == {"id", "title", "summary", "sections", "actions", "form"}


def test_headless_form_view_carries_the_full_form_schema_and_refuses_a_binding() -> None:
    form = cf.canonical_form()
    view = WorkspaceView(
        id=(
            WorkspaceViewId.INTAKE
            if hasattr(WorkspaceViewId, "INTAKE")
            else list(WorkspaceViewId)[0]
        ),
        title="Intake",
        form=form,
        actions=(cf.canonical_workspace_view().actions[1],),
    )
    out = workspace_to_headless(view)
    assert out["view"]["form"]["form_id"] == "canonical-form"
    assert [q["id"] for q in out["view"]["form"]["questions"]] == ["approach", "scope", "notes"]
    assert out["view"]["form"]["questions"][0]["type"] == "decision"
    assert out["view"]["form"]["elicitation_schema"] == form_to_elicitation_schema(form)
    with pytest.raises(ValueError, match="not valid on a form view"):
        workspace_to_headless(view, cf.canonical_binding())


def test_headless_response_contract_round_trips_the_real_collector_like_the_widget() -> None:
    view = cf.canonical_workspace_view()
    binding = cf.canonical_binding()
    headless_payload = cf.canonical_workspace_response(view, "apply", binding, {"ruling": "apply"})
    widget_payload = {
        WIDGET_RESPONSE_MARKER: True,
        "title": view.title,
        "view": "preview",
        "action": "apply",
        "confirmed": True,
        "responses": {"ruling": "apply"},
        **binding.to_payload(),
    }
    assert headless_payload == widget_payload
    via_headless = collect_workspace_action(view, headless_payload, binding)
    via_widget = collect_workspace_action(view, widget_payload, binding)
    assert via_headless == via_widget
    assert via_headless.action == "apply" and via_headless.confirmed is True
    assert via_headless.responses_payload() == {"ruling": "apply"}
    assert via_headless.revision == 3

    markdown = workspace_to_markdown(view, binding=binding)
    skeleton = json.loads(markdown.split("```json")[1].split("```")[0])
    assert set(skeleton) <= set(RESPONSE_CONTRACT_KEYS)
    assert skeleton["action"] == "apply" and skeleton["workspace_id"] == binding.workspace_id

    html = workspace_to_widget_html(view, instance_id=cf.CANONICAL_INSTANCE_ID, binding=binding)
    assert binding.action_nonce in html and binding.contract_hash in html

    unbound = cf.canonical_workspace_response(view, "dismiss")
    assert collect_workspace_action(view, unbound).action == "dismiss"


# --- AskUserQuestion compatibility fixture ----------------------------------


def test_askuserquestion_shape_digest_is_pinned_to_the_canonical_output() -> None:
    out = form_to_askuserquestion(cf.canonical_form())
    assert cf.digest(out) == rr.ASKUSERQUESTION_SHAPE_DIGEST
    mutated = json.loads(json.dumps(out))
    mutated[0][0]["options"].append("Other")
    assert cf.digest(mutated) != rr.ASKUSERQUESTION_SHAPE_DIGEST


def test_askuserquestion_compatibility_answers_validate_like_portable_and_headless() -> None:
    form = cf.canonical_form()
    batches = form_to_askuserquestion(form)
    derived: dict[str, object] = {}
    for question in (q for batch in batches for q in batch):
        derived[question["question_id"]] = (
            question["options"][-1] if question["options"] else "none"
        )
    assert set(derived) == {"approach", "scope", "notes"}

    via_specialized = collect_form_response(form, dict(derived))
    reply = "\n".join(f"{k}: {v}" for k, v in derived.items())
    portable_answers, problems = markdown_to_answers(form, reply)
    assert problems == []
    via_portable = collect_form_response(form, portable_answers)
    schema = form_to_elicitation_schema(form)
    assert set(schema["properties"]) == set(derived)
    via_headless = collect_form_response(form, {k: derived[k] for k in schema["properties"]})

    assert via_specialized.responses == via_portable.responses == via_headless.responses
    assert via_specialized.responses["approach"] == "Build first"


def test_widget_and_markdown_form_projections_are_deterministic_under_the_canonical_instance() -> (
    None
):
    form = cf.canonical_form()
    html = form_to_widget_html(form, instance_id=cf.CANONICAL_INSTANCE_ID)
    again = form_to_widget_html(form, instance_id=cf.CANONICAL_INSTANCE_ID)
    assert html != again, "the widget mints a per-render telemetry token"
    assert cf.normalize(html) == cf.normalize(again)
    assert cf.CANONICAL_INSTANCE_ID in html
    assert form_to_markdown(form) == form_to_markdown(form)
