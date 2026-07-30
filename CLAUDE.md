# CLAUDE.md

This repo is the **plug library** for Fin (`fincli`), the plugin-driven CLI
that manages local-development Docker containers (tool source: the sibling
`fin-v2` repo). Plugs are **declarative** classes subclassing `FinPlug`: they
describe containers (`ContainerSpec`) and contribute commands (`PlugCommand`),
and Fin's orchestrator acts on their behalf. This repo holds only plug source
(one file per plug under `plugs/`), the CI-generated `catalog.json`, and
tests — no packaging, no dependencies.

## Most important conventions

- **Plugs import ONLY `fincli.*` and the Python standard library.** The tool
  ships as a compiled binary with its own interpreter and stdlib but no
  site-packages — a third-party import in a plug fails to load at runtime.
  Heavy deps live inside the container the plug describes.
- **Plugs are declarative.** Never import `docker`, never call
  `run_container`, never shell out to the docker CLI. Handlers act only via
  `ctx.exec(...)` (`PlugContext`) inside the primary container.
- **One `FinPlug` subclass per `plugs/<name>.py`**, imported by file path; a
  broken plug warns and is skipped. Filenames are lowercase and MUST equal
  the plug's declared `name` — `fin plugs install <name>` fetches
  `https://raw.githubusercontent.com/sharanvelu/fin-plugs/master/plugs/<name>.py`,
  so renaming/moving a plug file is a breaking change. The type
  (APP/ASSET/GLOBAL) is declared in-class via `plug_type`.
- **`catalog.json` is generated, never hand-edited.** It powers
  `fin plugs search`; regenerate with `python3 scripts/build_catalog.py`
  after any plug change. CI checks PRs with `--check`; pushes to master
  publish the catalog to GitHub Releases as the next patch version
  (`1.1.2` → `1.1.3`) plus the rolling `latest` (asset always replaced).
  Plug files are always served from the master branch (`files_base_url`).
- **Assets are shared fixed-name containers** (`fin_mysql`, `fin_redis`, …)
  with credentials from `Config.ASSET_*` (`fin`/`password`) — never hardcoded.
- **Declare env contracts with `env_spec()`** (`EnvSpec`/`EnvVar`); `fin up`
  validates and reports every problem at once.
- **Interactive commands** (shells, REPLs, prompting artisan/manage.py
  subcommands) pass `interactive=True` to `ctx.exec`; one-shots don't.

## Setup / test / run

```bash
python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2   # make fincli importable (no venv)
python3 -m pytest                                                  # run the test suite
python3 scripts/build_catalog.py --check                           # catalog matches plugs/
```

Fin loads plugs at runtime from `~/.fin/plugs` as flat `<name>.py` files —
exactly this repo's `plugs/` layout — so the dev setup is a single symlink:
`ln -s "$PWD/plugs" ~/.fin/plugs`.

## More detail

- **[AGENTS.md](AGENTS.md)** — layout, conventions, how to add a plug, test
  fixtures, gotchas.
- **[.github/CI.md](.github/CI.md)** — the CI architecture (changes → work →
  gate per domain; only gates are required checks) and the catalog release
  flow.
- **[DESIGN.md](DESIGN.md)** — how plugs integrate with fincli: the declarative
  contract, the file-path loader, the compiled-binary model and import rule,
  the raw-URL install contract and catalog, `install_certs`, the env-spec
  pattern.
- **[README.md](README.md)** — what this repo is, the install URL scheme,
  `catalog.json`, per-plug summaries.
