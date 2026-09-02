"""Fix-first command workspace model and renderer receipts."""

from __future__ import annotations

import copy
import json
import pickle
import re
import shutil
import subprocess
from hashlib import sha256

import pytest

from attune_forms import (
    WorkspaceAction,
    WorkspaceActionBinding,
    WorkspaceActionIntent,
    WorkspaceActionResponse,
    WorkspaceBlock,
    WorkspaceBlockKind,
    WorkspaceItem,
    WorkspaceSection,
    WorkspaceValidationError,
    WorkspaceView,
    WorkspaceViewId,
    collect_workspace_action,
    form_from_dict,
    form_to_markdown,
    form_to_widget_html,
    workspace_action_contract,
    workspace_from_dict,
    workspace_to_markdown,
    workspace_to_widget_html,
)
from attune_forms.models import QuestionType
from attune_forms.tokens import SEMANTIC_TOKENS, token
from tests.fixtures.workspace_showcase import showcase_views

_CONTRACT_HASH = "a" * 64
_BINDING = WorkspaceActionBinding(
    workspace_id="fix-demo",
    revision=3,
    action_nonce="nonce_0123456789abcdef",
    contract_hash=_CONTRACT_HASH,
)


def _preview_definition() -> dict:
    return {
        "id": "preview",
        "title": "Fix preview",
        "summary": "Nothing has run.",
        "sections": [
            {
                "heading": "Contract",
                "tone": "neutral",
                "blocks": [
                    {
                        "kind": "key_value",
                        "items": [{"label": "Outcome", "value": "Repair parsing"}],
                    }
                ],
            }
        ],
        "actions": [
            {
                "id": "run_fix",
                "label": "Run Fix",
                "intent": "primary",
                "consequence": "Execute the previewed contract.",
                "requires_explicit_choice": True,
            },
            {"id": "edit_contract", "label": "Back to edit"},
        ],
    }


def _action_response_definition() -> dict:
    raw = _preview_definition()
    raw["actions"] = [
        {
            "id": "apply_rulings",
            "label": "Apply rulings",
            "intent": "primary",
            "consequence": "Apply every ruling in this batch atomically.",
            "requires_explicit_choice": True,
            "response_fields": [
                {
                    "id": "candidate_1",
                    "text": "First candidate",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                    "recommended": "promote",
                    "option_notes": {
                        "promote": "Advance this candidate.",
                        "decline": "Leave this candidate out.",
                    },
                },
                {
                    "id": "candidate_2",
                    "text": "Second candidate",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                },
            ],
        },
        {"id": "another_round", "label": "Another round"},
    ]
    return raw


def test_semantic_token_artifact_is_versioned_and_scalar_lookup_works() -> None:
    assert SEMANTIC_TOKENS["version"] == 1
    assert token("color.light.action") == "#004ac6"
    with pytest.raises(KeyError, match="mapping"):
        token("color.light")
    with pytest.raises(TypeError):
        SEMANTIC_TOKENS["color"]["light"]["action"] = "#f00"


def test_workspace_rejects_executable_shape_and_ambiguous_authority() -> None:
    with pytest.raises(ValueError, match="action id"):
        WorkspaceAction(id="alert(1)", label="Bad")
    with pytest.raises(ValueError, match="consequence"):
        WorkspaceAction(id="run", label="Run", requires_explicit_choice=True)
    with pytest.raises(ValueError, match="at most one primary"):
        WorkspaceView(
            id=WorkspaceViewId.PREVIEW,
            title="T",
            actions=(
                WorkspaceAction("a", "A", WorkspaceActionIntent.PRIMARY),
                WorkspaceAction("b", "B", WorkspaceActionIntent.PRIMARY),
            ),
        )
    with pytest.raises(ValueError, match="code block requires body"):
        WorkspaceBlock(WorkspaceBlockKind.CODE)
    with pytest.raises(ValueError, match="language identifier"):
        WorkspaceBlock(
            WorkspaceBlockKind.CODE,
            body="safe",
            language="text\n```\ninjected",
        )
    with pytest.raises(TypeError, match="block kind"):
        WorkspaceBlock("code", body="x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="section tone"):
        WorkspaceSection(blocks=(WorkspaceBlock(WorkspaceBlockKind.CODE, body="x"),), tone="x")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="action intent"):
        WorkspaceAction("run", "Run", intent="primary")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="view id"):
        WorkspaceView(id="preview", title="T")  # type: ignore[arg-type]


