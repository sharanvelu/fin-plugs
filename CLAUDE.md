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
  after any plug change (CI checks PRs with `--check` and auto-commits the
  regenerated catalog on pushes to master).
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

**Transitional:** the released `fincli` only discovers plugs under the old
`App/Asset/Global` tree, so the former dev symlink (`ln -s "$PWD"
~/.fin/plugs`) no longer works — exercise plugs via the test suite until
fin-v2 ships flat-layout support (then: `ln -s "$PWD/plugs" ~/.fin/plugs`).

## More detail

- **[AGENTS.md](AGENTS.md)** — layout, conventions, how to add a plug, test
  fixtures, gotchas.
- **[DESIGN.md](DESIGN.md)** — how plugs integrate with fincli: the declarative
  contract, the file-path loader, the compiled-binary model and import rule,
  the raw-URL install contract and catalog, `install_certs`, the env-spec
  pattern.
- **[README.md](README.md)** — what this repo is, the install URL scheme,
  `catalog.json`, per-plug summaries.
