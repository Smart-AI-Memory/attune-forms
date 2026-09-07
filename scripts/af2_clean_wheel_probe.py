#!/usr/bin/env python
"""AF-2 clean-wheel probe: run against an INSTALLED wheel, never a checkout.

    uv build --wheel
    uv venv /tmp/af2-venv --python 3.12
    uv pip install --python /tmp/af2-venv/bin/python dist/attune_forms-*.whl
    cd /tmp && /tmp/af2-venv/bin/python <repo>/scripts/af2_clean_wheel_probe.py

Asserts the attune-ai host-surface-parity AF-2 acceptance receipts on the
installed artifact and prints the digests attune-ai Task 2 locks.
"""
import importlib.metadata
import json
import sys

import attune_forms
from attune_forms import (
    INTERACTION_PROFILES,
    HostQuestionBatch,
    HostQuestionProfile,
    InteractionProfile,
    QuestionAnswerBinding,
    canonical_host_question_form,
    canonical_host_question_response,
    form_to_host_question,
    host_question_admissibility,
    installed_profile,
)
from attune_forms import renderer_registry as rr
from attune_forms.canonical_fixtures import digest, fixture_digest

assert "site-packages" in attune_forms.__file__, attune_forms.__file__
version = importlib.metadata.version("attune-forms")
rr.validate_registry()
report = rr.sweep_production_renderers()
assert report.ok, report.problems
host = [t for t in rr.iter_targets() if t.status == "route_active"]
assert [t.target_id for t in host] == ["form.host_question"], host
(target,) = host
profile = installed_profile(target.profile_id)
assert isinstance(profile, InteractionProfile) and profile.id == target.profile_id
assert isinstance(profile.host_question, HostQuestionProfile)
assert sum(1 for p in INTERACTION_PROFILES if p.id == profile.id) == 1
form = canonical_host_question_form()
verdict = host_question_admissibility(form, profile)
assert verdict.admissible, verdict.problems
batch = form_to_host_question(form, profile)
assert isinstance(batch, HostQuestionBatch)
assert all(isinstance(b, QuestionAnswerBinding) for b in batch.answer_bindings)
record = rr.RENDERER_REGISTRY[0]
assert batch == rr.render_fixture(record, target)
raw = canonical_host_question_response(batch, profile)
print(
    json.dumps(
        {
            "attune_forms": version,
            "file": attune_forms.__file__,
            "python": sys.version.split()[0],
            "route_active_target": target.target_id,
            "profile_id": profile.id,
            "facet_digest": digest(profile.host_question.serialize()),
            "record_digest": rr.record_digest(record),
            "registry_digest": rr.registry_digest(),
            "implementation_digest": rr.implementation_digest(target),
            "fixture_digest": fixture_digest(),
            "questions": len(batch.payload["questions"]),
            "raw_keys": sorted(raw),
        },
        indent=1,
    )
)