def test_workspace_rejects_invalid_direct_action_response_schemas() -> None:
    valid = form_from_dict(
        {"title": "T", "fields": [{"id": "x", "text": "X", "type": "text_input"}]}
    ).questions[0]
    with pytest.raises(TypeError, match="FormQuestion"):
        WorkspaceAction("run", "Run", response_fields=(object(),))  # type: ignore[arg-type]

    invalid_id = form_from_dict(
        {"title": "T", "fields": [{"id": "x", "text": "X", "type": "text_input"}]}
    ).questions[0]
    invalid_id.id = ""
    with pytest.raises(ValueError, match="non-empty"):
        WorkspaceAction("run", "Run", response_fields=(invalid_id,))
    with pytest.raises(ValueError, match="unique"):
        WorkspaceAction("run", "Run", response_fields=(valid, valid))

    form = form_from_dict(
        {"title": "T", "fields": [{"id": "y", "text": "Y", "type": "text_input"}]}
    )
    with pytest.raises(ValueError, match="cannot also declare"):
        WorkspaceView(
            WorkspaceViewId.INTAKE,
            "T",
            actions=(WorkspaceAction("run", "Run", response_fields=(valid,)),),
            form=form,
        )


def test_form_renderers_reject_ambiguous_response_envelopes() -> None:
    form = form_from_dict(
        {"title": "T", "fields": [{"id": "x", "text": "X", "type": "text_input"}]}
    )
    with pytest.raises(ValueError, match="submit_response_key"):
        form_to_widget_html(form, submit_response_key="Bad")
    with pytest.raises(ValueError, match="reserved"):
        form_to_widget_html(form, submit_context={"answers": "collision"})
    with pytest.raises(ValueError, match="keys"):
        form_to_widget_html(form, submit_context={"Bad": "value"})
    with pytest.raises(TypeError, match="values"):
        form_to_widget_html(form, submit_context={"extra": []})  # type: ignore[dict-item]

    with pytest.raises(ValueError, match="answer_key"):
        form_to_markdown(form, answer_key="Bad")
    with pytest.raises(ValueError, match="keys"):
        form_to_markdown(form, payload_context={"Bad": "value"})
    with pytest.raises(ValueError, match="reserved"):
        form_to_markdown(form, payload_context={"responses": {}})


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("workspace_id", "bad id", "workspace id"),
        ("revision", True, "revision"),
        ("revision", -1, "negative"),
        ("action_nonce", "short", "nonce"),
        ("contract_hash", "A" * 64, "contract hash"),
    ],
)
def test_workspace_action_binding_rejects_malformed_authority_context(
    field, value, message
) -> None:
    values = {
        "workspace_id": "fix-demo",
        "revision": 3,
        "action_nonce": "nonce_0123456789abcdef",
        "contract_hash": _CONTRACT_HASH,
    }
    values[field] = value
    with pytest.raises((TypeError, ValueError), match=message):
        WorkspaceActionBinding(**values)


def test_workspace_from_dict_casts_the_closed_document_grammar() -> None:
    view = workspace_from_dict(_preview_definition())
    assert view.id is WorkspaceViewId.PREVIEW
    assert view.sections[0].blocks[0].items[0].value == "Repair parsing"
    assert [action.id for action in view.actions] == ["run_fix", "edit_contract"]


def test_workspace_action_response_fields_are_validated_and_canonical() -> None:
    view = workspace_from_dict(_action_response_definition())
    action = view.actions[0]
    assert [question.id for question in action.response_fields] == [
        "candidate_1",
        "candidate_2",
    ]
    contract = workspace_action_contract(action)
    assert contract["id"] == "apply_rulings"
    assert [field["id"] for field in contract["response_fields"]] == [
        "candidate_1",
        "candidate_2",
    ]
    assert contract["response_fields"][0]["options"] == ["promote", "decline"]

    altered = _action_response_definition()
    altered["actions"][0]["response_fields"][0]["options"].reverse()
    altered_contract = workspace_action_contract(workspace_from_dict(altered).actions[0])

    reordered = _action_response_definition()
    reordered["actions"][0]["response_fields"].reverse()
    reordered_contract = workspace_action_contract(workspace_from_dict(reordered).actions[0])

    def digest(value) -> str:
        return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    assert digest(contract) != digest(altered_contract)
    assert digest(contract) != digest(reordered_contract)


