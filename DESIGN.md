# fin-plugs — Design

How the plugs in this repo integrate with the `fincli` tool. This is the
plug-side companion to `fin-v2/DESIGN.md` (the tool's architecture deep-dive);
file references below point into the sibling `fin-v2` repo.

---

## 1. The two-repo model: compiled tool, plain-text plugs

`fincli` ships as a **compiled binary** (PyInstaller/Nuitka). The binary embeds
its own Python interpreter, the `fincli` package, and the standard library —
and nothing else: **no site-packages**. Plugs are deliberately *not* compiled
in. They live as ordinary `.py` files under `~/.fin/plugs` and are imported at
runtime by the binary's embedded interpreter.

```
┌──────────────────────────────┐        ┌──────────────────────────────┐
│  fin binary (immutable)      │        │  ~/.fin/plugs (writable)     │
│  ├─ embedded Python + stdlib │  file- │  ├─ App/{laravel,django}     │
│  ├─ fincli package           │  path  │  ├─ Asset/{mysql,postgres,   │
│  └─ NO site-packages         │ import │  │        redis,minio}       │
│                              │ ─────► │  └─ Global/                  │
└──────────────────────────────┘        └──────────────────────────────┘
```

**Why.** The tool stays a single immutable artifact that can be updated
atomically, while plugs remain user-serviceable text: installable by copying a
directory, editable in place, hackable without a toolchain. This repo is that
writable half.

**The consequence — the import rule.** Because the embedded interpreter has no
site-packages, a plug may import only:

1. `fincli.*` — the plug API surface (below), and
2. the Python **standard library**.

A third-party import (`requests`, `yaml`, `docker`, …) may work on a dev
machine where those packages happen to be installed, and then fail inside the
shipped binary — the loader logs a warning and drops the plug. Anything heavy
belongs *inside the container the plug describes* (apt/pip steps in the
container's startup command, as the django plug does), never in the plug
process.

## 2. The declarative contract

A plug **describes**; it never **acts**. It returns data — `ContainerSpec`s
and `PlugCommand`s — and Fin's orchestrator (`fin-v2/fincli/core/orchestrator.py`),
the only code path that mutates the Docker daemon, acts on its behalf. A plug
never imports `docker`, never calls `run_container`, never shells out to the
docker CLI. This gives one audited Docker path: labels (`FIN_MANAGED`,
`FIN_TYPE`, …), the `fin` network, naming, and Traefik routing are applied
uniformly no matter which plug described the container — a plug *cannot*
forget a label or escape teardown. It also keeps plugs pure functions over
data: trivially testable with no daemon, which is exactly what `tests/` does.

## 3. The API surface (`fin-v2/fincli/plugs/base.py`, `context.py`, `core/env.py`)

### `FinPlug` — identity + the four overridables

```python
class MyPlug(FinPlug):
    name = "myplug"           # unique; keep equal to the directory name
    version = "1.0.0"
    plug_type = PlugType.APP  # APP | ASSET | GLOBAL
    description = "…"

    def env_spec(self) -> EnvSpec: ...                        # env contract
    def primary_spec(self, env) -> ContainerSpec | None: ...  # APP plugs
    def asset_specs(self, env) -> list[ContainerSpec]: ...    # ASSET plugs
    def commands(self) -> Mapping[str, PlugCommand]: ...      # sub-commands
```

`setup()` is an optional post-instantiation hook (cheap init only, no Docker).
`env` is a `ProjectEnv`: the project's `.env` merged with process env
(`FIN_*`/`DB_*`/`REDIS_*` win), plus helpers (`get`, `require`,
`project_name`).

### `ContainerSpec` — one container, described

Key fields (see `base.py` for all): `service` (the `FIN_SERVICE` label),
`image`, `environment`, `ports` (`PortMapping(container, host=None)` — `None`
lets Docker pick; Traefik routes), `volumes` (`VolumeMount(host, container)`;
a named volume as `host` makes a persistent Docker volume), `command`,
`web_exposed` + `web_port` (opts into Traefik routing by `FIN_SITE`),
`workdir_mount` (where `fin up` bind-mounts the project dir for primaries),
`container_name` (fixed shared name — assets) vs `name_suffix`
(`<project>-<suffix>` — primaries), and `extra` (raw kwargs forwarded to
`containers.run`).

**`install_certs` (opt-in).** Setting `install_certs=True` makes every
`fin up` copy the user's CA certs (`~/.fin/certs/*.{pem,crt}`) into the
container and refresh its trust store. Defaults target Debian-family images
(`cert_dir="/usr/local/share/ca-certificates"`,
`cert_update_cmd=["update-ca-certificates"]`); override both for other
families (RHEL: `/etc/pki/ca-trust/source/anchors` +
`["update-ca-trust", "extract"]`). Best-effort and idempotent — a cert problem
never fails the up. The laravel plug opts in; see `App/laravel/__init__.py`.

### `PlugCommand` + `PlugContext` — how commands execute

`commands()` maps a name to `PlugCommand(name, handler, help, aliases)`. A
handler is `(ctx: PlugContext, args: list[str]) -> int` and delegates every
action to `ctx.exec(cmd, workdir=…, interactive=…)`, which execs inside the
project's *primary* container (warns and returns 1 if it isn't running).

`interactive=True` attaches local stdin to a container TTY — required for
anything the user types into: shells, REPLs (`tinker`, `python`), and
prompting commands (`artisan vendor:publish`, `manage.py createsuperuser`,
composer). It transparently falls back to streaming when there is no TTY, so
wrapping prompt-capable one-shots interactively is safe in CI. Genuinely
non-interactive helpers (`phpunit`, `php -v`) stay `interactive=False`.

Command resolution when the user types `fin <cmd>`: **reserved** (system
commands, never shadowed) → the `FIN_APP` plug → each `FIN_PLUGS` plug in
order → `GLOBAL` plugs; first name-or-alias match wins
(`fin-v2/fincli/resolver.py`).

### `EnvSpec` / `EnvVar` — the env-contract pattern

Every configurable plug declares its variables once, declaratively:

```python
def env_spec(self) -> EnvSpec:
    return EnvSpec.of([
        EnvVar("FIN_SITE", required=True, description="hostname served at"),
        EnvVar("FIN_PHP_VERSION", default="latest"),
        EnvVar("FIN_COMPOSER_VERSION", choices=("1", "2"), default="2"),
        EnvVar("FIN_DJANGO_PORT", value_type=int, default="8000"),
    ])
```

`fin up` runs `plug.env_spec().validate(env)` and raises **one** error listing
every failing variable, so a misconfigured `.env` is fixed in a single pass.
Inside `primary_spec` the plugs still read defensively
(`env.get("X", default) or default`) because an empty string in `.env` is not
`None`, and they degrade rather than crash on junk (see the django plug's
`_safe_port`).

## 4. The loader: file-path imports over a directory tree

`fin-v2/fincli/plugs/loader.py` discovers plugs from
`Config.PLUGS_DIR = ~/.fin/plugs` (moves with `FIN_DATA_DIR`), grouped by type
directory — `App/`, `Asset/`, `Global/` (`Config.PLUG_TYPE_DIRS`). For each
package directory it:

1. imports `__init__.py` **by file path**
   (`importlib.util.spec_from_file_location`) under the synthetic module name
   `fin_plug_<TypeDir>_<name>` — plugs are not on `sys.path` and cannot be
   imported by package name;
2. picks the single class subclassing `FinPlug` *defined in that module*
   (imported classes are ignored — importing `FinPlug` itself doesn't count);
3. instantiates it and calls `setup()`.

Any failure at any step logs a warning and skips that plug — one broken plug
never crashes Fin. Entries starting with `.` or `_` are ignored (so
`__pycache__/` is harmless); a bare `<name>.py` also works as a single-file
plug. The SQLite registry (`~/.fin/registry.db`) is only a cache over this
tree, re-synced by `fin plugs list` — the directory layout is the source of
truth.

## 5. App vs Asset in practice

**APP plugs** (laravel, django) describe the per-project primary container:
`service="web"`, `web_exposed=True` + `web_port` for Traefik routing by
`FIN_SITE`, `workdir_mount` telling `fin up` where to bind-mount the project,
host port `None` (Traefik routes; no port juggling), and the developer command
set. The two bundled apps show the two config-injection styles: Laravel reads
the mounted `.env` file itself, so its spec forwards almost nothing; Django
reads `os.environ`, so its spec forwards the project env into the container —
minus `_FIN_CONTROL_VARS`, Fin's own steering variables, which must never leak
into an app's environment.

**ASSET plugs** (mysql, postgres, redis, minio) describe machine-wide shared
services: a **fixed** `container_name` (`fin_mysql`, …) so every project hits
the same instance, published host ports for host-side tooling, a persistent
volume, and credentials from `Config.ASSET_USERNAME`/`ASSET_PASSWORD`/
`ASSET_DEFAULT_DATABASE` (fixed `fin`/`password`/`fin` — throwaway local-dev
values by design; `fin up` auto-creates each project's `DB_DATABASE` inside
the shared engine). Assets are isolated by database, not by container.

**GLOBAL plugs** contribute project-independent commands; there are none yet
(`Global/` is kept as an empty tree).

## 6. Testing model

`tests/test_bundled_plugs.py` exercises the **real** plugs in this repo by
pointing `Config.PLUGS_DIR` at the repo root and loading through the real
loader (`load_by_name`) — so the tests cover discovery, the class contract,
env specs, container specs, and command wiring exactly as `fin up` would see
them. Because plugs are declarative, no Docker daemon is involved: handler
tests substitute a `FakeCtx` recording `ctx.exec` calls and assert the exact
command, workdir, and interactivity delegated. Autouse fixtures in
`tests/conftest.py` (mirrored from `fin-v2/tests/conftest.py`) re-point
`Config.DATA_DIR`/`CONFIG_FILE`/`REGISTRY_DB` at per-test tmp dirs and reset
the `DockerService` singleton, keeping the suite hermetic.
