"""Docs drift catchers (architecture review finding F6, 2026-08-20).

The grammar is documented by hand in three places — README's "The
grammar" section, the plugin skill, and the CHANGELOG — and the
construct COUNT has already rotted once (commit 543a7a0 hand-corrected
"six"). The code-level drift catchers (round-trip, CSS families,
version sync) had no docs-level counterpart, so the next construct's
documentation depended entirely on the author remembering. These tests
are that counterpart: they read the real files and fail red when the
grammar and its documentation disagree.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from attune_forms import __all__ as _public_names
from attune_forms.mcp_server import tool_definitions
from attune_forms.models import QuestionType

_ROOT = Path(__file__).resolve().parent.parent
_README = (_ROOT / "README.md").read_text(encoding="utf-8")
_SKILL = (_ROOT / "plugin" / "skills" / "forms" / "SKILL.md").read_text(encoding="utf-8")

#: The plain controls; every other QuestionType member is a construct.
_CORE_TYPES = {
    QuestionType.TEXT_INPUT,
    QuestionType.SINGLE_SELECT,
    QuestionType.MULTI_SELECT,
    QuestionType.BOOLEAN,
    QuestionType.NUMBER,
    QuestionType.DATE,
    QuestionType.TEXTAREA,
}
_CONSTRUCTS = [t for t in QuestionType if t not in _CORE_TYPES]

_COUNT_WORDS = {
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
}


def test_readme_states_the_real_construct_count() -> None:
    """ "eight constructs" must track the enum — the count is a
    maintained invariant that has been hand-corrected before."""
    word = _COUNT_WORDS[len(_CONSTRUCTS)]
    assert f"{word} constructs" in _README


def test_readme_describes_every_construct() -> None:
    lower = _README.lower()
    for qtype in _CONSTRUCTS:
        name = qtype.value.replace("_", " ")
        assert name in lower, f"README's grammar section is missing {qtype.value!r}"


def test_skill_describes_every_question_type() -> None:
    lower = _SKILL.lower()
    for qtype in QuestionType:
        assert qtype.value in lower, f"SKILL.md is missing {qtype.value!r}"


def test_skill_names_only_real_mcp_tools() -> None:
    real = {tool.name for tool in tool_definitions()}
    named = set(re.findall(r"`(elicitation_[a-z_]+)`", _SKILL))
    ghosts = named - real
    assert not ghosts, f"SKILL.md names MCP tool(s) that do not exist: {sorted(ghosts)}"


def test_skill_names_only_real_library_functions() -> None:
    """A backticked transform name (`x_to_y` shape) in the skill must be
    a real public export or a real MCP tool — the skill is the agent's
    instruction sheet, and a renamed function leaves it instructing the
    impossible."""
    real = set(_public_names) | {tool.name for tool in tool_definitions()}
    named = {name for name in re.findall(r"`([a-z][a-z0-9_]*)\(?", _SKILL) if "_to_" in name}
    ghosts = named - real
    assert not ghosts, f"SKILL.md names library function(s) that do not exist: {sorted(ghosts)}"


def test_readme_test_count_claim_is_not_stale() -> None:
    """A bare number in prose rots silently; gate it like any other claim.

    The README carried "950+ tests" while the suite was past 1,400 — no
    gate covered it, because this module gated NAMES and construct
    counts, not free-standing numeric claims.

    The count is pytest's COLLECTED total, which is what a reader takes
    the claim to mean. Counting `def test_` instead understates badly
    (1,191 functions vs 1,464 collected) because parametrize expands —
    the first version of this gate made exactly that mistake and failed
    a truthful README.
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(_ROOT / "src")},
    )
    found = re.search(r"(\d+) tests? collected", proc.stdout)
    assert found, f"could not read a collected count: {proc.stdout[-300:]}"
    actual = int(found.group(1))
    claims = re.findall(r"([\d,]+)\+ tests", _README)

    assert claims, "the README makes no test-count claim"
    for raw in claims:
        claimed = int(raw.replace(",", ""))
        assert claimed <= actual, f"README claims {claimed}+ tests; only {actual} collected"
        assert actual - claimed < 500, (
            f"README claims {claimed}+ tests but {actual} are collected; "
            "the claim is stale — raise it"
        )


def test_no_changelog_version_repeats_a_section_heading() -> None:
    """Two `### Changed` blocks in one version is a merge artifact.

    Rebasing two branches that both appended to `[Unreleased]` produces
    exactly this, with no conflict markers and no failing test — it reads
    as a clean merge and renders as a duplicated section. Hit twice on
    2026-09-08 and fixed by hand both times.
    """
    changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    blocks = re.split(r"^## \[", changelog, flags=re.M)[1:]
    for block in blocks:
        version = block.split("]", 1)[0]
        headings = re.findall(r"^### (.+)$", block, flags=re.M)
        duplicates = sorted({h for h in headings if headings.count(h) > 1})
        assert not duplicates, f"[{version}] repeats section heading(s) {duplicates}"
