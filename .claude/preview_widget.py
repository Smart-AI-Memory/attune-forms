#!/usr/bin/env python3
"""Dev preview: render the reference form widget and serve it.

attune-forms has no HTTP dev server (attune-forms-mcp is stdio), so this
launcher gives .claude/launch.json something visual: the REFERENCE_FORM —
every control type — rendered by the real widget pipeline. Regenerates on
every start; serves stdlib-only on 127.0.0.1.
"""

import functools
import http.server
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from attune_forms import REFERENCE_FORM, form_from_dict, form_to_widget_html

# Default 8642 (8000/8001 are taken by agent-memory / attune-gui); the
# PORT env var wins so parallel sessions can each run their own preview.
PORT = int(os.environ.get("PORT", "8642"))

out = Path(tempfile.gettempdir()) / "attune_forms_widget_preview"
out.mkdir(exist_ok=True)
widget = form_to_widget_html(form_from_dict(REFERENCE_FORM))
(out / "index.html").write_text(
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1'>"
    "<title>attune-forms widget preview</title></head>"
    f"<body style='margin:2rem auto;max-width:720px;font-family:system-ui'>{widget}</body></html>",
    encoding="utf-8",
)

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
print(f"widget preview: http://localhost:{PORT} (reference form, regenerated at start)")
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler).serve_forever()