def test_workspace_action_response_schema_is_an_immutable_snapshot() -> None:
    source = form_from_dict(
        {
            "title": "Action",
            "fields": [
                {
                    "id": "ruling",
                    "text": "Ruling",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                }
            ],
        }
    ).questions[0]
    action = WorkspaceAction("apply", "Apply", response_fields=(source,))
    view = WorkspaceView(
        id=WorkspaceViewId.PREVIEW,
        title="Review",
        actions=(action,),
    )
    contract = workspace_action_contract(action)

    source.options.append("defer")
    assert workspace_action_contract(action) == contract
    with pytest.raises(TypeError, match="immutable"):
        action.response_fields[0].options.append("defer")
    with pytest.raises(AttributeError, match="immutable"):
        action.response_fields[0].id = "changed"
    with pytest.raises(WorkspaceValidationError, match="not in options"):
        collect_workspace_action(
            view,
            {
                "__elicitation_response__": True,
                "title": "Review",
                "view": "preview",
                "action": "apply",
                "confirmed": True,
                "responses": {"ruling": "defer"},
            },
        )


@pytest.mark.parametrize(
    ("response_fields", "message"),
    [
        ([], "non-empty 'fields'"),
        ([{"id": "x", "text": "X", "type": "unknown"}], "invalid type"),
        (
            [
                {"id": "x", "text": "X", "type": "text_input"},
                {"id": "x", "text": "Again", "type": "text_input"},
            ],
            "duplicate id",
        ),
    ],
)
def test_workspace_rejects_malformed_action_response_fields(response_fields, message) -> None:
    raw = _action_response_definition()
    raw["actions"][0]["response_fields"] = response_fields
    with pytest.raises(WorkspaceValidationError, match=message):
        workspace_from_dict(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update({"callback": "run()"}),
        lambda raw: raw["actions"][0].update({"callback": "run()"}),
        lambda raw: raw["sections"][0]["blocks"][0].update({"html": "<script>"}),
    ],
)
def test_workspace_from_dict_rejects_every_unknown_definition_key(mutation) -> None:
    raw = _preview_definition()
    mutation(raw)
    with pytest.raises(WorkspaceValidationError, match="unknown definition key"):
        workspace_from_dict(raw)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "must be a mapping"),
        (
            {
                "id": "unknown",
                "title": 7,
                "summary": [],
                "sections": "bad",
                "actions": "bad",
                "form": "bad",
            },
            "must be one of",
        ),
        (
            {
                "id": "preview",
                "title": "T",
                "sections": [7, {"blocks": "bad"}],
                "actions": [7],
            },
            "must be a mapping",
        ),
        (
            {
                "id": "preview",
                "title": "T",
                "sections": [
                    {
                        "blocks": [
                            7,
                            {"kind": "code"},
                            {"kind": "timeline", "items": "bad"},
                            {"kind": "key_value", "items": [7]},
                        ]
                    }
                ],
            },
            "requires body",
        ),
        (
            {
                "id": "preview",
                "title": "T",
                "actions": [
                    {"id": "Bad", "label": "Bad"},
                    {
                        "id": "run",
                        "label": "Run",
                        "requires_explicit_choice": "yes",
                    },
                ],
            },
            "action id",
        ),
        (
            {
                "id": "intake",
                "title": "T",
                "form": {"title": "Broken", "fields": []},
            },
            "workspace form",
        ),
    ],
)
def test_workspace_from_dict_reports_malformed_nested_definitions(raw, message) -> None:
    with pytest.raises(WorkspaceValidationError, match=message):
        workspace_from_dict(raw)


def test_bound_renderers_emit_the_same_action_envelope() -> None:
    view = workspace_from_dict(_preview_definition())
    html = workspace_to_widget_html(view, instance_id="bound", binding=_BINDING)
    assert 'Object.assign(payload,{"workspace_id":"fix-demo","revision":3' in html
    assert f'"contract_hash":"{_CONTRACT_HASH}"' in html
    assert "confirmed:explicit" in html

    markdown = workspace_to_markdown(view, binding=_BINDING)
    skeleton = json.loads(markdown.split("```json")[-1].split("```")[0])
    assert skeleton == {
        "__elicitation_response__": True,
        "title": "Fix preview",
        "workspace_id": "fix-demo",
        "revision": 3,
        "view": "preview",
        "action": None,
        "action_nonce": "nonce_0123456789abcdef",
        "contract_hash": _CONTRACT_HASH,
        "confirmed": False,
    }


