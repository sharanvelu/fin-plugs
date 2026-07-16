# fin-plugs

> The plug library for [Fin](../fin-v2) — declarative container recipes for
> local development.

This repository holds the **plugs** that Fin (`fincli`) loads at runtime. It is
deliberately separate from the tool: `fincli` ships as a compiled binary, while
plugs stay plain `.py` files on disk that the binary discovers and imports. The
plugs here contain **no Docker code** — each one is a small declarative class
describing containers (`ContainerSpec`) and commands (`PlugCommand`); Fin's
orchestrator acts on its behalf.

---

## Layout

```
App/          primary application runtimes (one per project, PlugType.APP)
  laravel/    Laravel / PHP (nginx + php-fpm + supervisord image)
  django/     Django (python:<ver>-slim + runserver, live autoreload)
Asset/        shared services, one fixed-name container across all projects
  mysql/      fin_mysql    — mysql:8.0
  postgres/   fin_postgres — postgres:16-alpine
  redis/      fin_redis    — redis:7-alpine
  minio/      fin_minio    — quay.io/minio/minio (S3-compatible object store)
Global/       project-independent plugs (currently empty)
tests/        pytest suite exercising the real plugs above
```

Each plug is a package directory with an `__init__.py` defining exactly one
class that subclasses `fincli.plugs.base.FinPlug`.

## Installing plugs on a host

At runtime Fin loads plugs from `PLUGS_DIR`, fixed at `~/.fin/plugs` (it moves
with `FIN_DATA_DIR`), grouped into `App/`, `Asset/`, and `Global/`. To install,
place or symlink plug directories there:

```bash
# a single plug
cp -r App/laravel ~/.fin/plugs/App/laravel

# or the whole library (recommended for development):
ln -s "$PWD" ~/.fin/plugs
```

Verify with `fin plugs list` — every plug should show as loaded. A broken plug
logs a warning and is skipped; it never crashes Fin.

## Development workflow

```bash
git clone <this-repo> && cd fin-plugs

# 1. Point Fin at your working tree (once):
ln -s "$PWD" ~/.fin/plugs

# 2. Make fincli importable for your IDE and the tests (no venv):
python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2

# 3. Run the tests:
python3 -m pytest
```

Edits are live immediately — Fin re-imports plugs from disk on every
invocation.

## The import rule (important)

`fincli` ships as a **compiled binary** (PyInstaller/Nuitka) that embeds its own
Python interpreter, the `fincli` package, and the standard library — but **no
site-packages**. Plugs are executed by that embedded interpreter, so a plug may
import **only**:

1. `fincli.*` — the plug API (`fincli.plugs.base`, `fincli.plugs.context`,
   `fincli.core.env`, `fincli.config`), and
2. the **Python standard library**.

Never import third-party packages (`requests`, `docker`, `yaml`, …) — they do
not exist inside the binary and the plug will fail to load. Anything heavy
belongs *inside the container* the plug describes, not in the plug itself.

## The plugs

| Plug | Type | Summary |
| ---- | ---- | ------- |
| `laravel` | APP | Laravel/PHP runtime (`sharanvelu/laravel-php`, web on 80) with the full artisan/composer/tinker/migrate/queue command set; installs `~/.fin/certs` into the container (`install_certs=True`). |
| `django` | APP | Django on `python:<ver>-slim`; installs `requirements.txt` on start (warm shared pip cache), runs `manage.py runserver` with live autoreload; contributes manage/migrate/shell/createsuperuser/… commands. |
| `mysql` | ASSET | Shared MySQL 8.0 at `fin_mysql:3306`, credentials `fin`/`password`, persistent `fin_asset_mysql` volume. |
| `postgres` | ASSET | Shared PostgreSQL 16 (alpine) at `fin_postgres:5432`, credentials `fin`/`password`, persistent `fin_asset_postgres` volume. |
| `redis` | ASSET | Shared Redis 7 (alpine) at `fin_redis:6379`, persistent `fin_asset_redis` volume. |
| `minio` | ASSET | Shared MinIO object store at `fin_minio` (S3 API :9000, web console :9001, routed by Traefik), credentials `fin`/`password`. |

## Writing a plug

See [AGENTS.md](AGENTS.md) for the step-by-step guide and
[DESIGN.md](DESIGN.md) for how plugs integrate with the tool. In short: create
`{App|Asset|Global}/<name>/__init__.py`, subclass `FinPlug`, declare your env
contract with `env_spec()`, return `ContainerSpec`s from `primary_spec()` /
`asset_specs()`, and delegate command handlers to `ctx.exec(...)`. Describe,
never act.
