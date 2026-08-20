"""Tests for form_to_elicitation_schema — artifact → MCP requestedSchema.

Covers every QuestionType mapping plus title/description/default/required
threading. The lead v2 surface (D8) consumes this schema via
``ServerSession.elicit_form``.
"""

from __future__ import annotations

from attune_forms import form_from_dict, form_to_elicitation_schema


def _schema(field: dict) -> dict:
    form = form_from_dict({"title": "T", "fields": [field]})
    return form_to_elicitation_schema(form)


def _prop(field: dict) -> dict:
    return _schema(field)["properties"][field["id"]]


class TestTypeMapping:
    def test_single_select(self):
        p = _prop({"id": "g", "text": "Goal", "type": "single_select", "options": ["a", "b"]})
        assert p == {"title": "Goal", "type": "string", "enum": ["a", "b"]}

    def test_multi_select_required_sets_min_items(self):
        p = _prop({"id": "f", "text": "Focus", "type": "multi_select", "options": ["x", "y"]})
        assert p["type"] == "array"
        assert p["items"] == {"type": "string", "enum": ["x", "y"]}
        assert p["minItems"] == 1

    def test_multi_select_optional_no_min_items(self):
        p = _prop(
            {
                "id": "f",
                "text": "Focus",
                "type": "multi_select",
                "options": ["x", "y"],
                "required": False,
            }
        )
        assert "minItems" not in p

    def test_boolean(self):
        # A two-value string enum, not a JSON boolean: the validator
        # accepts only "Yes"/"No" (confirmation pass 2, 2026-08-20). A
        # `{"type": "boolean"}` projection was unanswerable both ways.
        p = _prop({"id": "b", "text": "Ship?", "type": "boolean"})
        assert p == {"title": "Ship?", "type": "string", "enum": ["Yes", "No"]}

    def test_number_with_bounds(self):
        p = _prop({"id": "n", "text": "Age", "type": "number", "minimum": 0, "maximum": 120})
        assert p == {"title": "Age", "type": "number", "minimum": 0, "maximum": 120}

    def test_number_without_bounds(self):
        p = _prop({"id": "n", "text": "Age", "type": "number"})
        assert p == {"title": "Age", "type": "number"}

    def test_date(self):
        p = _prop({"id": "d", "text": "When", "type": "date"})
        assert p == {"title": "When", "type": "string", "format": "date"}

    def test_textarea_with_max_length(self):
        p = _prop({"id": "t", "text": "Bio", "type": "textarea", "max_length": 280})
        assert p == {"title": "Bio", "type": "string", "maxLength": 280}

    def test_text_input_without_max_length(self):
        p = _prop({"id": "t", "text": "Name", "type": "text_input"})
        assert p == {"title": "Name", "type": "string"}


class TestSchemaShape:
    def test_help_text_becomes_description(self):
        p = _prop({"id": "n", "text": "Age", "type": "number", "help_text": "Years since birth"})
        assert p["description"] == "Years since birth"

    def test_default_threaded(self):
        p = _prop(
            {"id": "g", "text": "Goal", "type": "single_select", "options": ["a"], "default": "a"}
        )
        assert p["default"] == "a"

    def test_object_shape_and_required_list(self):
        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {"id": "req", "text": "R", "type": "text_input"},
                    {"id": "opt", "text": "O", "type": "text_input", "required": False},
                ],
            }
        )
        schema = form_to_elicitation_schema(form)
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"req", "opt"}
        assert schema["required"] == ["req"]


