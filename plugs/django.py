"""Django app plug for Fin.

Runs a Django project on the official ``python`` image with its built-in
development server (``manage.py runserver``). Because Fin bind-mounts the
project directory into the container, runserver's autoreloader (the polling
``StatReloader``) picks up source edits and restarts the server automatically —
live refresh on save, just like the Laravel plug, with no extra tooling and no
manual restart. Polling works reliably across Docker bind mounts (incl. macOS,
where inotify events don't propagate).

There is no maintained official Django image (the ``django`` Docker Hub image is
deprecated/Python 3.4), so this uses ``python:<version>-slim`` and installs the
project's ``requirements.txt`` on container start (preferring binary wheels). A
shared ``fin_pip_cache`` volume keeps pip's cache warm so reinstalls after
``fin down`` are fast.

Projects with native dependencies that compile from source (``psycopg2``,
source builds of ``Pillow``, ``mysqlclient``, ``lxml`` …) need system build
tooling that the slim image omits. Set ``FIN_APT_PACKAGES`` in the project
``.env`` to apt-install them before pip runs, e.g.::

    FIN_APT_PACKAGES=build-essential libpq-dev

Also pick a ``FIN_PYTHON_VERSION`` the project's pinned packages support (e.g.
Django 4.1 supports Python ≤ 3.11, not 3.12).

The plug is declarative: command handlers ask the :class:`PlugContext` to exec
inside the running primary container; they never touch Docker directly.
"""
from __future__ import annotations

from fincli.core.env import EnvSpec
from fincli.core.env import EnvVar
from fincli.plugs.base import ContainerSpec
from fincli.plugs.base import FinPlug
from fincli.plugs.base import PlugCommand
from fincli.plugs.base import PlugType
from fincli.plugs.base import PortMapping
from fincli.plugs.base import VolumeMount
from fincli.plugs.context import PlugContext

#: Where the project directory is bind-mounted inside the container.
WORKDIR = "/app"
#: pip cache dir inside the container, backed by a shared named volume.
PIP_CACHE_DIR = "/root/.cache/pip"
#: manage.py commands that prompt for input and need an interactive session.
_INTERACTIVE_MANAGE = {"shell", "dbshell", "createsuperuser", "changepassword"}

#: Fin's own control variables — not forwarded into the app container's env.
_FIN_CONTROL_VARS = frozenset({
    "FIN_APP", "FIN_PLUG", "FIN_PLUGS", "FIN_SITE", "FIN_PYTHON_VERSION",
    "FIN_DJANGO_PORT", "FIN_REQUIREMENTS", "FIN_APT_PACKAGES",
    "FIN_DOCKER_IMAGE", "FIN_CONTAINER_NAME", "FIN_OVERRIDE_ASSETS",
})


def _safe_port(value: str | None, default: int = 8000) -> int:
    """Parse a port from env, falling back to *default* on anything invalid."""
    try:
        return int(str(value)) if value else default
    except (TypeError, ValueError):
        return default


