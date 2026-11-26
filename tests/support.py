"""Explicit synthetic configuration shared by library tests, never examples."""

from pathlib import Path

TEST_CONFIG = Path(__file__).parent / "fixtures" / "repository.toml"
