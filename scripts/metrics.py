"""Report Python size, cyclomatic complexity, and maintainability (Radon)."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from radon.complexity import cc_rank, cc_visit
from radon.metrics import mi_visit
from radon.raw import analyze
from radon.visitors import Class

ROOT = Path(__file__).resolve().parents[1]


def measure(root: Path) -> dict:
    modules = {}
    functions = []
    package_root = root / "src/synirmos"
    for path in sorted(package_root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        blocks = cc_visit(source)
        # cc_visit already returns methods alongside their containing classes.
        # Excluding class aggregates avoids counting every method twice.
        blocks = [block for block in blocks if not isinstance(block, Class)]
        relative = path.relative_to(root).as_posix()
        entries = [
            {
                "module": relative,
                "name": block.fullname,
                "line": block.lineno,
                "complexity": block.complexity,
                "rank": cc_rank(block.complexity),
            }
            for block in blocks
        ]
        modules[relative] = {
            "source_lines": analyze(source).sloc,
            "maintainability_index": round(mi_visit(source, multi=True), 2),
            "functions": entries,
        }
        functions.extend(entries)
    return {
        "summary": {
            "modules": len(modules),
            "source_lines": sum(module["source_lines"] for module in modules.values()),
            "functions": len(functions),
            "average_complexity": round(mean(f["complexity"] for f in functions), 2),
            "maximum_complexity": max(f["complexity"] for f in functions),
            "average_maintainability": round(
                mean(module["maintainability_index"] for module in modules.values()), 2
            ),
            "minimum_maintainability": min(
                module["maintainability_index"] for module in modules.values()
            ),
        },
        "modules": modules,
        "highest_complexity": sorted(functions, key=lambda f: -f["complexity"])[:10],
    }


def main() -> None:
    result = measure(ROOT)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = ["# Python quality metrics", ""]
    summary.extend(
        f"- {key.replace('_', ' ')}: {value}" for key, value in result["summary"].items()
    )
    summary.extend(
        [
            "",
            "## Highest cyclomatic complexity",
            "",
            "| Function | Complexity | Rank |",
            "| --- | ---: | --- |",
        ]
    )
    summary.extend(
        f"| `{item['module']}:{item['name']}` | {item['complexity']} | {item['rank']} |"
        for item in result["highest_complexity"]
    )
    text = "\n".join(summary) + "\n"
    (reports / "metrics.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
