# tf_gnns reference workload

This example analyzes a pinned two-day slice of
[`mylonasc/tf_gnns`](https://github.com/mylonasc/tf_gnns) using the installed
Synirmos library. Its selection, scripts, recordings, and reports are owned by
this directory, not by the library. No `tf_gnns` Python package is required and
target repository code is never executed.

## Setup

Run these commands from the Synirmos project root:

```bash
uv sync --locked --dev
git clone https://github.com/mylonasc/tf_gnns.git data/tf_gnns
uv run pytest examples/tf_gnns/tests
```

The clone is an explicit network operation. Ensure it contains the anchor in
[`config.toml`](config.toml); the example does not fetch history implicitly.
The offline regression test uses only the checked-in GitHub evidence and does
not require this clone, credentials, or network access.

## Inspect the recorded evidence

```bash
uv run python examples/tf_gnns/runbook.py \
  --checkout data/tf_gnns \
  --cache examples/tf_gnns/tests/data \
  --output examples/tf_gnns/output/inspection
```

`--cache` is the directory containing `github/`. The runbook makes no GitHub
or LLM calls. Outputs are written to the supplied directory rather than
overwriting the historical artifacts.

## Evaluate and resume

```bash
uv run python examples/tf_gnns/evaluate.py \
  --checkout data/tf_gnns \
  --cache examples/tf_gnns/tests/data \
  --output examples/tf_gnns/output/evaluation
```

The default is offline and makes no model calls. Reuse the same output path to
resume checkpointed stages. For an explicitly online run, add `--online` and
use a writable cache such as `data/tf_gnns-cache` rather than changing the
checked-in recordings. `GITHUB_TOKEN` is optional for public data, subject to
rate limits. `--llm` opts into a hosted OpenAI request and requires the `openai`
extra (`uv sync --extra openai`), `OPENAI_API_KEY`, and consent to send the
selected public repository evidence to that provider.

`--config` can select a different configuration; it defaults to this example's
`config.toml`. Checkout, cache, and output paths are command-line inputs, never
hardcoded workspace paths.

## Historical artifacts

[`artifacts/`](artifacts/) contains the original report, SVG, evaluation, and
run manifest. These capture an earlier run and are not rewritten during tests;
their hashes, timestamps, configuration fingerprints, and software versions are
historical provenance, not descriptions of the current checkout. The
[original design](DESIGN.md) retains the initial workload and implementation
tracking references. This bounded workload does not establish full-history
coverage or general model accuracy.