def test_action_response_renderers_share_the_bound_response_envelope() -> None:
    view = workspace_from_dict(_action_response_definition())
    html = workspace_to_widget_html(view, instance_id="batch", binding=_BINDING)
    assert 'data-workspace-action="apply_rulings"' in html
    assert 'payload["responses"] = answers' in html
    assert 'Object.assign(payload, {"confirmed":true,"workspace_id":"fix-demo"' in html
    assert "if(b.closest&&b.closest('form'))return" in html

    markdown = workspace_to_markdown(view, binding=_BINDING)
    skeletons = [
        json.loads(block) for block in re.findall(r"```json\n(.*?)\n```", markdown, flags=re.DOTALL)
    ]
    response_skeleton = next(
        payload for payload in skeletons if payload.get("action") == "apply_rulings"
    )
    assert response_skeleton == {
        "__elicitation_response__": True,
        "title": "Fix preview",
        "responses": {"candidate_1": "promote", "candidate_2": None},
        "confirmed": False,
        "workspace_id": "fix-demo",
        "revision": 3,
        "action_nonce": "nonce_0123456789abcdef",
        "contract_hash": _CONTRACT_HASH,
        "action": "apply_rulings",
        "view": "preview",
    }
    assert any(payload.get("action") is None for payload in skeletons)

    baked = re.search(r"Object\.assign\(payload, (\{[^;]+\})\);", html)
    assert baked is not None
    response = collect_workspace_action(
        view,
        {
            "__elicitation_response__": True,
            "title": view.title,
            "view": view.id.value,
            "action": "apply_rulings",
            "responses": {"candidate_1": "promote", "candidate_2": "decline"},
            **json.loads(baked.group(1)),
        },
        _BINDING,
    )
    assert response.confirmed is True
    assert response.responses_payload()["candidate_1"] == "promote"


def test_version_one_default_rendering_bytes_are_pinned() -> None:
    view = workspace_from_dict(_preview_definition())
    form = form_from_dict(
        {
            "title": "Compatibility intake",
            "description": "Stable defaults.",
            "fields": [{"id": "scope", "text": "Scope?", "type": "text_input"}],
        }
    )
    rendered = (
        workspace_to_widget_html(view, instance_id="compat-v1"),
        workspace_to_markdown(view),
        form_to_widget_html(form, instance_id="compat-form"),
        form_to_markdown(form),
    )
    assert tuple(sha256(value.encode()).hexdigest() for value in rendered) == (
        "c5d34815e48efc95b51b1f93f1639c0d57916f7f1e85261a7b7aa70714f2d736",
        "062d00bc6d2fb186498ac9927f730d3e5c0bc75c3e028d93a8076d1a45adaf42",
        "34dc6d7d9f742a8beef0fc86255ad7e74e6a36c8f692369d2481321a114b1b45",
        "4d19c915b09c4822bcffd1dfb9c81b74dd86e562d6090c5b223a329c5cb043e3",
    )


def test_collect_workspace_action_accepts_only_the_bound_rendered_action() -> None:
    view = workspace_from_dict(_preview_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "run_fix",
        "confirmed": True,
        **_BINDING.to_payload(),
    }
    response = collect_workspace_action(view, payload, _BINDING)
    assert response.action == "run_fix"
    assert response.revision == 3
    assert response.contract_hash == _CONTRACT_HASH


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("action_nonce", "nönce_0123456789abcdef", "nonce does not match"),
        ("contract_hash", "é" * 64, "contract hash does not match"),
    ],
)
def test_bound_workspace_action_rejects_non_ascii_authority_as_validation(
    field, value, message
) -> None:
    view = workspace_from_dict(_preview_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "run_fix",
        "confirmed": True,
        **_BINDING.to_payload(),
    }
    payload[field] = value
    with pytest.raises(WorkspaceValidationError, match=message):
        collect_workspace_action(view, payload, _BINDING)


