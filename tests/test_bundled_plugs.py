"""Tests for the bundled plugs (Laravel/Django apps + MySQL/Redis/Postgres/Minio assets).

These load the *real* plugs in this repository by name, exercising the plug
contracts (env spec, primary/asset specs, command maps) through the real
fincli loader.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fincli.config import Config
from fincli.core.env import ProjectEnv
from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_by_name

#: The repo root is itself a PLUGS_DIR tree (App/ Asset/ Global/).
REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def bundled_plugs(monkeypatch):
    monkeypatch.setattr(Config, "PLUGS_DIR", REPO_ROOT)
    return REPO_ROOT


def _env(tmp_path, **values):
    return ProjectEnv(cwd=tmp_path, values=dict(values))


def test_laravel_loads(bundled_plugs):
    lp = load_by_name("laravel")
    assert lp is not None
    assert lp.plug_type is PlugType.APP
    assert lp.instance.name == "laravel"


def test_laravel_env_spec(bundled_plugs):
    lp = load_by_name("laravel")
    spec = lp.instance.env_spec()
    names = {v.name for v in spec.variables}
    assert "FIN_SITE" in names
    assert "FIN_PHP_VERSION" in names
    assert "FIN_COMPOSER_VERSION" in names
    # FIN_SITE is required
    site_var = next(v for v in spec.variables if v.name == "FIN_SITE")
    assert site_var.required is True


def test_laravel_primary_spec(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_SITE="app.localhost", FIN_PHP_VERSION="8.3"))
    assert spec.service == "web"
    assert spec.image == "sharanvelu/laravel-php:8.3"
    assert spec.web_exposed is True
    assert spec.web_port == 80
    assert spec.workdir_mount == "/var/www/html"
    # Laravel opts into installing ~/.fin/certs (Debian image → spec defaults).
    assert spec.install_certs is True
    assert spec.cert_dir == "/usr/local/share/ca-certificates"
    assert spec.cert_update_cmd == ["update-ca-certificates"]


def test_laravel_primary_spec_custom_image(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_DOCKER_IMAGE="custom/image:tag"))
    assert spec.image == "custom/image:tag"


def test_laravel_commands(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    for name in ("artisan", "composer", "tinker", "migrate", "bash", "php"):
        assert name in cmds
    # artisan has an alias
    assert "art" in cmds["artisan"].aliases


class FakeCtx:
    """Records the args/kwargs a plug command handler passes to ctx.exec().

    Mirrors the real PlugContext.exec signature, including the ``interactive``
    kwarg used by REPL/shell handlers (tinker, bash).
    """

    def __init__(self):
        self.calls = []

    def exec(self, cmd, *, workdir=None, interactive=False):
        self.calls.append({"cmd": cmd, "workdir": workdir, "interactive": interactive})
        return 0


def test_laravel_artisan_handler_delegates(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()

    ctx = FakeCtx()
    rc = cmds["artisan"].handler(ctx, ["migrate", "--seed"])
    assert rc == 0
    assert ctx.calls[0]["cmd"] == ["php", "artisan", "migrate", "--seed"]
    assert ctx.calls[0]["workdir"] == "/var/www/html"


def test_laravel_migrate_subcommands(bundled_plugs, tmp_path):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()

    ctx = FakeCtx()
    cmds["migrate"].handler(ctx, ["fresh"])
    assert ctx.calls[0]["cmd"] == ["php", "artisan", "migrate:fresh"]


# --------------------------------------------------------------------------- #
# Interactive contract.
# --------------------------------------------------------------------------- #
def test_laravel_tinker_is_interactive(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["tinker"].handler(ctx, [])
    assert ctx.calls[0]["interactive"] is True


def test_laravel_bash_is_interactive(bundled_plugs):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["bash"].handler(ctx, [])
    assert ctx.calls[0]["interactive"] is True


# artisan/composer wrappers run interactively so prompts (vendor:publish,
# make:model, migrate's production guard, composer prompts, …) work. The
# interactive path falls back to streaming when there's no TTY, so CI is fine.
@pytest.mark.parametrize(
    "name,args",
    [
        ("artisan", ["vendor:publish"]),
        ("artisan", ["list"]),
        ("composer", ["install"]),
        ("migrate", []),
        ("seed", []),
        ("make", ["model", "Post"]),
        ("queue", ["work"]),
    ],
)
def test_laravel_artisan_wrappers_are_interactive(bundled_plugs, name, args):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds[name].handler(ctx, args)
    assert ctx.calls[0]["interactive"] is True


# Genuinely non-interactive helpers stay non-interactive (they still get colour
# via the streamed TTY path, just no stdin attached).
@pytest.mark.parametrize("name,args", [("phpunit", []), ("php", ["-v"])])
def test_laravel_oneshot_handlers_not_interactive(bundled_plugs, name, args):
    lp = load_by_name("laravel")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds[name].handler(ctx, args)
    assert ctx.calls[0]["interactive"] is False


# --------------------------------------------------------------------------- #
# Django app plug
# --------------------------------------------------------------------------- #
def test_django_loads(bundled_plugs):
    lp = load_by_name("django")
    assert lp is not None
    assert lp.plug_type is PlugType.APP
    assert lp.instance.name == "django"


def test_django_env_spec(bundled_plugs):
    lp = load_by_name("django")
    spec = lp.instance.env_spec()
    names = {v.name for v in spec.variables}
    assert {"FIN_SITE", "FIN_PYTHON_VERSION", "FIN_DJANGO_PORT", "FIN_REQUIREMENTS"} <= names
    site_var = next(v for v in spec.variables if v.name == "FIN_SITE")
    assert site_var.required is True
    py_var = next(v for v in spec.variables if v.name == "FIN_PYTHON_VERSION")
    assert py_var.default == "3.12"


def test_django_primary_spec(bundled_plugs, tmp_path):
    lp = load_by_name("django")
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_SITE="app.localhost"))
    assert spec.service == "web"
    assert spec.image == "python:3.12-slim"  # default
    assert spec.web_exposed is True
    assert spec.web_port == 8000
    assert spec.workdir_mount == "/app"
    assert spec.extra.get("working_dir") == "/app"
    # autoreloading dev server + dependency install on start
    joined = " ".join(spec.command)
    assert "manage.py runserver 0.0.0.0:8000" in joined
    assert "pip install --prefer-binary -r" in joined
    # warm pip cache volume
    assert any(v.host == "fin_pip_cache" for v in spec.volumes)
    # live-output env
    assert spec.environment.get("PYTHONUNBUFFERED") == "1"


def test_django_apt_packages_opt_in(bundled_plugs, tmp_path):
    lp = load_by_name("django")
    # Default: no apt step in the startup command.
    spec = lp.instance.primary_spec(_env(tmp_path, FIN_SITE="x.localhost"))
    assert "apt-get install" not in " ".join(spec.command)
    assert spec.environment.get("FIN_APT_PACKAGES") == ""

    # Opt-in: apt-install runs before pip and the packages reach the container env.
    spec2 = lp.instance.primary_spec(
        _env(tmp_path, FIN_SITE="x.localhost", FIN_APT_PACKAGES="build-essential libpq-dev")
    )
    joined = " ".join(spec2.command)
    assert "apt-get install" in joined
    assert joined.index("apt-get install") < joined.index("pip install")  # apt before pip
    assert spec2.environment["FIN_APT_PACKAGES"] == "build-essential libpq-dev"


def test_django_primary_spec_custom_version_and_port(bundled_plugs, tmp_path):
    lp = load_by_name("django")
    spec = lp.instance.primary_spec(
        _env(tmp_path, FIN_SITE="x.localhost", FIN_PYTHON_VERSION="3.11", FIN_DJANGO_PORT="9000")
    )
    assert spec.image == "python:3.11-slim"
    assert spec.web_port == 9000
    assert "runserver 0.0.0.0:9000" in " ".join(spec.command)


def test_django_primary_spec_custom_image_and_bad_port(bundled_plugs, tmp_path):
    lp = load_by_name("django")
    spec = lp.instance.primary_spec(
        _env(tmp_path, FIN_DOCKER_IMAGE="myorg/django:dev", FIN_DJANGO_PORT="not-a-number")
    )
    assert spec.image == "myorg/django:dev"
    assert spec.web_port == 8000  # falls back safely


def test_django_forwards_project_env_strips_control_vars(bundled_plugs, tmp_path):
    lp = load_by_name("django")
    spec = lp.instance.primary_spec(_env(
        tmp_path,
        FIN_SITE="x.localhost",            # control var → must NOT be forwarded
        FIN_PYTHON_VERSION="3.11",         # control var → must NOT be forwarded
        DJANGO_MYSQL_HOST="fin_mysql",     # app var → must be forwarded
        SECRET_KEY="s3cret",               # app var → must be forwarded
    ))
    env = spec.environment
    assert env["DJANGO_MYSQL_HOST"] == "fin_mysql"
    assert env["SECRET_KEY"] == "s3cret"
    assert "FIN_SITE" not in env
    assert "FIN_PYTHON_VERSION" not in env
    # plug runtime vars still set
    assert env["PYTHONUNBUFFERED"] == "1"


def test_django_commands(bundled_plugs):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    for name in ("manage", "migrate", "makemigrations", "shell", "createsuperuser",
                 "collectstatic", "test", "startapp", "pip", "python", "bash"):
        assert name in cmds
    assert "mm" in cmds["makemigrations"].aliases
    assert "csu" in cmds["createsuperuser"].aliases
    assert "py" in cmds["python"].aliases


def test_django_manage_passthrough(bundled_plugs):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["manage"].handler(ctx, ["migrate", "--noinput"])
    assert ctx.calls[0]["cmd"] == ["python", "manage.py", "migrate", "--noinput"]
    assert ctx.calls[0]["workdir"] == "/app"
    assert ctx.calls[0]["interactive"] is False


@pytest.mark.parametrize("name", ["shell", "dbshell", "createsuperuser", "bash"])
def test_django_interactive_handlers(bundled_plugs, name):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds[name].handler(ctx, [])
    assert ctx.calls[0]["interactive"] is True


def test_django_manage_interactive_for_prompting_subcommands(bundled_plugs):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["manage"].handler(ctx, ["createsuperuser"])
    assert ctx.calls[0]["interactive"] is True


def test_django_python_repl_is_interactive_with_no_args(bundled_plugs):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds["python"].handler(ctx, [])           # REPL → interactive
    assert ctx.calls[0]["interactive"] is True
    ctx2 = FakeCtx()
    cmds["python"].handler(ctx2, ["-c", "print(1)"])  # one-shot → not
    assert ctx2.calls[0]["interactive"] is False


@pytest.mark.parametrize("name,args", [("migrate", []), ("collectstatic", []), ("test", [])])
def test_django_oneshot_handlers_not_interactive(bundled_plugs, name, args):
    lp = load_by_name("django")
    cmds = lp.instance.commands()
    ctx = FakeCtx()
    cmds[name].handler(ctx, args)
    assert ctx.calls[0]["interactive"] is False


# --------------------------------------------------------------------------- #
# Asset plugs
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "plug_name,expected_image,container_name",
    [
        ("mysql", "mysql:8.0", "fin_mysql"),
        ("postgres", "postgres:16-alpine", "fin_postgres"),
        ("redis", "redis:7-alpine", "fin_redis"),
        ("minio", "quay.io/minio/minio", "fin_minio"),
    ],
)
def test_asset_plugs(bundled_plugs, tmp_path, plug_name, expected_image, container_name):
    lp = load_by_name(plug_name)
    assert lp is not None
    assert lp.plug_type is PlugType.ASSET
    specs = lp.instance.asset_specs(_env(tmp_path))
    assert len(specs) == 1
    spec = specs[0]
    assert spec.image == expected_image
    assert spec.container_name == container_name


@pytest.mark.parametrize(
    "plug_name,container_name,image",
    [
        ("postgres", "fin_postgres", "postgres:16-alpine"),
        ("redis", "fin_redis", "redis:7-alpine"),
    ],
)
def test_asset_spec_has_ports_and_volumes(
    bundled_plugs, tmp_path, plug_name, container_name, image
):
    lp = load_by_name(plug_name)
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    assert spec.container_name == container_name
    assert spec.image == image
    assert spec.ports  # at least one published port
    assert spec.volumes  # at least one persistent volume


def test_mysql_uses_config_credentials(bundled_plugs, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ASSET_USERNAME", "fin")
    monkeypatch.setattr(Config, "ASSET_PASSWORD", "password")
    lp = load_by_name("mysql")
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    assert spec.environment["MYSQL_USER"] == "fin"
    assert spec.environment["MYSQL_PASSWORD"] == "password"


def test_minio_spec(bundled_plugs, tmp_path):
    lp = load_by_name("minio")
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    # S3 API on 9000, web console on 9001, both published to the host.
    ports = {(p.container, p.host) for p in spec.ports}
    assert ports == {(9000, 9000), (9001, 9001)}
    # The console is served by `server --console-address :9001` and routed
    # by Traefik (web-exposed asset).
    assert spec.command == ["server", "/data", "--console-address", ":9001"]
    assert spec.web_exposed is True
    assert spec.web_port == 9001
    # Data persists in a host directory mounted at /data.
    assert spec.volumes and spec.volumes[0].container == "/data"


def test_minio_uses_config_credentials(bundled_plugs, tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "ASSET_USERNAME", "fin")
    monkeypatch.setattr(Config, "ASSET_PASSWORD", "password")
    lp = load_by_name("minio")
    spec = lp.instance.asset_specs(_env(tmp_path))[0]
    assert spec.environment["MINIO_ROOT_USER"] == "fin"
    assert spec.environment["MINIO_ROOT_PASSWORD"] == "password"
