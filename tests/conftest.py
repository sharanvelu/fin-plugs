"""Shared pytest fixtures for the fin-plugs test suite.

The suite loads the *real* plugs in this repo through the real fincli loader
(tests point ``Config.PLUGS_DIR`` at the repo root — see ``REPO_ROOT``), but is
otherwise hermetic: it must NEVER touch a real Docker daemon or the developer's
real ``~/.fin`` data dir. Two autouse mechanisms enforce that:

* ``reset_docker_singleton`` clears ``DockerService._instance`` and ``_client``
  before *and* after every test, so a mocked client from one test never leaks
  into the next.
* ``isolate_config`` re-points ``Config.DATA_DIR`` / ``CONFIG_FILE`` /
  ``REGISTRY_DB`` at a per-test tmp dir, so nothing can clobber a developer's
  real ``~/.fin``.

Requires ``fincli`` to be importable — install the tool editable once:
``python3 -m pip install --user -e /Users/sharan/Projects/05-DockR/fin-v2``.

Fixtures mirrored from ``fin-v2/tests/conftest.py`` so the plug tests here stay
drop-in compatible with the tool's suite.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from fincli.config import Config
from fincli.core import docker_client as docker_client_mod

#: This repository's root — a valid PLUGS_DIR tree (App/ Asset/ Global/).
REPO_ROOT = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Fake docker SDK objects
# --------------------------------------------------------------------------- #
def make_fake_container(
    *,
    name: str = "demo-web",
    status: str = "running",
    id: str = "abc123def456",
    short_id: str | None = None,
    image_tags: list[str] | None = None,
    labels: dict[str, str] | None = None,
    attrs: dict | None = None,
) -> MagicMock:
    """Build a MagicMock that quacks like a docker-py Container.

    Exposes the attributes Fin reads: ``.name``, ``.status``, ``.id``,
    ``.short_id``, ``.image.tags``, ``.attrs`` (with Config/Labels and
    NetworkSettings/Ports), and stubbed action methods (start/stop/remove/
    exec_run/logs/stats).
    """
    c = MagicMock(name=f"container::{name}")
    c.name = name
    c.status = status
    c.id = id
    c.short_id = short_id if short_id is not None else id[:12]

    image = MagicMock()
    image.tags = image_tags if image_tags is not None else ["demo:latest"]
    c.image = image

    base_attrs = {
        "Config": {"Labels": labels or {"FIN_MANAGED": "true", "FIN_SERVICE": "web"}},
        "NetworkSettings": {"Ports": {}},
        "Created": "2026-06-14T10:00:00Z",
    }
    if attrs:
        base_attrs.update(attrs)
    c.attrs = base_attrs

    # exec_run: when stream=True docker-py returns (exit_code, output_gen).
    c.exec_run.return_value = (0, iter([b"ok\n"]))
    c.logs.return_value = b"log line\n"
    c.stats.return_value = {}
    return c


@pytest.fixture
def fake_container():
    return make_fake_container


# --------------------------------------------------------------------------- #
# Autouse isolation
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def reset_docker_singleton():
    """Clear the DockerService singleton before and after every test."""
    docker_client_mod.DockerService._instance = None
    yield
    svc = docker_client_mod.DockerService._instance
    if svc is not None and getattr(svc, "_client", None) is not None:
        # Don't call a possibly-mock close in a way that errors.
        svc._client = None
    docker_client_mod.DockerService._instance = None


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    """Point all Config paths at a per-test tmp dir.

    Guards against tests writing to the developer's real ~/.fin. PLUGS_DIR
    defaults to an empty tmp tree; plug-loading tests override it (see the
    ``bundled_plugs`` fixture in test_bundled_plugs.py, which points it at
    this repo's root).
    """
    data_dir = tmp_path / "fin-data"
    monkeypatch.setattr(Config, "DATA_DIR", data_dir)
    monkeypatch.setattr(Config, "CONFIG_FILE", data_dir / "config.json")
    monkeypatch.setattr(Config, "REGISTRY_DB", data_dir / "registry.db")
    plugs_dir = tmp_path / "plugs-empty"
    plugs_dir.mkdir()
    monkeypatch.setattr(Config, "PLUGS_DIR", plugs_dir)
    yield


# --------------------------------------------------------------------------- #
# Plug-tree helpers
# --------------------------------------------------------------------------- #
def write_plug(
    plugs_dir: Path,
    *,
    type_sub: str,
    name: str,
    class_name: str,
    plug_type: str,
    version: str = "1.0.0",
    description: str = "",
    body_extra: str = "",
) -> Path:
    """Write a minimal FinPlug package under ``plugs_dir/<type_sub>/<name>``.

    Returns the package directory path.
    """
    pkg = plugs_dir / type_sub / name
    pkg.mkdir(parents=True, exist_ok=True)
    source = f'''
from fincli.plugs.base import FinPlug, PlugType, PlugCommand


class {class_name}(FinPlug):
    name = "{name}"
    version = "{version}"
    plug_type = PlugType.{plug_type}
    description = "{description}"
{body_extra}
'''
    (pkg / "__init__.py").write_text(source, encoding="utf-8")
    return pkg


@pytest.fixture
def plug_factory():
    """Return the ``write_plug`` helper for building temp plugs."""
    return write_plug
