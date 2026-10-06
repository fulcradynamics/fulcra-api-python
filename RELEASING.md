# Releasing

Releases are automated. A release is a PR that bumps the version; merging it publishes `fulcra-api` to PyPI, tags `vX.Y.Z`, creates a GitHub release, and deploys the docs to GitHub Pages (<https://fulcradynamics.github.io/fulcra-api-python/>). To redeploy the docs without a release, run the `release` workflow by hand with "Deploy the docs" ticked.

## Cutting a release

```bash
uv run python scripts/release.py bump 0.1.45
```

This updates `pyproject.toml` and `uv.lock`. Open a PR with them.

On every PR, `.github/workflows/release-check.yml` (the `release-metadata` check) confirms that:
- a changed version goes up;
- `uv.lock` matches `pyproject.toml`;
- the package builds, and passes `twine check`, so PyPI will accept its description.

The `tests` workflow runs the suite on every Python version the package supports, and builds the docs in strict mode, so a broken docstring fails the PR.


