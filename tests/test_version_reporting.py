"""A running attune-forms must be able to say which one it is.

Before this, it could not. ``Server("attune-forms")`` passed no version,
and the MCP SDK fills that gap with *its own* version — so a host asking
which attune-forms it was talking to was told "1.30.0", the SDK's
number, under this package's name. The package had no ``__version__``
either, so there was no answer available from Python.

That matters here more than in most libraries. attune-forms ships
default-on and unpinned (``uvx --from 'attune-forms[mcp]'``, no
constraint), so several versions can be resolved on one machine at once
and the running one is whichever uvx last materialized. Undetectable
version skew turns every behavior question into a guess.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

import attune_forms
from attune_forms import __version__

PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_the_package_reports_a_version():
    assert isinstance(__version__, str)
    assert __version__
    assert __version__ != "0+unknown"


def test_a_source_checkout_reports_its_own_version_not_an_installed_one():
    # The regression that motivated this: a different attune-forms may be
    # pip-installed in the same interpreter. Reporting that one is the
    # exact skew this exists to expose.
    declared = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(), re.M)

    assert declared is not None
    assert __version__ == declared.group(1)


def test_the_version_is_not_the_mcp_sdk_version():
    mcp = pytest.importorskip("mcp")
    from importlib.metadata import version

    assert __version__ != version("mcp")
    assert not hasattr(mcp, "__version__") or __version__ != mcp.__version__


def test_the_server_advertises_the_package_version():
    pytest.importorskip("mcp")
    from attune_forms.mcp_server import _server

    assert _server.name == "attune-forms"
    assert _server.version == __version__


def test_the_version_is_not_part_of_the_tiered_public_surface():
    # A dunder is not API surface; keeping it out of __all__ keeps the
    # stability manifest from having to tier it.
    assert "__version__" not in attune_forms.__all__


def test_the_handshake_reports_the_package_version():
    pytest.importorskip("mcp")
    root = pathlib.Path(__file__).resolve().parents[1]
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {"elicitation": {}},
                "clientInfo": {"name": "version-probe", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
    ]
    stdin = "".join(json.dumps(message) + "\n" for message in messages)

    result = subprocess.run(
        [sys.executable, "-m", "attune_forms.mcp_server"],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=root,
        # Inherit the environment rather than replacing it: Windows
        # Python needs SystemRoot to seed hash randomization and to
        # initialize winsock, and a bare env fails before __main__ runs.
        env={**os.environ, "PYTHONPATH": str(root / "src")},
    )

    reported = None
    for line in result.stdout.splitlines():
        try:
            message = json.loads(line)
        except ValueError:
            continue
        if message.get("id") == 1:
            reported = message["result"]["serverInfo"]
    assert reported is not None, result.stderr
    assert reported["name"] == "attune-forms"
    assert reported["version"] == __version__
