"""Regenerate the syntax-forest spike page (#217, rung 4).

uv run --extra dev python labs/syntax_forest_spike/spike_stand.py /tmp/forest_stand.json
uv run python labs/syntax_forest_spike/build.py /tmp/forest_stand.json /tmp/forest_spike.html

Open the html directly or publish it as an artifact; three.js loads from cdnjs.
"""

import sys
from pathlib import Path

here = Path(__file__).resolve().parent
data = Path(sys.argv[1]).read_text()
out = Path(sys.argv[2])
out.write_text(
    (here / "template.html").read_text(encoding="utf-8").replace("__DATA__", data), encoding="utf-8"
)
print(f"wrote {out} ({out.stat().st_size // 1024} KB)")
