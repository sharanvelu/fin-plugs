"""Laravel app plug for Fin.

Provides the primary PHP/Laravel container (a public PHP-FPM image bundling
nginx + php-fpm + supervisord, overridable via ``FIN_DOCKER_IMAGE``) and the
full set of Laravel developer commands (artisan, composer, tinker, migrate,
seed, make, queue, bash, phpunit, bin).

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
from fincli.plugs.context import PlugContext

#: Where the project directory is mounted inside the container.
WEBROOT = "/var/www/html"


class LaravelPlug(FinPlug):
    name = "laravel"
    version = "1.0.0"
    plug_type = PlugType.APP
    description = "Laravel / PHP application runtime (nginx + php-fpm + supervisord)."

    # --- env contract -------------------------------------------------------
    def env_spec(self) -> EnvSpec:
        return EnvSpec.of([
            EnvVar(
                "FIN_SITE",
                required=True,
                description="hostname the app is served at (e.g. myapp.localhost)",
            ),
            EnvVar(
                "FIN_PHP_VERSION",
                required=False,
                default="latest",
                description="PHP/image tag (e.g. 8.3, 8.2, latest)",
            ),
            EnvVar(
                "FIN_COMPOSER_VERSION",
                required=False,
                choices=("1", "2"),
                default="2",
                description="Composer major version",
            ),
        ])

    # --- primary container --------------------------------------------------
    def primary_spec(self, env) -> ContainerSpec:
        php_version = env.get("FIN_PHP_VERSION", "latest") or "latest"
        image = env.get("FIN_DOCKER_IMAGE") or f"sharanvelu/laravel-php:{php_version}"

        environment = {
            "FIN_CONTAINER_TYPE": "web",
            "FIN_COMPOSER_VERSION": env.get(
                "FIN_COMPOSER_VERSION",
                "2") or "2",
        }
        return ContainerSpec(
            service="web",
            image=image,
            name_suffix="web",
            environment=environment,
            # random host port; Traefik routes
            ports=[PortMapping(container=80, host=None)],
            web_exposed=True,
            web_port=80,
            workdir_mount=WEBROOT,
            # Install any CA certs from ~/.fin/certs into the container on `up`.
            # The image is Debian-based, so the ContainerSpec defaults
            # (/usr/local/share/ca-certificates + update-ca-certificates) apply.
            install_certs=True,
        )

    # --- commands -----------------------------------------------------------
    def commands(self):
        return {
            "artisan": PlugCommand(
                "artisan",
                _artisan,
                "Run an artisan command.",
                aliases=(
                    "art",
                )),
            "composer": PlugCommand(
                "composer",
                _composer,
                "Run composer in the container."),
            "tinker": PlugCommand(
                "tinker",
                _tinker,
                "Open a Laravel tinker session."),
            "migrate": PlugCommand(
                "migrate",
                _migrate,
                "Run migrations (fresh|rollback|refresh)."),
            "seed": PlugCommand(
                "seed",
                _seed,
                "Run database seeders ([class])."),
            "make": PlugCommand(
                "make",
                _make,
                "Run artisan make:<type>."),
            "queue": PlugCommand(
                "queue",
                _queue,
                "Run the queue (work|listen|restart)."),
            "bash": PlugCommand(
                "bash",
                _bash,
                "Open a shell in the container.",
                aliases=(
                    "shell",
                )),
            "phpunit": PlugCommand(
                "phpunit",
                _phpunit,
                "Run ./vendor/bin/phpunit."),
            "bin": PlugCommand(
                "bin",
                _bin,
                "Run ./vendor/bin/<command>."),
            "php": PlugCommand(
                "php",
                _php,
                "Run the php binary."),
        }


# --- command handlers ------------------------------------------------------- #
# Each receives (ctx: PlugContext, args: list[str]) and returns an exit code.
#
# Note: artisan/composer-wrapping handlers run interactively. Many artisan
# commands prompt (vendor:publish, make:model, migrate's production guard, …)
# and so does composer; attaching stdin lets those prompts work. When fin isn't
# attached to a TTY (piped/CI), ctx.exec transparently falls back to streaming,
# so non-interactive use is unaffected.
def _artisan(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["php", "artisan", *args], workdir=WEBROOT, interactive=True)


def _composer(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["composer", *args], workdir=WEBROOT, interactive=True)


def _tinker(ctx: PlugContext, args: list[str]) -> int:
    # tinker is a REPL — needs an interactive session so it reads stdin and
    # exits cleanly on `exit`/Ctrl-D.
    return ctx.exec(["php", "artisan", "tinker", *args],
                    workdir=WEBROOT, interactive=True)


def _migrate(ctx: PlugContext, args: list[str]) -> int:
    sub = args[0] if args else None
    cmd = "migrate"
    rest = args
    if sub in ("fresh", "rollback", "refresh"):
        cmd = f"migrate:{sub}"
        rest = args[1:]
    return ctx.exec(["php", "artisan", cmd, *rest],
                    workdir=WEBROOT, interactive=True)


def _seed(ctx: PlugContext, args: list[str]) -> int:
    cmd = ["php", "artisan", "db:seed"]
    if args:
        cmd += ["--class", args[0], *args[1:]]
    return ctx.exec(cmd, workdir=WEBROOT, interactive=True)


def _make(ctx: PlugContext, args: list[str]) -> int:
    if not args:
        from fincli.ui.console import error
        error(
            "Usage: fin make <type> <name> [options]",
            title="Invalid Argument")
        return 1
    return ctx.exec(["php",
                     "artisan",
                     f"make:{args[0]}",
                     *args[1:]],
                    workdir=WEBROOT, interactive=True)


def _queue(ctx: PlugContext, args: list[str]) -> int:
    sub = args[0] if args else "listen"
    return ctx.exec(
        ["php", "artisan", f"queue:{sub}", *args[1:]],
        workdir=WEBROOT, interactive=True)


def _bash(ctx: PlugContext, args: list[str]) -> int:
    # An interactive shell session — attach stdin so `exit`/Ctrl-D ends it.
    return ctx.exec(["bash", *args], workdir=WEBROOT, interactive=True)


def _phpunit(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["./vendor/bin/phpunit", *args], workdir=WEBROOT)


def _bin(ctx: PlugContext, args: list[str]) -> int:
    if not args:
        from fincli.ui.console import error
        error("Usage: fin bin <command> [args...]", title="Invalid Argument")
        return 1
    return ctx.exec([f"./vendor/bin/{args[0]}", *args[1:]], workdir=WEBROOT)


def _php(ctx: PlugContext, args: list[str]) -> int:
    return ctx.exec(["php", *args], workdir=WEBROOT)