def test_collect_workspace_action_returns_immutable_validated_responses() -> None:
    view = workspace_from_dict(_action_response_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "apply_rulings",
        "confirmed": True,
        "responses": {"candidate_1": "promote", "candidate_2": "decline"},
        **_BINDING.to_payload(),
    }
    response = collect_workspace_action(view, payload, _BINDING)
    assert response.responses_payload() == {
        "candidate_1": "promote",
        "candidate_2": "decline",
    }
    with pytest.raises(TypeError):
        response.responses["candidate_1"] = "decline"  # type: ignore[index]
    detached = response.responses_payload()
    detached["candidate_1"] = "decline"
    assert response.responses["candidate_1"] == "promote"

    nested = WorkspaceActionResponse(
        WorkspaceViewId.PREVIEW,
        "apply_rulings",
        True,
        responses={"ordered": ["a", "b"], "rulings": {"a": "promote"}},
    )
    assert nested.responses_payload() == {
        "ordered": ["a", "b"],
        "rulings": {"a": "promote"},
    }
    with pytest.raises(TypeError):
        nested.responses["rulings"]["a"] = "decline"  # type: ignore[index]
    nested_detached = nested.responses_payload()
    nested_detached["ordered"].append("c")
    assert nested.responses_payload()["ordered"] == ["a", "b"]


def test_workspace_actions_and_responses_preserve_hashability() -> None:
    action = workspace_from_dict(_action_response_definition()).actions[0]
    response = WorkspaceActionResponse(
        WorkspaceViewId.PREVIEW,
        "apply_rulings",
        True,
        responses={"ordered": ["a", "b"], "rulings": {"a": "promote"}},
    )
    assert isinstance(hash(action.response_fields[0].options), int)
    assert {action: "action"}[action] == "action"
    assert {response: "response"}[response] == "response"


def test_immutable_workspace_values_support_copy_and_pickle_round_trips() -> None:
    source_question = form_from_dict(
        {
            "title": "Ruling",
            "fields": [
                {
                    "id": "candidate_1",
                    "text": "Candidate 1",
                    "type": "single_select",
                    "options": ["promote", "decline"],
                    "option_notes": {"promote": "Advance."},
                }
            ],
        }
    ).questions[0]
    action = WorkspaceAction("apply_rulings", "Apply rulings", response_fields=(source_question,))
    response = WorkspaceActionResponse(
        WorkspaceViewId.PREVIEW,
        "apply_rulings",
        True,
        responses={"ordered": ["a", "b"], "rulings": {"a": "promote"}},
    )

    assert action.response_fields[0] == source_question
    assert action.response_fields[0] != object()
    assert copy.copy(action.response_fields[0]) is action.response_fields[0]
    assert copy.copy(action.response_fields[0].options) is action.response_fields[0].options
    assert copy.deepcopy(action.response_fields[0].options) is action.response_fields[0].options
    assert (
        copy.copy(action.response_fields[0].option_notes) is action.response_fields[0].option_notes
    )
    assert copy.copy(action) == action
    assert copy.deepcopy(action) == action
    assert copy.deepcopy(response) == response
    assert pickle.loads(pickle.dumps(action)) == action
    assert pickle.loads(pickle.dumps(response)) == response
    with pytest.raises(TypeError):
        pickle.loads(pickle.dumps(action)).response_fields[0].options.append("later")


def test_all_response_field_actions_render_without_plain_dispatch_script() -> None:
    definition = _action_response_definition()
    definition["actions"] = definition["actions"][:1]
    view = workspace_from_dict(definition)

    html = workspace_to_widget_html(view, instance_id="all-response", binding=_BINDING)
    markdown = workspace_to_markdown(view, binding=_BINDING)

    assert html.count('data-workspace-action="apply_rulings"') == 1
    assert "window.confirm(form.getAttribute('data-submit-consequence'))" in html
    assert "root.addEventListener('click'" not in html
    assert 'class="ae-ws-dispatch" role="status" aria-live="polite"' in html
    assert "### Apply rulings" in markdown
    assert "For an action without fields" not in markdown


