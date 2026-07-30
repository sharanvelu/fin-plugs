# CI/CD architecture

Mirrors the [fin repo's CI architecture](https://github.com/sharanvelu/fin)
(`fin-v2/.github/CI.md`). Every PR workflow follows the same
**changes → work → gate** pattern:

1. **`changes`** — `dorny/paths-filter` detects which domains the PR touches
   (each filter includes the workflow's own file and the shared setup action,
   so editing CI re-runs CI). On `workflow_dispatch` all outputs are forced to
   `'true'`.
2. **Work jobs** — path-gated with `if: needs.changes.outputs.<domain> == 'true'`;
   PRs that don't touch a domain skip its jobs entirely.
3. **`gate`** — runs `if: always()` and fails iff any needed job failed or was
   cancelled. **Only the gate is a required check** — a skipped work job can
   therefore never wedge a PR, and the required-check list stays stable as work
   jobs are added or renamed.

## Required status checks (branch ruleset on `master`)

| Check                  | Workflow                  | What it runs                                                        |
| ---------------------- | ------------------------- | ------------------------------------------------------------------- |
| `Tests Gate`           | `tests.yml`               | pytest (py 3.11–3.13); plug-contract checks; `fin plugs list` smoke |
| `Code Style Gate`      | `code-style.yml`          | `ruff check` + `ruff format --check` (check-only, never rewrites)   |
| `Catalog Gate`         | `catalog.yml`             | `scripts/build_catalog.py --check` — catalog.json matches plugs/    |
| `Static Analysis Gate` | `static-code-analyze.yml` | actionlint + zizmor when `.github/**` changes                       |
| `PR Title Lint`        | `pr-title.yml`            | Conventional Commits on the PR title (squash-merge commit message)  |
| `Dependency Review`    | `dependency-review.yml`   | blocks newly-introduced vulnerable deps (moderate+; github-actions) |

Never mark the work jobs themselves required — they are path-filtered and
legitimately skip.

Also enable in repo settings: **Allow auto-merge** (for
`dependabot-auto-merge.yml`), **squash merge** as the merge method, and the
**dependency graph** (for `dependency-review.yml`).

## The toolchain

This repo has no pyproject — plugs run under fincli, so the toolchain IS
fincli. The shared composite action
[`actions/setup`](actions/setup/action.yml) checks out `sharanvelu/fin` into
`fin-cli/` and installs `"./fin-cli[dev]"`, which brings pytest/ruff/mypy at
the tool repo's pinned versions. This repo pins no QA-tool versions of its
own, so the two repos can never disagree; ruff *rule selection* lives here in
`ruff.toml` (pinned explicitly — never ruff's floating defaults).

## Catalog release flow

```
push to master
  → catalog-release.yml regenerates catalog.json via the real fincli loader
      unchanged vs the `latest` release's asset?  → stop (no empty releases)
      changed → publish release <X.Y.(Z+1)> with catalog.json attached
                (previous 1.1.2 → this build 1.1.3; 1.0.0 when none exist)
              → replace the catalog.json asset on the rolling `latest` release
```

- The numbered releases are what GitHub's native
  `releases/latest/download/catalog.json` URL (fetched by the fin CLI)
  resolves to — keep them **non-prerelease and non-draft**.
- If GitHub's **immutable releases** setting is ever enabled here, the rolling
  `latest` release's `--clobber` upload will start failing; delete the rolling
  release — the numbered releases already serve the CLI. (The fin repo was
  bitten by exactly this.)
- Plug files are always served from the master branch raw URLs (the catalog's
  `files_base_url`); releases only distribute the catalog itself.

PR-side freshness (`Catalog Gate`) guarantees the committed `catalog.json`
never drifts from `plugs/`, so master regenerations are near-always no-ops.

## Deliberately not adopted from fin

- **mypy job** (`static-code-analyze.yml`) — this repo has no mypy config of
  its own; plugs are typed against fincli's API and the tool repo runs its own
  static analysis. The workflow keeps only the actionlint + zizmor job.
- **`codeql.yml`** — alerts-only (never a required check) and heavyweight for
  ~6 small declarative plug files already covered by the contract tests and
  zizmor; revisit if the plug library grows real logic.
- **`build-check.yml` / `tag.yml` / `build.yml`** — nothing to package here;
  the catalog release flow above is this repo's whole release story.

## Hardening conventions (apply to every workflow)

- `permissions: {}` at workflow level; per-job grants only.
- Third-party actions pinned to full commit SHAs (`# vX.Y.Z` comment).
- `actions/checkout` with `persist-credentials: false`.
- `timeout-minutes` on every job.
- A `concurrency` group per workflow — cancel-in-progress on PR workflows;
  NOT on `catalog-release.yml` (never cancel a half-finished publish).
- Toolchain setup only via the shared composite action
  [`actions/setup`](actions/setup/action.yml) — one place to bump Python.
- CI is check-only: it never reformats, auto-fixes, or commits code.
