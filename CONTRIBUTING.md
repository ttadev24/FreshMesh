# Contributing to FreshMesh

Thank you for helping improve FreshMesh. Contributions can include bug fixes, documentation, translations, accessibility improvements, tests, and reproducible research. Follow our [Code of Conduct](CODE_OF_CONDUCT.md) in project spaces.

## Before you start

Search [existing issues](https://github.com/ttadev24/FreshMesh/issues) and pull requests. Open an issue before a substantial architectural change or a new experiment so the scope and evaluation criteria can be discussed. Small, focused fixes can go straight to a pull request.

For vulnerabilities, use [SECURITY.md](SECURITY.md) instead of a public bug report. Usage questions belong in an issue with a clear question and sanitized context; see [SUPPORT.md](SUPPORT.md).

## Set up a development environment

Fork the repository, clone your fork with submodules, and create a descriptive branch:

```bash
git clone --recurse-submodules https://github.com/YOUR_USERNAME/FreshMesh.git
cd FreshMesh
git switch -c docs/describe-your-change
uv sync --locked
(cd web && npm ci)
scripts/bootstrap.sh --skip-fl
```

See the [quick start](README.md#quick-start) for the solver and application servers, and [configuration](docs/configuration.md) for local credentials. Use Python 3.12+ and Node.js 22.13+.

The bootstrap command regenerates demo data. Use a disposable checkout or a separate data directory when preserving local decisions matters. Generated FL experiments also write to `docs/experiments/`; inspect your diff before committing.

## Working conventions

- Keep each pull request focused on one problem and explain the resulting behavior.
- Match existing Python and TypeScript conventions. Use Ruff for Python and the repository's ESLint/typecheck commands for the web app.
- Read applicable `AGENTS.md` instructions, including `web/AGENTS.md` before changing the web application.
- Keep shared business logic in the service/domain layers so the CLI, API, and assistant use consistent calculations.
- Preserve chain/store authorization, the draft approval boundary, audit records, and provenance labels.
- Never present generated transactions or AI estimates as measured business data.
- Avoid unrelated formatting, generated databases, caches, credentials, and dependency upgrades in a focused fix.
- Keep `uv.lock` or `web/package-lock.json` consistent when dependencies change. Explain changes to the solver submodule pin.
- Write new community documentation in English. Preserve Vietnamese user-facing copy and provide translations deliberately.

## Validate your change

Run the checks relevant to your change and report the exact commands and outcomes in the pull request:

```bash
uv run pytest
uv run ruff check
(cd web && npm run lint && npm run typecheck)
```

The default Python test command excludes tests marked `integration`. For routing changes, start the solver and run:

```bash
docker compose up -d --build solver
uv run pytest -m integration
```

For UI flows, bootstrap data, start the solver, and run:

```bash
cd web
npx playwright install chromium
npm run test:e2e
```

Playwright can start the API and production web server, or reuse running servers outside CI. Tests write drafts and audit rows to demo databases. Some chat scenarios need an Anthropic key; inspect the relevant tests before running them.

Documentation-only changes should check links, commands against the actual scripts, image paths, and Markdown rendering. Add meaningful regression coverage when changing application behavior. If a check cannot run, state the reason instead of marking it passed.

## Research and data contributions

State the dataset source, revision, license, seed, split, baseline, units, and evaluation protocol. Preserve existing results, including failures. Distinguish pre-registered choices from changes made after inspecting results. Never silently replace a baseline or claim production impact from simulated data.

Update provenance alongside new datasets. Do not commit private customer data, unlicensed datasets, provider keys, or full database dumps. FreshRetailNet validation uses the optional `bench` group (`uv sync --group bench`) and is separate from the demo pipeline.

Live assistant evaluation (`uv run python -m agent.eval --client anthropic`) calls a paid external service. Run it intentionally with your own credentials and include the model/configuration when reporting results.

## Submit a pull request

1. Describe the problem, the change, and any relevant issue.
2. Include screenshots for visible UI changes, or before/after examples for behavior changes.
3. List validation performed, known limitations, and any external-service requirements.
4. Update documentation and notices when behavior, configuration, dependencies, or data sources change.
5. Review the diff for secrets, generated artifacts, and unrelated changes.
6. Open the pull request against the repository's default branch and respond to review feedback.

No particular commit-message format is required; use clear, descriptive messages. Maintainers decide when a change is ready to merge.

## Licensing your contribution

By submitting a contribution, you agree to license your original contribution under the project's **GPL-3.0-only** license. Only submit material you have the right to contribute. Preserve upstream copyright, attribution, and license notices for third-party material. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
