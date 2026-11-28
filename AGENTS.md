# Agent notes

## Branches

- Land all commits related to the ontology-driven KG feature (ONTO-KG,
  parent issue #1, slices #2–#8) on the `onto-kg-feature` branch, not on
  `main`. Open PRs against `main` from that branch when a slice is done.

## Verification

- Fast gates: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run pytest tests/ -q`.
- Full gates (also CI): `uv run python scripts/check.py` — lint, format,
  tests with a 90% coverage floor, example regressions, metrics, build,
  and installed-wheel smoke test.
- Notebooks under `examples/` are linted by ruff (code cells included);
  keep every imported name used and verify cells execute in order.