@pytest.mark.parametrize(
    ("responses", "message"),
    [
        (None, "must be a mapping"),
        ({"candidate_1": "promote"}, "candidate_2.*required"),
        (
            {"candidate_1": "promote", "candidate_2": "decline", "foreign": "promote"},
            "unknown answer key 'foreign'",
        ),
        (
            {"candidate_1": "maybe", "candidate_2": "decline"},
            "candidate_1.*not in options",
        ),
    ],
)
def test_collect_workspace_action_rejects_malformed_response_batches(responses, message) -> None:
    view = workspace_from_dict(_action_response_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "apply_rulings",
        "confirmed": True,
        **_BINDING.to_payload(),
    }
    if responses is not None:
        payload["responses"] = responses
    with pytest.raises(WorkspaceValidationError, match=message):
        collect_workspace_action(view, payload, _BINDING)


def test_collect_workspace_action_selects_only_the_submitted_action_schema() -> None:
    view = workspace_from_dict(_action_response_definition())
    field_free_payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "another_round",
        "confirmed": False,
        **_BINDING.to_payload(),
    }
    response = collect_workspace_action(view, field_free_payload, _BINDING)
    assert response.responses_payload() == {}

    with pytest.raises(WorkspaceValidationError, match="does not declare response fields"):
        collect_workspace_action(
            view,
            {**field_free_payload, "responses": {}},
            _BINDING,
        )


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("action", "delete_repo", "not allowed"),
        ("view", "receipt", "view does not match"),
        ("revision", 2, "revision does not match"),
        ("action_nonce", "different_0123456789", "nonce does not match"),
        ("contract_hash", "b" * 64, "contract hash does not match"),
        ("confirmed", False, "explicit confirmation"),
    ],
)
def test_collect_workspace_action_rejects_stale_or_fabricated_context(key, value, message) -> None:
    view = workspace_from_dict(_preview_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "run_fix",
        "confirmed": True,
        **_BINDING.to_payload(),
    }
    payload[key] = value
    with pytest.raises(WorkspaceValidationError, match=message):
        collect_workspace_action(view, payload, _BINDING)


def test_collect_workspace_action_rejects_unknown_response_keys() -> None:
    view = workspace_from_dict(_preview_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "edit_contract",
        "confirmed": False,
        "callback": "run()",
    }
    with pytest.raises(WorkspaceValidationError, match="unknown key 'callback'"):
        collect_workspace_action(view, payload)


def test_collect_workspace_action_accepts_an_unbound_secondary_action() -> None:
    view = workspace_from_dict(_preview_definition())
    payload = {
        "__elicitation_response__": True,
        "title": view.title,
        "view": view.id.value,
        "action": "edit_contract",
        "confirmed": False,
    }
    response = collect_workspace_action(view, payload)
    assert response.action == "edit_contract"
    assert response.revision is None


def test_collect_workspace_action_rejects_unexpected_binding_and_bad_shape() -> None:
    view = workspace_from_dict(_preview_definition())
    with pytest.raises(WorkspaceValidationError, match="must be a mapping"):
        collect_workspace_action(view, "run_fix")

    payload = {
        "__elicitation_response__": False,
        "title": "different",
        "view": view.id.value,
        "action": None,
        "confirmed": "yes",
        **_BINDING.to_payload(),
    }
    with pytest.raises(WorkspaceValidationError) as exc:
        collect_workspace_action(view, payload)
    assert any(
        "requires __elicitation_response__=true" in problem for problem in exc.value.problems
    )
    assert any("unexpected binding" in problem for problem in exc.value.problems)


def test_form_workspace_rejects_action_binding_on_both_renderers() -> None:
    intake = showcase_views()[0]
    with pytest.raises(ValueError, match="not valid on a form view"):
        workspace_to_widget_html(intake, binding=_BINDING)
    with pytest.raises(ValueError, match="not valid on a form view"):
        workspace_to_markdown(intake, binding=_BINDING)


def test_form_view_requires_exactly_one_submit_action() -> None:
    form = form_from_dict(
        {"title": "T", "fields": [{"id": "x", "text": "X?", "type": "text_input"}]}
    )
    with pytest.raises(ValueError, match="exactly one"):
        WorkspaceView(id=WorkspaceViewId.INTAKE, title="T", form=form)


def test_showcase_covers_every_view_construct_and_display_block() -> None:
    views = showcase_views()
    assert {view.id for view in views} == set(WorkspaceViewId)
    intake = views[0]
    assert intake.form is not None
    assert {q.type for q in intake.form.questions} == set(QuestionType)
    kinds = {block.kind for view in views for section in view.sections for block in section.blocks}
    assert kinds == set(WorkspaceBlockKind)


