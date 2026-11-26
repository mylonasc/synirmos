"""Smoke-test an installed wheel outside the source tree, without examples."""

import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    wheel = ROOT / f"dist/synirmos-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel) as archive:
        assert not any("examples/" in name or "tf_gnns" in name for name in archive.namelist())
        assert not any(name.startswith("repo_history/") for name in archive.namelist())
    with tarfile.open(ROOT / f"dist/synirmos-{version}.tar.gz") as archive:
        assert not any("/examples/" in name or "tf_gnns" in name for name in archive.getnames())
        assert f"synirmos-{version}/CHANGELOG.md" in archive.getnames()
    code = '''
from pathlib import Path
from importlib.metadata import version
from importlib.util import find_spec
import synirmos
from synirmos import load_config
from synirmos.core.models import RuntimeConfig
from synirmos.sources.git import GitHistory
assert version("synirmos") == EXPECTED_VERSION
assert "site-packages" in synirmos.__file__
assert find_spec("repo_history") is None
config = Path("repository.toml")
config.write_text("""[repository]
owner = "acme"
name = "project"
url = "https://github.com/acme/project"
anchor = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
[repository.window]
start = "2026-01-01T00:00:00Z"
end = "2026-01-02T00:00:00Z"
""")
assert isinstance(load_config(config), RuntimeConfig)
assert load_config(config).repository.full_name == "acme/project"
print("Installed-wheel smoke test passed without source checkout or examples.")
'''
    code = code.replace("EXPECTED_VERSION", repr(version))
    environ = os.environ.copy()
    environ.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="synirmos-wheel-") as directory:
        subprocess.run(
            [
                "uv",
                "run",
                "--isolated",
                "--no-project",
                "--python",
                sys.executable,
                "--with",
                str(wheel),
                "python",
                "-c",
                code,
            ],
            cwd=directory,
            env=environ,
            check=True,
        )


if __name__ == "__main__":
    main()
