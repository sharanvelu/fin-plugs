# fin-plugs

[![tests](https://github.com/sharanvelu/fin-plugs/actions/workflows/tests.yml/badge.svg)](https://github.com/sharanvelu/fin-plugs/actions/workflows/tests.yml)
[![catalog release](https://github.com/sharanvelu/fin-plugs/actions/workflows/catalog-release.yml/badge.svg)](https://github.com/sharanvelu/fin-plugs/actions/workflows/catalog-release.yml)

> The plug library for [Fin](https://github.com/sharanvelu/fin) — declarative
> container recipes for local development.

This repository holds the **plugs** that Fin (`fincli`) loads at runtime. It is
deliberately separate from the tool: `fincli` ships as a compiled binary, while
plugs stay plain `.py` files on disk that the binary discovers and imports. The
plugs here contain **no Docker code** — each one is a small declarative class
describing containers (`ContainerSpec`) and commands (`PlugCommand`); Fin's
orchestrator acts on its behalf.

---

## Layout

```
plugs/          every plug — one file each; the filename IS the plug name
  laravel.py    APP   — Laravel / PHP (nginx + php-fpm + supervisord image)
  django.py     APP   — Django (python:<ver>-slim + runserver, live autoreload)
  mysql.py      ASSET — fin_mysql    — mysql:8.0
  postgres.py   ASSET — fin_postgres — postgres:16-alpine
  redis.py      ASSET — fin_redis    — redis:7-alpine
  minio.py      ASSET — fin_minio    — quay.io/minio/minio (S3-compatible)
catalog.json    machine-readable plug index (CI-generated — never hand-edit)
scripts/        build_catalog.py — regenerates and validates catalog.json
tests/          pytest suite exercising the real plugs above
```

Each plug is a **single lowercase file** defining exactly one class that
subclasses `fincli.plugs.base.FinPlug`. The declared `name` attribute must
equal the filename, and the plug's type (APP / ASSET / GLOBAL) is declared
in-class via `plug_type` — the layout carries no type information.

## Installing plugs — the raw-URL contract

`fin plugs install <name>` downloads exactly one file over plain HTTPS:

```
https://raw.githubusercontent.com/sharanvelu/fin-plugs/master/plugs/<name>.py
```

The URL is derived from the plug name alone — that is why the layout is flat
and every filename is lowercase and equal to the plug's declared `name`.
**Renaming or moving a file under `plugs/` is a breaking change** for everyone
installing that plug: treat plug filenames as public API.

`fin plugs search <query>` reads [`catalog.json`](catalog.json), published on
GitHub Releases (see below):

```
https://github.com/sharanvelu/fin-plugs/releases/download/latest/catalog.json
```

Whichever catalog version is read, plug files themselves are always fetched
from the `master` branch — the catalog's `files_base_url` records that base.

Installed plugs land in `PLUGS_DIR`, fixed at `~/.fin/plugs` (it moves with
`FIN_DATA_DIR`). A broken plug logs a warning and is skipped; it never crashes
Fin. Verify with `fin plugs list`.

## catalog.json

The machine-readable index of every plug — name, type, version, description,
command names, and file path — that powers `fin plugs search`. It is
**generated, never hand-edited**:

- `python3 scripts/build_catalog.py` regenerates it (deterministic output —
  regeneration is a no-op when nothing changed);
- `python3 scripts/build_catalog.py --check` fails if the committed file is
  stale — CI runs this on every PR, so a plug change without a regenerated
  catalog cannot merge;
- every push to `master` regenerates the catalog and publishes it to GitHub
  Releases twice: as a **new incremental patch version** (previous release
  `1.1.2` → this build publishes `1.1.3`) and onto the rolling **`latest`**
  release, whose `catalog.json` asset is always replaced. Publishing is
  skipped when the catalog content hasn't changed.

Version-pinned catalogs stay available forever at
`releases/download/<version>/catalog.json`; `releases/download/latest/catalog.json`
always serves the current one. The catalog only indexes — plug files are
served from `master` (`files_base_url`), regardless of catalog version.

## Development workflow

> **Transitional limitation:** the released `fincli` binary still discovers
> plugs only under the old `App/`/`Asset/`/`Global/` type directories, so
> symlinking this repo into `~/.fin/plugs` no longer works. Until fin-v2
> ships flat-layout support (the dev setup then becomes
> `ln -s "$PWD/plugs" ~/.fin/plugs`), the plugs here are exercised through
> the test suite.

```bash
git clone <this-repo> && cd fin-plugs

# 1. Make fincli importable for your IDE and the tests (no venv):
python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2

# 2. Run the tests:
python3 -m pytest

# 3. After adding or changing a plug, regenerate the catalog:
python3 scripts/build_catalog.py
```

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
`plugs/<name>.py` (lowercase, equal to the class's declared `name`), subclass
`FinPlug`, declare your env contract with `env_spec()`, return
`ContainerSpec`s from `primary_spec()` / `asset_specs()`, delegate command
handlers to `ctx.exec(...)`, and regenerate `catalog.json`. Describe, never
act.