def test_widget_form_action_uses_specific_label_and_stable_id() -> None:
    html = workspace_to_widget_html(showcase_views()[0], instance_id="showcase")
    assert 'data-workspace-view="intake"' in html
    assert ">Preview fix</button>" in html
    assert "payload.action = submitAction" in html
    assert 'var submitAction = "preview_fix"' in html
    assert 'var submitView = "intake"' in html
    assert 'data-form-title="Fix"' in html
    assert html.count("<h2") == 1
    assert "<h3>All Constructs Reference</h3>" not in html
    assert "@import" not in html


def test_public_widget_context_rejects_script_values() -> None:
    form = showcase_views()[0].form
    assert form is not None
    with pytest.raises(ValueError, match="stable lowercase identifier"):
        form_to_widget_html(form, submit_action="</script><img src=x>")


def test_widget_display_actions_post_only_stable_action_id() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="preview")
    assert 'data-workspace-action="run_fix" data-explicit="1"' in html
    assert 'data-workspace-action="edit_contract"' in html
    assert "action:b.getAttribute('data-workspace-action')" in html
    assert "typeof sendPrompt==='function'" in html
    assert "window.confirm" not in html
    assert "data-confirm-armed" in html
    assert "Click again to confirm." in html
    assert 'data-consequence="Execute the previewed contract."' in html
    assert "Workspace action submitted" in html
    assert "view:root.getAttribute('data-workspace-view')" in html
    assert 'role="status" aria-live="polite"' in html
    assert "x.disabled=true" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_widget_display_action_script_parses() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="parse")
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script is not None
    result = subprocess.run(
        ["node", "--check"],
        input=script.group(1),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_consequential_action_requires_two_clicks_and_other_action_disarms() -> None:
    html = workspace_to_widget_html(showcase_views()[1], instance_id="two-click")
    script = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert script is not None
    harness = f"""
const assert = require('node:assert/strict');
const listeners = {{}};
const sent = [];
function button(action, label, explicit, consequence) {{
  const attrs = {{'data-workspace-action': action}};
  if (explicit) attrs['data-explicit'] = '1';
  if (consequence) attrs['data-consequence'] = consequence;
  return {{
    textContent: label,
    disabled: false,
    getAttribute: function (name) {{ return attrs[name] || null; }},
    setAttribute: function (name, value) {{ attrs[name] = value; }},
    removeAttribute: function (name) {{ delete attrs[name]; }}
  }};
}}
const edit = button('edit_contract', 'Edit contract', false, null);
const run = button('run_fix', 'Run Fix', true, 'Execute the previewed contract.');
const status = {{textContent: ''}};
const root = {{
  addEventListener: function (name, callback) {{ listeners[name] = callback; }},
  contains: function () {{ return true; }},
  getAttribute: function (name) {{
    return name === 'data-workspace-title' ? 'Fix preview' : 'preview';
  }},
  querySelector: function () {{ return status; }},
  querySelectorAll: function (selector) {{
    if (selector === '[data-workspace-action]') return [edit, run];
    if (selector === '[data-explicit="1"][data-confirm-armed="1"]') {{
      return run.getAttribute('data-confirm-armed') === '1' ? [run] : [];
    }}
    return [];
  }}
}};
global.document = {{getElementById: function () {{ return root; }}}};
global.sendPrompt = function (value) {{ sent.push(value); }};
eval({json.dumps(script.group(1))});
function click(target) {{
  listeners.click({{
    target: {{closest: function () {{ return target; }}}}
  }});
}}
click(run);
assert.equal(sent.length, 0);
assert.equal(run.textContent, 'Confirm Run Fix');
assert.equal(run.getAttribute('data-confirm-armed'), '1');
assert.match(status.textContent, /Click again to confirm/);
click(run);
assert.equal(sent.length, 1);
assert.match(sent[0], /"action":"run_fix"/);
assert.match(sent[0], /"confirmed":true/);

run.disabled = false;
run.removeAttribute('data-confirm-armed');
run.textContent = 'Run Fix';
sent.length = 0;
click(run);
click(edit);
assert.equal(run.textContent, 'Run Fix');
assert.equal(run.getAttribute('data-confirm-armed'), null);
assert.equal(sent.length, 1);
assert.match(sent[0], /"action":"edit_contract"/);
assert.match(sent[0], /"confirmed":false/);
"""
    result = subprocess.run(
        ["node", "-e", harness],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_form_workspace_preserves_explicit_action_semantics() -> None:
    intake = showcase_views()[0]
    action = WorkspaceAction(
        "preview_fix",
        "Preview fix",
        WorkspaceActionIntent.PRIMARY,
        consequence="Build the deterministic preview.",
        requires_explicit_choice=True,
    )
    view = WorkspaceView(
        id=intake.id,
        title=intake.title,
        form=intake.form,
        actions=(action,),
    )
    html = workspace_to_widget_html(view, instance_id="explicit")
    assert "Build the deterministic preview." in html
    assert "window.confirm(form.getAttribute('data-submit-consequence'))" in html
    markdown = workspace_to_markdown(view)
    assert "**Explicit confirmation required:** Build the deterministic preview." in markdown
    assert "<script>alert" not in html


def test_workspace_markdown_preserves_sections_actions_and_form_state() -> None:
    intake_md = workspace_to_markdown(showcase_views()[0])
    skeleton = json.loads(intake_md.split("```json")[-1].split("```")[0])
    assert skeleton["action"] == "preview_fix"
    assert skeleton["view"] == "intake"
    assert set(skeleton["answers"])
    assert intake_md.count("## Fix") == 1
    preview_md = workspace_to_markdown(showcase_views()[1])
    assert "### Contract" in preview_md
    assert "`run_fix` — Run Fix" in preview_md
    assert "Execute the previewed contract" in preview_md
    action_skeleton = json.loads(preview_md.split("```json")[-1].split("```")[0])
    assert action_skeleton["view"] == "preview"
    assert action_skeleton["action"] is None


def test_workspace_markdown_escapes_evidence_table_cells() -> None:
    receipt = showcase_views()[-1]
    evidence = receipt.sections[0].blocks[-1]
    unsafe = WorkspaceBlock(
        WorkspaceBlockKind.EVIDENCE,
        items=(WorkspaceItem("lint | test", "a | b", detail="line 1\nline 2"),),
    )
    view = WorkspaceView(
        id=receipt.id,
        title=receipt.title,
        sections=(WorkspaceSection(blocks=(evidence, unsafe)),),
    )
    markdown = workspace_to_markdown(view)
    assert "lint \\| test" in markdown
    assert "a \\| b" in markdown
    assert "line 1<br>line 2" in markdown


def test_workspace_markdown_contains_multiline_author_text() -> None:
    view = WorkspaceView(
        id=WorkspaceViewId.EXECUTION,
        title="Run *fix*",
        sections=(
            WorkspaceSection(
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.TIMELINE,
                        items=(WorkspaceItem("Edit", "one\ntwo", "three\nfour"),),
                    ),
                ),
            ),
        ),
    )
    markdown = workspace_to_markdown(view)
    assert "Run \\*fix\\*" in markdown
    assert "one<br>two" in markdown
    assert "three<br>four" in markdown


