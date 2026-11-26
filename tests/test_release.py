"""Release decisions and artifact validation never contact or upload to PyPI."""

import io
import subprocess
import tarfile
import zipfile
from pathlib import Path

import pytest
import yaml
from packaging.version import InvalidVersion

from scripts import release


def project(version, name="synirmos"):
    return f'[project]\nname = "{name}"\nversion = "{version}"\n'.encode()


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("0.1.0", "0.1.1"),
        ("0.1.9", "0.2.0"),
        ("0.9.0", "1.0.0"),
        ("0.1.0", "0.2.0rc1"),
        ("0.2.0rc1", "0.2.0"),
    ],
)
def test_increasing_public_versions_are_release_candidates(old, new):
    assert release.release_version(project(new), project(old)) == new


@pytest.mark.parametrize(("old", "new"), [("0.1.0", "0.1.0"), ("1.0", "1.0.0")])
def test_unchanged_or_equivalent_versions_are_not_released(old, new):
    assert release.release_version(project(new), project(old)) is None


def test_initial_project_version_can_be_released():
    assert release.release_version(project("0.1.0"), None) == "0.1.0"


@pytest.mark.parametrize(
    ("version", "message"),
    [
        ("0.0.9", "downgrade"),
        ("0.2.0+local", "local version"),
        ("v0.2.0", "canonical version"),
    ],
)
def test_invalid_release_changes_fail_closed(version, message):
    with pytest.raises(ValueError, match=message):
        release.release_version(project(version), project("0.1.0"))


def test_invalid_version_and_wrong_project_are_rejected():
    with pytest.raises(InvalidVersion):
        release.release_version(project("not-a-version"), None)
    with pytest.raises(ValueError, match="only for synirmos"):
        release.release_version(project("1.0.0", name="another-project"), None)


def test_distribution_rename_does_not_publish_an_unchanged_version():
    assert release.release_version(project("0.1.0"), project("0.1.0", "repo-history")) is None


def git(root, *args):
    return (
        subprocess.check_output(["git", *args], cwd=root, env=release.git_environment())
        .decode()
        .strip()
    )


