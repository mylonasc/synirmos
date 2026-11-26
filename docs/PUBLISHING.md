# Publishing Synirmos to PyPI

The trusted publisher is `.github/workflows/publish-pypi.yml` in
`mylonasc/synirmos`. It uses GitHub OIDC; do not add a PyPI password or API token
to repository secrets. This workflow does not specify a GitHub environment; the
PyPI publisher's environment field should therefore be left empty. If you later
require an environment such as `pypi`, configure it on both sides together.

## Release a version

From an up-to-date `main` branch (or a PR that will be merged into it):

First update `CHANGELOG.md`, moving the relevant unreleased notes into a
versioned section for the release.

```bash
uv version --bump patch       # or --bump minor / --bump major
uv lock
uv run python scripts/check.py
git add pyproject.toml uv.lock
git add CHANGELOG.md
git commit -m "Bump version for release"
git push origin main
```

If using branch protection, push the branch and merge the PR instead. Tags and
GitHub releases are not required. Commit the lockfile together with the version
change; locked CI fails if they disagree. Do not change a previously published
version's contents: make a new version bump instead.

## What CI does

1. Every push/PR runs `.github/workflows/quality.yml` on Python 3.11–3.13.
2. A push to `main` touching `pyproject.toml` also runs `publish-pypi.yml`.
   It compares `project.version` against the commit before the entire push, not
   just the previous individual commit. Unchanged versions skip publication;
   downgrades, local versions, and unexpected project names are rejected.
3. A version increase runs the same reusable quality matrix. Publication cannot
   proceed unless all test, coverage, lint, format, and package checks pass.
4. A separate job builds a fresh wheel and source distribution and checks their
   names and embedded project/version metadata. Exactly those artifacts are
   transferred to the publishing job.
5. The publishing job alone receives `id-token: write` and uploads through PyPI
   trusted publishing. It does not check out or run project code. Concurrent
   publishes of the same version are serialized; reruns skip files that PyPI
   already accepted. Different versions do not cancel one another's release jobs.

The publishing workflow does not run on pull requests, tags, other branches, or
fork repositories. A failed release can be retried with GitHub Actions' **Re-run
failed jobs**; no further version bump is needed if the version was not fully
published. A first push with no preceding project metadata treats the initial
version as a release candidate. Adding this workflow alone to an existing branch
does not publish an unchanged version.

The shared quality workflow also runs independently, so a version-bump push has
both ordinary CI and the explicit release-gating CI run. This intentional extra
run avoids publishing based on an unrelated or stale workflow result.

## Troubleshooting

- OIDC authorization failure: confirm the PyPI project/pending publisher is for
  `synirmos`, owner `mylonasc`, repository `synirmos`, workflow filename
  **`publish-pypi.yml`**, and no environment restriction unless one is also added
  to the job. A workflow display name is not the trusted-publisher filename.
- Version unchanged: bump `project.version`; modifying dependencies alone is not
  a release trigger.
- Missing pre-push commit: the detector fails rather than guessing a version
  after unavailable/force-pushed history. Restore access to that commit or make
  a new version-bump push from an available baseline.
- A published version is immutable: use a new version for fixes. `skip-existing`
  supports interrupted upload retries, not replacing artifacts on PyPI.

No version has been bumped or uploaded merely by adding this configuration.
