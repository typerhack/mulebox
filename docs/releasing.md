# CI and releasing

For people who maintain mulebox. Versions, commits and the project log follow
[AGENTS.md](../AGENTS.md).

## CI

[.github/workflows/ci.yml](../.github/workflows/ci.yml) runs on every push to `main` and every
pull request: the file-size check and the test suite, on the minimum supported Python and on a
newer one, and a `web` job for the dashboard's front end (`npm ci`, lint with the check for
values typed in beside the design tokens, types, unit tests, build). `tests/test_ci_workflow.py` checks the rules below, and that the first Python in the
workflow is `requires-python` from `pyproject.toml`. Change the two together.

To check the workflow without pushing, lint it and run the same commands:

```sh
uvx --from actionlint-py actionlint .github/workflows/ci.yml
mulebox check
```

## The dashboard's front end

`web/` builds into `mulebox/dashboard/app/`, which is not in git: every way a package is made
builds it first.

- `mulebox setup` builds it on the laptop before it makes the wheel it sends, when the build is
  missing or older than a file under `web/` (`mulebox/client/webbuild.py`). Without `npm` it
  stops and names Node.js and npm; a build that is already fresh needs neither.
- The release workflow builds it before the wheel it publishes to PyPI.
- A wheel made by hand needs it built first: `(cd web && npm ci && npm run build)`.

Packages are pinned to exact versions in `web/package.json`, with `package-lock.json`
committed; a test holds that. To update one, change both with `npm install --save-exact`.

## Keeping CI safe in a public repository

- **GitHub-hosted machines only.** A workflow file that says so is not enough: a pull request
  runs the workflow from its own branch, so a fork can change `runs-on` to name a self-hosted
  runner and run anything on it. The only protection is that the repository has no such runner.
  Before a repository goes public, list its runners and remove every one:

  ```sh
  gh api repos/typerhack/mulebox/actions/runners --jq '.runners[].name'
  mulebox runner unregister --repo typerhack/mulebox
  ```

  Delete the `CI_RUNS_ON` repository variable too, if it exists: this workflow no longer reads it.
- **Ask before running a stranger's workflow.** In the repository's settings, under Actions,
  require approval for all external contributors.
- **`pull_request`, never `pull_request_target`.** The first gives a fork's code no secrets and
  a read-only token. The second runs with both.
- **Actions are pinned to a full commit**, with the version in a comment. A tag can move. To
  update one, look up the commit of the new release and change both.

## Versions and tags

`MAJOR.MINOR.PATCH`, in [VERSION](../VERSION) only. Every change bumps it in its own commit, with
an entry in [PROJECT_LOG.md](../PROJECT_LOG.md), so a commit's subject already names its version.

**A release is made when the user says so**, at whatever version `main` is on; no agent or
contributor releases on their own. Only the user declares a MAJOR version. The versions between
releases need no release step: they are on `main`, and a clone installs them.

## Making a release

Only after the user has said to release.

1. Everything for the release is merged, and `main` is green in CI.
2. `VERSION` is the version to release, with its log entry, committed with the subject starting
   with that version. For a new MAJOR, the user has declared it. Let CI pass on that commit.
3. Tag that commit and push the tag:

   ```sh
   git tag -a v1.1.0 -m "mulebox 1.1.0"
   git push origin v1.1.0
   ```

4. The tag starts [.github/workflows/release.yml](../.github/workflows/release.yml). It checks
   that the tag is `VERSION`, builds the dashboard's front end and the wheel, with the README's
   links pointed at the tag on GitHub (`tools/pypi_readme.py`, as PyPI has none of the files),
   installs the wheel and runs it, then publishes it to
   [PyPI](https://pypi.org/project/mulebox/). There is no token: PyPI trusts the workflow
   through trusted publishing, set on PyPI for `typerhack/mulebox`, `release.yml` and the
   repository environment `pypi`, and only the publish job may ask for that identity.
5. Install it from PyPI on a laptop, `uv tool install mulebox` or `uv tool upgrade mulebox`,
   run `mulebox setup` from it and a real project through it: [install.md,
   Upgrade](install.md#upgrade).

A version on PyPI cannot be uploaded twice, and a tag is never moved or deleted once pushed. If
a release is wrong, fix it in a new version. 1.0.0 was tagged before mulebox was on PyPI; 1.1.1
(2026-11-11) is the first release there.