class DjangoPlug(FinPlug):
    name = "django"
    version = "1.0.0"
    plug_type = PlugType.APP
    description = "Django application runtime (python + runserver, live autoreload)."

    # --- env contract -------------------------------------------------------
    def env_spec(self) -> EnvSpec:
        return EnvSpec.of([
            EnvVar(
                "FIN_SITE",
                required=True,
                description="hostname the app is served at (e.g. myapp.localhost)",
            ),
            EnvVar(
                "FIN_PYTHON_VERSION",
                required=False,
                default="3.12",
                description="Python image tag (e.g. 3.12, 3.11, 3.13)",
            ),
            EnvVar(
                "FIN_DJANGO_PORT",
                required=False,
                value_type=int,
                default="8000",
                description="Port runserver binds inside the container",
            ),
            EnvVar(
                "FIN_REQUIREMENTS",
                required=False,
                default="requirements.txt",
                description="Requirements file installed on container start",
            ),
            EnvVar(
                "FIN_APT_PACKAGES",
                required=False,
                default="",
                description=(
                    "Space-separated apt packages to install before pip "
                    "(for native deps, e.g. 'build-essential libpq-dev')"
                ),
            ),
        ])

    # --- primary container --------------------------------------------------
    def primary_spec(self, env) -> ContainerSpec:
        py_version = env.get("FIN_PYTHON_VERSION", "3.12") or "3.12"
        image = env.get("FIN_DOCKER_IMAGE") or f"python:{py_version}-slim"
        port = _safe_port(env.get("FIN_DJANGO_PORT", "8000"))
        requirements = env.get("FIN_REQUIREMENTS", "requirements.txt") or "requirements.txt"
        apt_packages = (env.get("FIN_APT_PACKAGES", "") or "").strip()

        # Startup (runs once per container create): optionally apt-install system
        # packages needed to build native wheels (psycopg2, Pillow, mysqlclient…),
        # install Python deps preferring binary wheels, then hand control to
        # runserver via exec so it becomes the main process and its autoreloader
        # re-execs cleanly on code changes without re-running install steps.
        steps = ["set -e"]
        if apt_packages:
            steps.append(
                'apt-get update '
                "&& apt-get install -y --no-install-recommends ${FIN_APT_PACKAGES} "
                "&& rm -rf /var/lib/apt/lists/*"
            )
        steps.append(
            f"if [ -f '{requirements}' ]; then "
            f"pip install --prefer-binary -r '{requirements}'; fi"
        )
        steps.append(f"exec python manage.py runserver 0.0.0.0:{port}")
        startup = "; ".join(steps)

        # Forward the project's own .env into the container. Django reads its
        # config from os.environ (e.g. DJANGO_MYSQL_HOST, SECRET_KEY), unlike
        # Laravel which reads the mounted .env file directly. Fin's own control
        # vars are stripped so they don't leak into the app's environment.
        environment = {
            k: v for k, v in env.values.items() if k not in _FIN_CONTROL_VARS
        }
        environment.update({
            "FIN_CONTAINER_TYPE": "web",
            "PYTHONUNBUFFERED": "1",        # stream runserver output to `fin logs`
            "PYTHONDONTWRITEBYTECODE": "1",  # don't litter the mounted volume with .pyc
            "PIP_CACHE_DIR": PIP_CACHE_DIR,
            "FIN_APT_PACKAGES": apt_packages,
        })
        return ContainerSpec(
            service="web",
            image=image,
            name_suffix="web",
            environment=environment,
            command=["sh", "-c", startup],
            # random host port; Traefik routes by FIN_SITE.
            ports=[PortMapping(container=port, host=None)],
            # shared, warm pip cache so post-`down` reinstalls are fast.
            volumes=[VolumeMount(host="fin_pip_cache", container=PIP_CACHE_DIR)],
            web_exposed=True,
            web_port=port,
            workdir_mount=WORKDIR,
            extra={"working_dir": WORKDIR},
        )

    # --- commands -----------------------------------------------------------
    def commands(self):
        return {
            "manage": PlugCommand(
                "manage",
                _manage,
                "Run a manage.py command (passthrough)."),
            "migrate": PlugCommand(
                "migrate",
                _migrate,
                "Apply database migrations."),
            "makemigrations": PlugCommand(
                "makemigrations",
                _makemigrations,
                "Create new migrations from model changes.",
                aliases=(
                    "mm",
                )),
            "shell": PlugCommand(
                "shell",
                _shell,
                "Open the Django shell (interactive)."),
            "dbshell": PlugCommand(
                "dbshell",
                _dbshell,
                "Open the database shell (interactive)."),
            "createsuperuser": PlugCommand(
                "createsuperuser",
                _createsuperuser,
                "Create a Django superuser (interactive).",
                aliases=(
                    "csu",
                )),
            "collectstatic": PlugCommand(
                "collectstatic",
                _collectstatic,
                "Collect static files."),
            "test": PlugCommand(
                "test",
                _test,
                "Run the Django test suite."),
            "startapp": PlugCommand(
                "startapp",
                _startapp,
                "Scaffold a new Django app."),
            "pip": PlugCommand(
                "pip",
                _pip,
                "Run pip in the container."),
            "python": PlugCommand(
                "python",
                _python,
                "Run python (REPL when given no args).",
                aliases=(
                    "py",
                )),
            "bash": PlugCommand(
                "bash",
                _bash,
                "Open a shell in the container.",
                aliases=(
                    "sh",
                )),
        }


# --- command handlers ------------------------------------------------------- #
# Each receives (ctx: PlugContext, args: list[str]) and returns an exit code.
def _manage(ctx: PlugContext, args: list[str]) -> int:
    # Some manage.py subcommands prompt for input; attach stdin for those.
    interactive = bool(args) and args[0] in _INTERACTIVE_MANAGE
    return ctx.exec(["python", "manage.py", *args],
                    workdir=WORKDIR, interactive=interactive)


def _migrate(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "migrate", *args], workdir=WORKDIR)


def _makemigrations(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "makemigrations", *args], workdir=WORKDIR)


def _shell(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "shell", *args],
                    workdir=WORKDIR, interactive=True)


def _dbshell(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "dbshell", *args],
                    workdir=WORKDIR, interactive=True)


def _createsuperuser(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "createsuperuser", *args],
                    workdir=WORKDIR, interactive=True)


def _collectstatic(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "collectstatic", *args], workdir=WORKDIR)


def _test(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["python", "manage.py", "test", *args], workdir=WORKDIR)


def _startapp(ctx: PlugContext, args: list[str]) -> int:
    if not args:
        from fincli.ui.console import error
        error("Usage: fin startapp <name> [path]", title="Invalid Argument")
        return 1
    return ctx.exec(["python", "manage.py", "startapp", *args], workdir=WORKDIR)


def _pip(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["pip", *args], workdir=WORKDIR)


def _python(ctx: PlugContext, args: list[str]) -> int:
    # `fin python` with no args opens an interactive REPL; with args it's one-shot.
    return ctx.exec(["python", *args], workdir=WORKDIR, interactive=not args)


def _bash(ctx: PlugContext, args: list[str]) -> int:
    # An interactive shell session — attach stdin so `exit`/Ctrl-D ends it.
    return ctx.exec(["bash", *args], workdir=WORKDIR, interactive=True)
