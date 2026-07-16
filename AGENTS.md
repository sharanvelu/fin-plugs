# AGENTS.md — working in the fin-plugs repo

Guide for AI coding agents. Read [DESIGN.md](DESIGN.md) for how plugs integrate
with the `fincli` tool, and [README.md](README.md) for user-facing behaviour.
The tool itself lives in a sibling repo (`fin-v2`); its `AGENTS.md`/`DESIGN.md`
cover the core.

## What this repo is

The plug library for Fin (`fincli`) — the plugin-driven CLI that runs local-dev
Docker containers. Every plug is a **declarative** Python class: it describes
containers (`ContainerSpec`) and contributes commands (`PlugCommand`), and Fin
acts on its behalf. This repo holds ONLY plug source plus its tests; there is
no packaging, no dependencies, and nothing to build.

## Project layout

```
App/                      primary application runtimes (PlugType.APP)
  laravel/__init__.py     LaravelPlug — PHP image, artisan/composer/tinker/… commands
  django/__init__.py      DjangoPlug — python-slim + runserver, manage/migrate/shell/… commands
Asset/                    shared fixed-name services (PlugType.ASSET)
  mysql/__init__.py       MySQLPlug    — fin_mysql, mysql:8.0
  postgres/__init__.py    PostgresPlug — fin_postgres, postgres:16-alpine
  redis/__init__.py       RedisPlug    — fin_redis, redis:7-alpine
  minio/__init__.py       MinioPlug    — fin_minio, quay.io/minio/minio
Global/                   project-independent plugs (empty; .gitkeep only)
tests/
  conftest.py             hermetic fixtures (isolate ~/.fin, fake docker objects)
  test_bundled_plugs.py   loads the REAL plugs above and checks their contracts
```

At runtime plugs load from `Config.PLUGS_DIR`, fixed at `~/.fin/plugs` (moves
with `FIN_DATA_DIR`) — see `fin-v2/fincli/config.py`. For development, symlink
this repo there once: `ln -s "$PWD" ~/.fin/plugs`.

## Conventions (do not violate)

- **Plugs import ONLY `fincli.*` and the Python standard library.** `fincli`
  ships as a compiled binary embedding its own interpreter + stdlib but **no
  site-packages**; plugs run as plain `.py` files under that interpreter, so a
  third-party import fails to load at runtime even if it works on your machine.
  Heavy dependencies belong inside the container the plug describes.
- **Plugs are declarative.** Return `ContainerSpec`/`PlugCommand`; never import
  `docker`, never call `run_container`, never `subprocess` the docker CLI. The
  only way a plug executes anything is `ctx.exec(...)` (`PlugContext`), which
  runs inside the project's primary container via Fin's audited Docker path.
- **One `FinPlug` subclass per package.** The loader imports each plug package
  by file path and picks the single class subclassing `FinPlug` that is
  *defined in that module* (imported classes are ignored). Set `name`,
  `version`, `plug_type`, `description`.
- **Terminal output goes through `fincli.ui.console`** (`error`, `warning`, …).
  Never call bare `print()` in a plug. Import it locally inside the handler
  (see `_make` in the laravel plug) to keep module import light.
- **Assets use fixed names and Config credentials.** Shared containers are
  `fin_<service>` with `container_name` set explicitly; credentials come from
  `Config.ASSET_USERNAME` / `ASSET_PASSWORD` / `ASSET_DEFAULT_DATABASE`
  (fixed `fin`/`password`/`fin`) — never hardcode them in the plug.
- Modules use `from __future__ import annotations`.

## How to add a plug

1. Create `{App|Asset|Global}/<name>/__init__.py` with one class subclassing
   `FinPlug` (`name`, `version`, `plug_type`, `description`).
2. APP plugs implement `primary_spec(env) -> ContainerSpec` (set `service="web"`,
   `web_exposed`/`web_port` for Traefik routing, `workdir_mount` for the project
   bind mount). ASSET plugs implement `asset_specs(env) -> list[ContainerSpec]`
   with a fixed `container_name`.
