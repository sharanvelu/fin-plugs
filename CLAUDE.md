# CLAUDE.md

This repo is the **plug library** for Fin (`fincli`), the plugin-driven CLI
that manages local-development Docker containers (tool source: the sibling
`fin-v2` repo). Plugs are **declarative** classes subclassing `FinPlug`: they
describe containers (`ContainerSpec`) and contribute commands (`PlugCommand`),
and Fin's orchestrator acts on their behalf. This repo holds only plug source
(`App/`, `Asset/`, `Global/`) plus tests — no packaging, no dependencies.

## Most important conventions

- **Plugs import ONLY `fincli.*` and the Python standard library.** The tool
  ships as a compiled binary with its own interpreter and stdlib but no
  site-packages — a third-party import in a plug fails to load at runtime.
  Heavy deps live inside the container the plug describes.
- **Plugs are declarative.** Never import `docker`, never call
  `run_container`, never shell out to the docker CLI. Handlers act only via
  `ctx.exec(...)` (`PlugContext`) inside the primary container.
- **One `FinPlug` subclass per `{App|Asset|Global}/<name>/__init__.py`**,
  imported by file path; a broken plug warns and is skipped.
- **Assets are shared fixed-name containers** (`fin_mysql`, `fin_redis`, …)
  with credentials from `Config.ASSET_*` (`fin`/`password`) — never hardcoded.
- **Declare env contracts with `env_spec()`** (`EnvSpec`/`EnvVar`); `fin up`
  validates and reports every problem at once.
- **Interactive commands** (shells, REPLs, prompting artisan/manage.py
  subcommands) pass `interactive=True` to `ctx.exec`; one-shots don't.

## Setup / test / run

```bash
ln -s "$PWD" ~/.fin/plugs                                          # plugs load from ~/.fin/plugs (PLUGS_DIR)
python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2   # make fincli importable (no venv)
python3 -m pytest                                                  # run the test suite
python3 -m fincli plugs list                                       # smoke test: all plugs "loaded"
```

## More detail

- **[AGENTS.md](AGENTS.md)** — layout, conventions, how to add a plug, test
  fixtures, gotchas.
- **[DESIGN.md](DESIGN.md)** — how plugs integrate with fincli: the declarative
  contract, the file-path loader, the compiled-binary model and import rule,
  `install_certs`, the env-spec pattern.
- **[README.md](README.md)** — what this repo is, installing plugs on a host,
  per-plug summaries.
