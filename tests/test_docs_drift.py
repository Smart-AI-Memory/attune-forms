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
