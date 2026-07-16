"""Repo-wide contract checks for every plug in this repository.

These enforce the two invariants that nothing else catches:

* **The import rule.** ``fincli`` ships as a compiled binary embedding its own
  interpreter and the standard library but NO site-packages, so a plug may
  import only ``fincli.*`` and the stdlib. A third-party import passes on a dev
  machine (where the package happens to be installed) and then fails inside the
  shipped binary — the loader warns and silently drops the plug.
* **The declarative rule.** Plugs describe containers; they never act. No
  ``docker`` import, no ``subprocess``, no reaching into Fin's Docker-mutating
  core modules.

Plus discovery smoke checks: every plug directory actually loads through the
real loader, and its declared identity matches its location on disk.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from fincli.config import Config
from fincli.plugs.loader import load_all

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Modules a plug must never import, and why.
BANNED_IMPORTS = {
    "docker": "plugs are declarative — only fincli core talks to the daemon",
    "subprocess": "plugs never shell out; delegate via ctx.exec(...)",
    "fincli.core.docker_client": "plugs must not reach the Docker client",
    "fincli.core.orchestrator": "the orchestrator acts on plugs, not vice versa",
    "fincli.core.containers": "run_container/lookup are Fin-core-only paths",
}


def plug_packages() -> list[Path]:
    """Every plug package dir (or single-file plug) under App/Asset/Global."""
    found = []
    for type_sub in Config.PLUG_TYPE_DIRS.values():
        type_dir = REPO_ROOT / type_sub
        if not type_dir.is_dir():
            continue
        for child in sorted(type_dir.iterdir()):
            if child.name.startswith((".", "_")):
                continue
            if child.is_dir() or child.suffix == ".py":
                found.append(child)
    return found


def plug_source_files() -> list[Path]:
    """Every .py file belonging to a plug."""
    files: list[Path] = []
    for pkg in plug_packages():
        files.extend(sorted(pkg.rglob("*.py")) if pkg.is_dir() else [pkg])
    return files


def _imported_modules(tree: ast.AST):
    """Yield (module_path, lineno) for every import in *tree*, however nested.

    ``from a.b import c`` yields both ``a.b`` and ``a.b.c`` so bans work at
    either granularity. Relative imports (within the plug package) are skipped.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside the plug package
                continue
            module = node.module or ""
            yield module, node.lineno
            for alias in node.names:
                yield f"{module}.{alias.name}", node.lineno


_SOURCE_IDS = [str(p.relative_to(REPO_ROOT)) for p in plug_source_files()]


@pytest.mark.parametrize("path", plug_source_files(), ids=_SOURCE_IDS)
def test_plug_imports_only_fincli_and_stdlib(path):
    """The compiled-binary import rule: fincli.* + standard library, nothing else."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = sorted(
        {
            f"line {lineno}: '{module}'"
            for module, lineno in _imported_modules(tree)
            if module.split(".")[0] not in sys.stdlib_module_names
            and module.split(".")[0] != "fincli"
        }
    )
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} imports outside fincli/stdlib "
        f"(unavailable inside the compiled fin binary): {offenders}"
    )


@pytest.mark.parametrize("path", plug_source_files(), ids=_SOURCE_IDS)
def test_plug_never_touches_docker(path):
    """The declarative rule: describe containers, never act on the daemon."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for module, lineno in _imported_modules(tree):
        for banned, why in BANNED_IMPORTS.items():
            if module == banned or module.startswith(banned + "."):
                offenders.append(f"line {lineno}: '{module}' — {why}")
    assert not offenders, f"{path.relative_to(REPO_ROOT)}: {sorted(set(offenders))}"


def test_every_plug_loads_through_the_real_loader(monkeypatch):
    """No plug silently drops out of discovery (bad import, no FinPlug subclass, …)."""
    monkeypatch.setattr(Config, "PLUGS_DIR", REPO_ROOT)
    loaded = {lp.name: lp for lp in load_all()}
    expected = {pkg.stem for pkg in plug_packages()}
    missing = expected - set(loaded)
    assert not missing, (
        f"Plug dirs exist but failed to load (see loader warnings above): {sorted(missing)}"
    )


def test_plug_identity_matches_location(monkeypatch):
    """Declared name == directory name; declared plug_type == type directory."""
    monkeypatch.setattr(Config, "PLUGS_DIR", REPO_ROOT)
    for lp in load_all():
        assert lp.instance.name == lp.path.stem, (
            f"plug at {lp.path.name}/ declares name={lp.instance.name!r}"
        )
        expected_dir = Config.PLUG_TYPE_DIRS[lp.instance.plug_type.value]
        assert lp.path.parent.name == expected_dir, (
            f"{lp.name} declares {lp.instance.plug_type.value} but lives in "
            f"{lp.path.parent.name}/"
        )
        assert lp.instance.version, f"{lp.name} has an empty version"
        assert lp.instance.description, f"{lp.name} has an empty description"