3. Declare env requirements with `env_spec()` returning an `EnvSpec` of
   `EnvVar`s (`required`, `choices`, `value_type`, `default`, `description`).
   `fin up` validates it and reports *all* problems at once.
4. Add `commands()` returning `{name: PlugCommand(name, handler, help, aliases)}`.
   Handlers take `(ctx: PlugContext, args: list[str])`, return an exit code, and
   delegate via `ctx.exec([...], workdir=..., interactive=...)`. Set
   `interactive=True` for anything the user types into (shells, REPLs, prompting
   commands); it falls back to streaming when there's no TTY, so CI is safe.
5. To trust the user's CA certs (`~/.fin/certs`), set `install_certs=True` on
   the `ContainerSpec` (Debian defaults; override `cert_dir`/`cert_update_cmd`
   for other bases — RHEL: `/etc/pki/ca-trust/source/anchors` +
   `["update-ca-trust", "extract"]`).
6. Add tests in `tests/test_bundled_plugs.py` (load via `load_by_name`, assert
   the env spec, the container spec fields, and each handler's `ctx.exec`
   delegation with the `FakeCtx` recorder) and run the suite.

## Running tests

```bash
# one-time: make fincli importable (no venv; Fin is a --user install)
python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2

python3 -m pytest                     # full suite
python3 -m pytest -k django           # focused run
```

The suite loads the **real** plugs in this repo (`Config.PLUGS_DIR` is pointed
at the repo root) but is otherwise hermetic: an autouse fixture re-points
`Config.DATA_DIR`/`CONFIG_FILE`/`REGISTRY_DB` at a per-test tmp dir and another
clears the `DockerService` singleton, so no test can touch a real Docker daemon
or the developer's `~/.fin`.

To smoke-test against the actual tool (with the symlink in place):

```bash
python3 -m fincli plugs list          # all six plugs should show as loaded
```

CI (`.github/workflows/ci.yml`) runs on every push/PR: the suite across Python
3.11–3.13 (checking out the public `sharanvelu/fin` repo for `fincli`), a
`ruff check` lint job, and a dedicated **plug contracts** job
(`tests/test_plug_contracts.py`) enforcing the fincli/stdlib-only import rule,
the declarative no-Docker rule, and loader discovery for every plug. Run those
contract checks locally with `python3 -m pytest tests/test_plug_contracts.py`.

## Gotchas

- **The loader imports by file path, not module name.** Each plug becomes
  module `fin_plug_<TypeDir>_<name>`; relative imports beyond the plug package
  won't resolve. Directories starting with `.` or `_` are skipped (which is why
  stray `__pycache__/` dirs are harmless).
- **A broken plug is silently-ish skipped.** Import errors, a missing `FinPlug`
  subclass, or a failing `setup()` log a warning and the plug is dropped — a
  "missing" plug in `fin plugs list` usually means an import error, not a
  discovery problem. A third-party import is the classic cause.
- **Directory name vs `name` attribute.** `load_by_name` matches the package
  directory first, then falls back to scanning declared `.name` attributes.
  Keep them identical to avoid confusion.
- **`Config` paths are resolved at import time.** Tests must
  `monkeypatch.setattr(Config, "PLUGS_DIR", ...)` — setting `FIN_DATA_DIR`
  after `fincli.config` is imported has no effect.
- **`env.get(...)` returns what's in the `.env`, including empty strings** —
  follow the existing `env.get("X", default) or default` pattern when an empty
  value should fall back.
- **Don't forward Fin control vars into app containers.** See the django plug's
  `_FIN_CONTROL_VARS` strip — `FIN_*` steering vars must not leak into the
  app's environment.
- **`fin plugs list` writes the real registry.** It re-syncs
  `~/.fin/registry.db` from disk; that's expected outside tests, but never do
  it *inside* a test without the isolation fixtures.