class TestConfirmationPass2:
    """Boolean mirror-drift (2026-08-20): the derived schema declared
    `{"type": "boolean"}` while the validator accepts only "Yes"/"No",
    making a boolean field unanswerable in both directions."""

    def test_boolean_answer_cross_validates_both_ways(self):
        import pytest

        jsonschema = pytest.importorskip("jsonschema")
        from attune_forms import collect_form_response

        form = form_from_dict(
            {"title": "T", "fields": [{"id": "b", "type": "boolean", "text": "Ship?"}]}
        )
        schema = form_to_elicitation_schema(form)
        # The only collectable answers now conform to the schema...
        for answer in ("Yes", "No"):
            jsonschema.validate({"b": answer}, schema)
            assert collect_form_response(form, {"b": answer}).responses["b"] == answer
        # ...and a raw JSON boolean, which the validator rejects, no
        # longer conforms to the schema either (no false contract).
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate({"b": True}, schema)

    def test_boolean_default_conforms_to_its_own_type(self):
        p = _prop({"id": "b", "type": "boolean", "text": "Ship?", "default": "Yes"})
        assert p["default"] in p["enum"]

    def test_directly_built_confirm_with_default_emits_no_schema_default(self):
        # `form_from_dict` rejects a `default` on confirm, but a
        # FormQuestion built DIRECTLY (dataclass constructor) bypasses
        # that check. The generic default projection must not emit it —
        # a schema `default` pre-selects approval in the client dialog,
        # defeating the two-way gate (checkpoint-2 promoted item).
        from attune_forms.models import FormQuestion, FormSchema, QuestionType

        form = FormSchema(
            title="T",
            description="",
            questions=[
                FormQuestion(
                    id="gate",
                    type=QuestionType.CONFIRM,
                    text="Approve?",
                    options=["Approve", "Abort"],
                    consequences=[{"label": "irreversible"}],
                    default="Approve",
                )
            ],
        )
        prop = form_to_elicitation_schema(form)["properties"]["gate"]
        assert "default" not in prop

    def test_directly_built_ranking_default_does_not_clobber_suggested(self):
        # A directly-built ranking's stray `default` must not become the
        # schema default (nor overwrite the legitimate `suggested`-derived
        # one). Defense in depth for the schema surface.
        from attune_forms.models import FormQuestion, FormSchema, QuestionType

        form = FormSchema(
            title="T",
            description="",
            questions=[
                FormQuestion(
                    id="rk",
                    type=QuestionType.RANKING,
                    text="Order",
                    options=["A", "B", "C"],
                    suggested=["C", "B", "A"],
                    default=["A", "B", "C"],
                )
            ],
        )
        prop = form_to_elicitation_schema(form)["properties"]["rk"]
        # The visible proposal (suggested) survives; the illegal `default`
        # never reaches the schema.
        assert prop["default"] == ["C", "B", "A"]

    def test_display_only_progress_is_skipped(self):
        # A display-only PROGRESS (no blocked options) projected to
        # `{"type": "string", "enum": []}` — an unanswerable property a
        # strict client could reject the whole schema over. It carries no
        # answer, so it must not appear in properties/required at all
        # (confirmation pass 2, 2026-08-20).
        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {
                        "id": "p",
                        "text": "Progress",
                        "type": "progress",
                        "required": False,
                        "progress_items": [
                            {"label": "A", "status": "done"},
                            {"label": "B", "status": "in_flight"},
                        ],
                    }
                ],
            }
        )
        schema = form_to_elicitation_schema(form)
        assert "p" not in schema["properties"]
        assert "p" not in schema["required"]

    def test_progress_with_blocked_options_still_projects(self):
        # A PROGRESS that carries blocked options is a real single-pick and
        # must keep projecting as a string enum.
        form = form_from_dict(
            {
                "title": "T",
                "fields": [
                    {
                        "id": "p",
                        "text": "Progress",
                        "type": "progress",
                        "options": ["B"],
                        "progress_items": [
                            {"label": "A", "status": "done"},
                            {"label": "B", "status": "blocked"},
                        ],
                    }
                ],
            }
        )
        schema = form_to_elicitation_schema(form)
        assert schema["properties"]["p"] == {
            "title": "Progress",
            "type": "string",
            "enum": ["B"],
        }
        assert schema["required"] == ["p"]
