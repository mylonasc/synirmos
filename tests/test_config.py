"""Configuration loading and fingerprinting."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from synirmos.core.config import config_fingerprint, load_config
from synirmos.core.models import (
    ContentSettings,
    GitHubSettings,
    GitSettings,
    OrchestrationSettings,
    RuntimeConfig,
)
from tests.support import TEST_CONFIG


def test_explicit_config_expresses_a_repository_selection():
    config = load_config(TEST_CONFIG)
    assert config.repository.full_name == "acme/project"
    assert config.repository.anchor == "a" * 40
    assert config.repository.window.start == datetime(2026, 9, 13, tzinfo=UTC)
    assert config.repository.window.end == datetime(2026, 9, 15, tzinfo=UTC)
    assert config.repository.allowed_work_items == (10, 11, 12)
    assert config.llm.enabled is False
    assert config.llm.privacy_consent is False


def test_sample_config_is_offline_capable_without_credentials():
    config = load_config(TEST_CONFIG)
    assert config.budgets.max_commits == 32
    assert config.offline is False
    assert config.cache_dir == "data/cache"
    assert "openai" in config.llm.provider


def test_custom_config_selects_another_repository(tmp_path):
    text = TEST_CONFIG.read_text()
    for original, replacement in (
        ('owner = "acme"', 'owner = "another-owner"'),
        ('name = "project"', 'name = "another-project"'),
        (
            'url = "https://github.com/acme/project.git"',
            'url = "https://github.com/another-owner/another-project.git"',
        ),
        (f'anchor = "{"a" * 40}"', f'anchor = "{"b" * 40}"'),
        ("allowed_work_items = [10, 11, 12]", "allowed_work_items = []"),
    ):
        text = text.replace(original, replacement)
    path = tmp_path / "my-repository.toml"
    path.write_text(text)

    config = load_config(path)

    assert config.repository.full_name == "another-owner/another-project"
    assert config.repository.url == "https://github.com/another-owner/another-project.git"
    assert config.repository.anchor == "b" * 40
    assert config.repository.allowed_work_items == ()


def test_git_settings_are_loaded_from_toml():
    config = load_config(TEST_CONFIG)
    assert config.git.max_depth == 256
    assert config.git.initial_fetch_depth == 64
    assert config.git.max_fetch_depth == 512
    assert config.git.skew_tolerance_seconds == 0
    assert config.git.rename_threshold == 50
    assert config.git.max_blob_bytes == 2097152


def test_git_settings_reject_inverted_fetch_depths():
    with pytest.raises(ValidationError):
        GitSettings(initial_fetch_depth=32, max_fetch_depth=16)
    with pytest.raises(ValidationError):
        GitSettings(max_depth=0)
    with pytest.raises(ValidationError):
        GitSettings(rename_threshold=101)


def test_content_settings_are_loaded_from_toml():
    config = load_config(TEST_CONFIG)
    assert config.content.max_file_bytes == 2097152
    assert config.content.max_sections == 500
    assert config.content.max_symbols == 1000
    assert config.content.max_imports == 500


def test_content_settings_reject_invalid_limits():
    with pytest.raises(ValidationError):
        ContentSettings(max_file_bytes=1)
    with pytest.raises(ValidationError):
        ContentSettings(max_sections=0)
    with pytest.raises(ValidationError):
        ContentSettings(max_symbols=10_001)
    with pytest.raises(ValidationError):
        ContentSettings(max_imports=0)


def test_github_settings_are_loaded_from_toml():
    config = load_config(TEST_CONFIG)
    assert config.github.api_url == "https://api.github.com"
    assert config.github.token_env == "GITHUB_TOKEN"
    assert config.github.per_page == 50
    assert config.github.max_pages == 20
    assert config.github.max_retries == 2
    assert config.github.max_response_bytes == 2097152
    assert config.github.required_scopes == ()
    assert config.github.user_agent == "synirmos/0.1"
    assert config.github.user_agent == GitHubSettings().user_agent


def test_github_settings_reject_invalid_limits():
    with pytest.raises(ValidationError):
        GitHubSettings(per_page=101)
    with pytest.raises(ValidationError):
        GitHubSettings(max_pages=0)
    with pytest.raises(ValidationError):
        GitHubSettings(max_retries=6)
    with pytest.raises(ValidationError):
        GitHubSettings(api_url="api.github.com")
    with pytest.raises(ValidationError):
        GitHubSettings(token_env="  ")


def test_orchestration_settings_are_loaded_from_toml():
    config = load_config(TEST_CONFIG)
    assert config.orchestration.journal_file == "data/journal/events.jsonl"
    assert config.orchestration.checkpoint_file == "data/journal/checkpoint.json"


def test_orchestration_settings_reject_blank_paths():
    with pytest.raises(ValidationError):
        OrchestrationSettings(journal_file="  ")
    with pytest.raises(ValidationError):
        OrchestrationSettings(checkpoint_file="")


def test_fingerprint_is_stable_and_sensitive(tmp_path):
    original = load_config(TEST_CONFIG)
    assert config_fingerprint(original) == config_fingerprint(load_config(TEST_CONFIG))
    assert len(config_fingerprint(original)) == 64

    changed = original.model_copy(
        update={"budgets": original.budgets.model_copy(update={"max_commits": 31})}
    )
    assert config_fingerprint(changed) != config_fingerprint(original)

    text = TEST_CONFIG.read_text().replace("max_commits = 32", "max_commits = 31")
    path = tmp_path / "changed.toml"
    path.write_text(text)
    assert config_fingerprint(load_config(path)) == config_fingerprint(changed)


def test_typed_sections_reject_unknown_keys():
    config = load_config(TEST_CONFIG)
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({**config.model_dump(), "unexpected": "value"})


def test_missing_required_config_key_fails(tmp_path):
    text = TEST_CONFIG.read_text().replace(f'anchor = "{"a" * 40}"\n', "")
    path = tmp_path / "missing-anchor.toml"
    path.write_text(text)
    with pytest.raises(ValidationError):
        load_config(path)


def test_configuration_requires_an_explicit_path():
    with pytest.raises(TypeError):
        load_config()


def test_missing_config_does_not_fall_back_to_a_sample(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.toml")
