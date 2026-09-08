"""Which attune-forms is actually running.

Kept in its own module so ``__init__`` can resolve it alongside its
other imports rather than running code above them.

The MCP server passes this to ``Server(...)``. Without it the SDK
reports its own version under this package's name, which is how a host
came to be told attune-forms was "1.30.0".
"""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _distribution_version
from pathlib import Path


def _resolve_version() -> str:
    """The version of the code that is actually running.

    Installed metadata is the normal answer. It is NOT the answer in a
    source checkout: a different attune-forms may be pip-installed in
    the same interpreter, and reporting that one is precisely the
    version skew this exists to expose. So a sibling ``pyproject.toml``
    that declares this project wins, and the metadata is the fallback.
    """
    source = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            if re.search(r'^name\s*=\s*"attune-forms"', text, re.M):
                found = re.search(r'^version\s*=\s*"([^"]+)"', text, re.M)
                if found:
                    return found.group(1)
    except OSError:  # pragma: no cover - unreadable checkout
        pass
    try:
        return _distribution_version("attune-forms")
    except PackageNotFoundError:  # pragma: no cover - neither source nor installed
        return "0+unknown"


#: The running package's version. Reported in the MCP handshake, so a
#: host can tell which attune-forms it is actually talking to.
__version__ = _resolve_version()