def test_workspace_escapes_all_author_text() -> None:
    view = WorkspaceView(
        id=WorkspaceViewId.RECEIPT,
        title="<img src=x onerror=alert(1)>",
        sections=(
            WorkspaceSection(
                blocks=(
                    WorkspaceBlock(
                        WorkspaceBlockKind.KEY_VALUE,
                        items=(WorkspaceItem("<script>", "<b>unsafe</b>"),),
                    ),
                ),
            ),
        ),
        actions=(WorkspaceAction(id="inspect", label="Inspect"),),
    )
    html = workspace_to_widget_html(view, instance_id="escape")
    assert "<img" not in html and "<b>unsafe" not in html and "<script></script>" not in html
    assert "&lt;script&gt;" in html
    assert "</script><img" not in html
    assert "title:root.getAttribute('data-workspace-title')" in html


def test_workspace_instance_suffix_is_ascii_only() -> None:
    html = workspace_to_widget_html(showcase_views()[2], instance_id="fooｓ²")
    assert 'id="attune-workspace-foo"' in html
    hyphenated = workspace_to_widget_html(showcase_views()[2], instance_id="fix-1")
    compact = workspace_to_widget_html(showcase_views()[2], instance_id="fix1")
    assert 'id="attune-workspace-fix-1"' in hyphenated
    assert 'id="attune-workspace-fix1"' in compact