def test_hook_environment_cannot_redirect_temporary_git_repositories(tmp_path, monkeypatch):
    foreign = tmp_path / "foreign.git"
    foreign.mkdir()
    marker = foreign / "config"
    marker.write_text("[core]\n\tbare = true\n")
    monkeypatch.setenv("GIT_DIR", str(foreign))
    monkeypatch.setenv("GIT_WORK_TREE", str(tmp_path / "wrong-worktree"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(tmp_path / "foreign-index"))
    repository = tmp_path / "repo"
    repository.mkdir()
    git(repository, "init", "-q")
    metadata = project("0.1.0")
    (repository / "pyproject.toml").write_bytes(metadata)
    before = commit(repository, "isolated")
    assert release.previous_project(repository, before) == metadata
    assert (repository / ".git").is_dir()
    assert marker.read_text() == "[core]\n\tbare = true\n"
    assert not (tmp_path / "foreign-index").exists()


def commit(root, message):
    git(root, "add", ".")
    git(
        root,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        message,
    )
    return git(root, "rev-parse", "HEAD")


def test_detection_reads_the_entire_push_baseline_not_just_head_parent(tmp_path):
    git(tmp_path, "init", "-q")
    metadata = tmp_path / "pyproject.toml"
    metadata.write_bytes(project("0.1.0"))
    before = commit(tmp_path, "baseline")
    metadata.write_bytes(project("0.1.1"))
    commit(tmp_path, "version bump")
    (tmp_path / "notes.txt").write_text("another commit in the same push")
    commit(tmp_path, "notes")

    previous = release.previous_project(tmp_path, before)
    assert release.release_version(metadata.read_bytes(), previous) == "0.1.1"
    assert release.previous_project(tmp_path, "0" * 40) is None


def test_missing_project_metadata_is_distinct_from_missing_commit(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("initial repository")
    before = commit(tmp_path, "no project yet")
    assert release.previous_project(tmp_path, before) is None
    with pytest.raises(subprocess.CalledProcessError):
        release.previous_project(tmp_path, "1" * 40)
    with pytest.raises(ValueError, match="full Git commit ID"):
        release.previous_project(tmp_path, "HEAD~1")


def write_distributions(root, *, name="synirmos", version="0.2.0"):
    metadata = f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\n\n".encode()
    with zipfile.ZipFile(root / "synirmos-0.2.0-py3-none-any.whl", "w") as archive:
        archive.writestr("synirmos-0.2.0.dist-info/METADATA", metadata)
    with tarfile.open(root / "synirmos-0.2.0.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo("synirmos-0.2.0/PKG-INFO")
        info.size = len(metadata)
        archive.addfile(info, io.BytesIO(metadata))


def test_distribution_pair_must_have_the_expected_names_and_metadata(tmp_path):
    write_distributions(tmp_path)
    (tmp_path / ".gitignore").write_text("*")
    release.validate_artifacts(tmp_path, "0.2.0")
    (tmp_path / "old-release.whl").write_bytes(b"unrelated artifact")
    with pytest.raises(ValueError, match="exactly"):
        release.validate_artifacts(tmp_path, "0.2.0")


@pytest.mark.parametrize("changes", [{"name": "wrong-project"}, {"version": "0.3.0"}])
def test_mismatched_embedded_distribution_metadata_is_rejected(tmp_path, changes):
    write_distributions(tmp_path, **changes)
    with pytest.raises(ValueError, match="metadata"):
        release.validate_artifacts(tmp_path, "0.2.0")


def test_detector_outputs_skip_without_changing_project_files(tmp_path, monkeypatch, capsys):
    metadata = project("0.1.0")
    (tmp_path / "pyproject.toml").write_bytes(metadata)
    output = tmp_path / "github-output"
    output.write_text("other=value\n")
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "previous_project", lambda *args: metadata)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr("sys.argv", ["release.py", "detect", "--before", "a" * 40])
    release.main()
    assert "release=false\nversion=\n" in capsys.readouterr().out
    assert output.read_text() == "other=value\nrelease=false\nversion=\n"
    assert (tmp_path / "pyproject.toml").read_bytes() == metadata


def test_detector_outputs_new_version(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_bytes(project("0.2.0"))
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "previous_project", lambda *args: project("0.1.0"))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr("sys.argv", ["release.py", "detect", "--before", "a" * 40])
    release.main()
    assert capsys.readouterr().out == "release=true\nversion=0.2.0\n"


def workflow(name):
    root = Path(__file__).resolve().parents[1]
    # BaseLoader preserves the literal `on` key rather than YAML 1.1's boolean.
    return yaml.load((root / ".github/workflows" / name).read_text(), Loader=yaml.BaseLoader)


def test_release_workflow_requires_passing_ci_and_is_scoped_to_main():
    publish = workflow("publish-pypi.yml")
    assert set(publish["on"]) == {"push"}
    assert publish["on"]["push"]["branches"] == ["main"]
    assert publish["on"]["push"]["paths"] == ["pyproject.toml"]
    jobs = publish["jobs"]
    assert jobs["tests"]["needs"] == "version"
    assert jobs["tests"]["if"] == "needs.version.outputs.release == 'true'"
    assert jobs["tests"]["uses"] == "./.github/workflows/quality.yml"
    assert set(jobs["build"]["needs"]) == {"version", "tests"}
    assert any(step.get("run") == "uv build" for step in jobs["build"]["steps"])
    assert set(jobs["publish"]["needs"]) == {"version", "build"}
    assert "github.repository == 'mylonasc/synirmos'" in jobs["publish"]["if"]
    assert "github.ref == 'refs/heads/main'" in jobs["publish"]["if"]


def test_only_the_isolated_publishing_job_has_oidc_permission():
    publish = workflow("publish-pypi.yml")
    assert publish["permissions"] == {"contents": "read"}
    for name, job in publish["jobs"].items():
        assert (job.get("permissions", {}).get("id-token") == "write") == (name == "publish")
    steps = publish["jobs"]["publish"]["steps"]
    assert not any("run" in step or "checkout" in step.get("uses", "") for step in steps)
    assert steps[-1]["uses"] == "pypa/gh-action-pypi-publish@release/v1"
    assert "password" not in steps[-1]["with"]


def test_ci_is_reusable_and_covers_all_supported_python_versions():
    quality = workflow("quality.yml")
    assert {"push", "pull_request", "workflow_call"} <= set(quality["on"])
    assert quality["jobs"]["quality"]["strategy"]["matrix"]["python"] == ["3.11", "3.12", "3.13"]
