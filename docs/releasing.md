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
- The release workflow builds it before the binary, which carries the package's files.
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

**Only MAJOR releases get a tag.** The user declares them; no agent or contributor bumps MAJOR on
their own. PATCH and MINOR versions need no release step.

## Making a MAJOR release

Only after the user has declared it.

1. Everything for the release is merged, and `main` is green in CI.
2. For the first public release, the open tasks of the roadmap's "Open-source readiness" are
   done: docs, the security review and the scan of the history for personal data.
3. Set `VERSION` (for example `1.0.0`), add the log entry, mark the roadmap and commit, with the
   subject starting with the new version. Let CI pass on that commit.
4. Tag that commit and push the tag:

   ```sh
   git tag -a v1.0.0 -m "mulebox 1.0.0"
   git push origin v1.0.0
   ```

5. The tag starts [.github/workflows/release.yml](../.github/workflows/release.yml), which builds
   the binaries for macOS on Apple silicon and Linux on x86-64 and puts them on a draft release.
   Add the wheel, write the notes from the log, and publish it:

   ```sh
   (cd web && npm ci && npm run build)    # the dashboard's front end goes into the wheel
   python -m pip wheel --no-deps -w dist .
   gh release upload v1.0.0 dist/mulebox-1.0.0-py3-none-any.whl
   gh release edit v1.0.0 --draft=false --notes-file notes.md
   ```

   To build a binary yourself: `pip install '.[binary]' && python tools/build_binary.py`. Update
   the version in the example in [install.md](install.md#2-install-on-the-laptop) with the release.

6. Install a binary on a laptop, run `mulebox setup` from it and run a real project through it:
   [install.md, Upgrade](install.md#upgrade).

A tag is never moved or deleted once pushed. If a release is wrong, fix it in a new version.
mulebox is not published to a package index; that is a decision for a later release.
