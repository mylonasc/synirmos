"""Detect explicit version bumps and validate distributions before OIDC publishing.

This helper never contacts PyPI, changes a version, creates a tag, or uploads
anything. Only the isolated publish job has permission to request a PyPI token.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PROJECT_NAME = "synirmos"


def git_environment() -> dict[str, str]:
    """Do not let a caller's hook/worktree environment redirect Git commands."""
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def release_version(current: bytes, previous: bytes | None) -> str | None:
    """Return a new public version, skip unchanged versions, reject downgrades."""
    project = tomllib.loads(current.decode())["project"]
    if canonicalize_name(project["name"]) != PROJECT_NAME:
        raise ValueError(f"this publisher is configured only for {PROJECT_NAME}")
    version = Version(project["version"])
    if version.local is not None:
        raise ValueError("PyPI releases cannot use local version identifiers")
    if str(version) != project["version"]:
        raise ValueError(f"use the canonical version spelling: {version}")
    if previous is not None:
        old = Version(tomllib.loads(previous.decode())["project"]["version"])
        if version < old:
            raise ValueError(f"refusing a version downgrade: {old} -> {version}")
        if version == old:
            return None
    return str(version)


def previous_project(root: Path, before: str) -> bytes | None:
    """Read the pre-push version; fail closed if its commit is unavailable."""
    if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", before):
        raise ValueError("before must be a full Git commit ID")
    if set(before) == {"0"}:
        return None  # First push: the initial project version is a release candidate.
    env = git_environment()
    subprocess.run(["git", "cat-file", "-e", f"{before}^{{commit}}"], cwd=root, env=env, check=True)
    paths = subprocess.check_output(
        ["git", "ls-tree", "--name-only", before, "--", "pyproject.toml"], cwd=root, env=env
    )
    if not paths.strip():
        return None
    return subprocess.check_output(["git", "show", f"{before}:pyproject.toml"], cwd=root, env=env)


def validate_artifacts(directory: Path, version: str) -> None:
    """Require exactly the intended wheel/sdist and matching embedded metadata."""
    expected = {
        f"{PROJECT_NAME}-{version}-py3-none-any.whl",
        f"{PROJECT_NAME}-{version}.tar.gz",
    }
    # `uv build` creates this harmless marker in its output directory.
    files = {
        path.name
        for path in directory.iterdir()
        if not (path.name == ".gitignore" and path.is_file())
    }
    if files != expected:
        raise ValueError("release directory must contain exactly the expected wheel and sdist")
    with zipfile.ZipFile(directory / f"{PROJECT_NAME}-{version}-py3-none-any.whl") as archive:
        raw_wheel = archive.read(f"{PROJECT_NAME}-{version}.dist-info/METADATA")
    with tarfile.open(directory / f"{PROJECT_NAME}-{version}.tar.gz") as archive:
        member = archive.extractfile(f"{PROJECT_NAME}-{version}/PKG-INFO")
        if member is None:
            raise ValueError("source distribution is missing PKG-INFO")
        with member:
            raw_sdist = member.read()
    for raw in (raw_wheel, raw_sdist):
        metadata = BytesParser().parsebytes(raw)
        if metadata["Name"] != PROJECT_NAME or metadata["Version"] != version:
            raise ValueError("distribution metadata does not match the intended project/version")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    detect = commands.add_parser("detect", help="compare the version against the pre-push commit")
    detect.add_argument("--before", required=True)
    artifacts = commands.add_parser("artifacts", help="validate release artifact metadata")
    artifacts.add_argument("--version", required=True)
    args = parser.parse_args()
    if args.command == "artifacts":
        validate_artifacts(ROOT / "dist", args.version)
        print(f"Validated {PROJECT_NAME} {args.version} distributions")
        return
    version = release_version(
        (ROOT / "pyproject.toml").read_bytes(), previous_project(ROOT, args.before)
    )
    output = f"release={'true' if version else 'false'}\nversion={version or ''}\n"
    print(output, end="")
    if destination := os.environ.get("GITHUB_OUTPUT"):
        with Path(destination).open("a", encoding="utf-8") as handle:
            handle.write(output)


if __name__ == "__main__":
    main()
