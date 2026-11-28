"""Execute shipped plain-Python notebook cells, offline, without a Jupyter extra."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
NOTEBOOKS = sorted((ROOT / "examples/onto_kg/notebooks").glob("*.ipynb"))


def test_expected_notebooks_exist():
    assert {"00_ontology_registry.ipynb", "D0_contracts.ipynb"} <= {path.name for path in NOTEBOOKS}


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda path: path.stem)
def test_notebook_code_cells_execute_in_order(notebook, tmp_path):
    code = """
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
notebook = json.loads(path.read_text(encoding="utf-8"))
namespace = {"__name__": "__main__"}
count = 0
for index, cell in enumerate(notebook["cells"], start=1):
    if cell["cell_type"] == "code":
        source = cell["source"]
        if isinstance(source, list):
            source = "".join(source)
        exec(compile(source, f"{path}:cell-{index}", "exec"), namespace)
        count += 1
assert count > 0, "a shipped notebook must exercise code"
print(f"Executed {count} cells: {path.name}")
"""
    subprocess.run(
        [sys.executable, "-c", code, str(notebook)],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        check=True,
        timeout=60,
    )
