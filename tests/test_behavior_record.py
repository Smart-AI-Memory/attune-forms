"""The behavior record is the maintainer-side half of default-on.

attune-forms ships enabled, unpinned, with no feature flags, and a
plugin user cannot pin their way out of a change. So a behavior change
to promised surface has to be caught here, before release, rather than
by a consumer afterwards.

``test_the_stable_behavior_has_not_moved`` compares the live record with
``tests/data/stable-behavior.json`` and names the key that moved. Update
the file deliberately — the diff is the review artifact — and add a
``### Changed`` entry naming the observable difference.

Two tests keep the record honest in opposite directions:
``test_presentation_does_not_move_the_digest`` proves it ignores paint,
so it will not cry wolf on a CSS tweak and get muted;
``test_a_semantic_change_moves_the_digest`` proves it still notices
meaning.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from attune_forms.behavior_record import (
    behavior_digest,
    behavior_record,
    canonical_record_json,
)

RECORD_PATH = pathlib.Path(__file__).parent / "data" / "stable-behavior.json"

#: The behavior as ratified. Changing this means the promised behavior
#: changed; say so in the changelog.
RATIFIED_BEHAVIOR_DIGEST = "233be77436beb2f5c511e739e44ffc017b97cf3ebdc1eeedd585defa777d3b7e"


@pytest.fixture
def stored() -> dict:
    return json.loads(RECORD_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def live() -> dict:
    return behavior_record()


def _flatten(value, prefix=""):
    """Leaf paths, so a failure names the key that moved."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten(item, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _flatten(item, f"{prefix}[{index}]")
    else:
        yield prefix, value


def test_the_stable_behavior_has_not_moved(stored, live):
    stored_leaves = dict(_flatten(stored["stable"]))
    live_leaves = dict(_flatten(live["stable"]))

    moved = {
        key: (stored_leaves.get(key), live_leaves.get(key))
        for key in stored_leaves.keys() | live_leaves.keys()
        if stored_leaves.get(key) != live_leaves.get(key)
    }

    assert not moved, (
        "Promised behavior changed. If that was intended, regenerate "
        "tests/data/stable-behavior.json, update RATIFIED_BEHAVIOR_DIGEST, "
        f"and add a ### Changed entry. Moved (stored -> live): {moved}"
    )


def test_the_digest_matches_the_stored_record(stored):
    assert behavior_digest(stored) == RATIFIED_BEHAVIOR_DIGEST


def test_the_live_digest_matches_the_ratified_one():
    assert behavior_digest() == RATIFIED_BEHAVIOR_DIGEST


def test_the_stored_file_is_byte_identical_to_a_fresh_render(live):
    # Keeps the file a real diff artifact rather than drifting in
    # formatting from whatever wrote it last.
    assert RECORD_PATH.read_text(encoding="utf-8") == canonical_record_json(live) + "\n"


def test_the_record_is_deterministic():
    # No timestamp, uuid or response id may leak in; two renders in the
    # same process must agree exactly.
    assert behavior_record() == behavior_record()


def test_the_record_is_json_safe(live):
    assert json.loads(json.dumps(live)) == live


# --- the record ignores paint and notices meaning ------------------------


def test_presentation_does_not_move_the_digest(monkeypatch):
    # A CSS change is exactly the false alarm that gets a golden test
    # muted. docs/stability.md does not guarantee rendered bytes, and
    # the record must agree with the policy.
    import attune_forms.widget as widget

    before = behavior_digest()
    monkeypatch.setattr(widget, "_CSS_BASE", widget._CSS_BASE + "\n/* cosmetic */\n")

    assert behavior_digest() == before


def test_a_semantic_change_moves_the_digest(monkeypatch):
    import attune_forms.behavior_record as record

    before = behavior_digest()
    reference = dict(record.REFERENCE_FORM)
    dropped = list(reference["fields"])[-1]
    reference["fields"] = list(reference["fields"])[:-1]
    monkeypatch.setattr(record, "REFERENCE_FORM", reference)
    monkeypatch.setattr(
        record,
        "EXAMPLE_ANSWERS",
        {k: v for k, v in record.EXAMPLE_ANSWERS.items() if k != dropped["id"]},
    )

    assert behavior_digest() != before


def test_a_routing_flip_shows_up_in_the_provisional_record(monkeypatch):
    # select_form_surface changed its default in 0.15.0 with nothing to
    # catch it. This proves the record would have.
    import attune_forms.behavior_record as record

    before = behavior_record()["provisional"]["routing"]
    monkeypatch.setattr(record, "select_form_surface", lambda *a, **k: "widget")
    after = behavior_record()["provisional"]["routing"]

    assert before != after
    assert before["host_admissible_single_select"] == "ask"
    assert after["host_admissible_single_select"] == "widget"


def test_the_provisional_half_is_outside_the_digest(monkeypatch):
    # Provisional behavior is expected to move; folding it into the
    # digest would make the receipt meaningless.
    import attune_forms.behavior_record as record

    before = behavior_digest()
    monkeypatch.setattr(record, "select_form_surface", lambda *a, **k: "widget")

    assert behavior_digest() == before


# --- what the record covers ---------------------------------------------


def test_every_question_type_is_exercised(live):
    from attune_forms import QuestionType

    recorded = {entry["type"] for entry in live["stable"]["parse"]}

    assert recorded == {member.value for member in QuestionType}


def test_validation_attribution_is_recorded_per_field(live):
    corrupted = {k: v for k, v in live["stable"]["validate"].items() if k.startswith("corrupt.")}

    assert len(corrupted) >= 10
    for key, case in corrupted.items():
        field = key.split(".", 1)[1]
        if not case["accepted"]:
            assert case["fields"] == [field], key


def test_problem_prose_is_not_recorded(live):
    # The policy does not guarantee wording; recording it would make
    # every message tweak a behavior change.
    blob = json.dumps(live["stable"]["validate"])

    assert "is required" not in blob
    assert "not in options" not in blob
