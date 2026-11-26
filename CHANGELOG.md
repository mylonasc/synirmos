# Changelog

Notable changes to Synirmos are recorded here. Unreleased changes are not yet
available on PyPI.

## [Unreleased]

### Added

- Python 3.11–3.13 CI with linting, formatting, coverage, complexity and
  maintainability reports, package builds, and installed-wheel checks.
- PyPI trusted publishing through `publish-pypi.yml`, gated on passing CI and
  version increases merged to `main`.
- Local pre-commit and pre-push quality hooks.
- Provider-neutral platform contracts and explicit GitLab/Jira placeholders.
- A detailed extensibility plan for remote-authoritative Git capture,
  interchangeable platform integrations, and multi-language parsers.

### Changed

- The distribution and Python import package are both named `synirmos`, using
  the standard `src/synirmos/` layout and uv's native build backend. Build the
  wheel and source distribution with `uv build`; no module-name overrides or
  package-name translation are required.
- Implementations are grouped into `core`, `sources`, `processing`, `storage`,
  `runtime`, `reporting`, and `platform_integrations` packages.
- The `tf_gnns` example owns its scripts, configuration, recordings, tests, and
  historical artifacts independently of the library and its distributions.

### Breaking changes

- Replace `repo_history` imports with canonical `synirmos` imports, for example
  `repo_history.git.GitHistory` becomes `synirmos.sources.git.GitHistory`.
  The old namespace and flat compatibility aliases are no longer installed.
- `load_config(path)` requires an explicit TOML configuration; the library no
  longer implicitly selects the `tf_gnns` example.

### Release status

- The configured project version remains `0.1.0`. This changelog does not claim
  that a PyPI release has been uploaded. Move these notes into a versioned
  section when preparing the first release.
