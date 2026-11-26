"""Guard the package boundaries and compatibility of the modular layout."""

import ast
import importlib
from importlib.util import resolve_name
from pathlib import Path

import pytest

from scripts.metrics import measure

MODULES = {
    "analysis": "core",
    "budgets": "core",
    "config": "core",
    "events": "core",
    "ids": "core",
    "models": "core",
    "protocols": "core",
    "git": "sources",
    "github": "sources",
    "content": "processing",
    "enrichment": "processing",
    "labeling": "processing",
    "linking": "processing",
    "graph": "storage",
    "capabilities": "storage",
    "orchestration": "runtime",
    "worker": "runtime",
    "inspection": "reporting",
    "viz": "reporting",
    "evaluate": "reporting",
}
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("module", "package"), MODULES.items())
def test_domain_modules_use_the_synirmos_namespace(module, package):
    name = f"synirmos.{package}.{module}"
    assert importlib.import_module(name).__name__ == name


def test_library_has_no_example_paths_or_repository_defaults():
    for path in (ROOT / "src/synirmos").rglob("*.py"):
        source = path.read_text()
        assert "tf_gnns" not in source, path
        assert "/tmp/opencode" not in source, path
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = (
                    [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else [alias.name for alias in node.names]
                )
                assert not any(name.startswith("examples") for name in names), path


def test_core_does_not_import_outer_layers():
    for path in (ROOT / "src/synirmos/core").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.level < 2, path
                if node.module and node.module.startswith("synirmos."):
                    assert node.module.startswith("synirmos.core."), path


def test_implementations_use_domain_packages_not_flat_aliases():
    aliases = {f"synirmos.{module}" for module in MODULES}
    source_root = ROOT / "src"
    package_root = source_root / "synirmos"
    for path in package_root.rglob("*.py"):
        if path.parent == package_root:
            continue
        package = ".".join(path.parent.relative_to(source_root).parts)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level:
                    module = resolve_name("." * node.level + module, package)
                targets = {module, *(f"{module}.{alias.name}" for alias in node.names)}
            elif isinstance(node, ast.Import):
                targets = {alias.name for alias in node.names}
            else:
                continue
            assert not targets & aliases, path


def test_metrics_count_methods_once(tmp_path):
    module = tmp_path / "src/synirmos/core/example.py"
    module.parent.mkdir(parents=True)
    module.write_text("def top():\n    pass\nclass A:\n    def method(self):\n        pass\n")
    report = measure(tmp_path)
    assert report["summary"]["functions"] == 2
    assert report["summary"]["maximum_complexity"] == 1


def test_metrics_include_nested_integrations(tmp_path):
    module = tmp_path / "src/synirmos/platform_integrations/example/normalizer.py"
    module.parent.mkdir(parents=True)
    module.write_text("def normalize():\n    return ()\n")
    report = measure(tmp_path)
    assert report["summary"]["functions"] == 1
    assert str(module.relative_to(tmp_path)) in report["modules"]


def test_project_name_matches_the_default_uv_module_layout():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["project"]["name"] == "synirmos"
    assert project["build-system"]["build-backend"] == "uv_build"
    assert "module-name" not in project.get("tool", {}).get("uv", {}).get("build-backend", {})
    assert (ROOT / "src/synirmos/__init__.py").is_file()
    assert not (ROOT / "src/repo_history").exists()
