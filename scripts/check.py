"""Run the same quality gates locally, in pre-push hooks, and in CI."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    commands = [
        ["ruff", "check", "."],
        ["ruff", "format", "--check", "."],
        [
            "pytest",
            "tests",
            "--cov=synirmos",
            "--cov-report=term-missing",
            "--cov-report=xml",
            "--cov-report=html",
        ],
        ["pytest", "examples/tf_gnns/tests"],
        [sys.executable, "scripts/metrics.py"],
        ["uv", "build"],
        [sys.executable, "scripts/check_package.py"],
    ]
    for command in commands:
        print(f"\n> {' '.join(command)}", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
