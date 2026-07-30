"""Repo-wide contract checks for every plug in this repository.

These enforce the invariants that nothing else catches:

* **The import rule.** ``fincli`` ships as a compiled binary embedding its own
  interpreter and the standard library but NO site-packages, so a plug may
  import only ``fincli.*`` and the stdlib. A third-party import passes on a dev
  machine (where the package happens to be installed) and then fails inside the
  shipped binary — the loader warns and silently drops the plug.
* **The declarative rule.** Plugs describe containers; they never act. No
  ``docker`` import, no ``subprocess``, no reaching into Fin's Docker-mutating
  core modules.
* **The install-URL rule.** ``fin plugs install <name>`` fetches
  ``plugs/<name>.py`` from this repo by raw URL, so every plug is exactly one
  lowercase file whose name equals the plug's declared ``name`` attribute,
  holding exactly one ``FinPlug`` subclass, with its ``plug_type`` declared
  in-class (the flat layout carries no type information).

Plus a discovery smoke check: every ``plugs/*.py`` file actually loads through
the real loader.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from fincli.plugs.base import PlugType

try:  # flat-layout fincli (fin-v2 in development)
    from fincli.plugs.loader import load_plug_file as _loader_load
except ImportError:  # released fincli: legacy dir loader with a type argument
    from fincli.plugs.loader import load_plug_dir as _legacy_load

    def _loader_load(py):
        # The PlugType argument is a placeholder — assertions use the
        # declared ``instance.plug_type``, never this value.
        return _legacy_load(py.with_suffix(""), PlugType.APP)


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGS_DIR = REPO_ROOT / "plugs"

#: Modules a plug must never import, and why.
BANNED_IMPORTS = {
    "docker": "plugs are declarative — only fincli core talks to the daemon",
    "subprocess": "plugs never shell out; delegate via ctx.exec(...)",
    "fincli.core.docker_client": "plugs must not reach the Docker client",
    "fincli.core.orchestrator": "the orchestrator acts on plugs, not vice versa",
    "fincli.core.containers": "run_container/lookup are Fin-core-only paths",
}


def plug_source_files() -> list[Path]:
    """Every plug in the repo — one single file per plug: plugs/<name>.py."""
    return sorted(PLUGS_DIR.glob("*.py"))


def load_plug_file(path: Path):
    """Load one plugs/<name>.py directly through the real loader.

    Bridges the two fincli generations: flat-layout fincli's
    ``load_plug_file`` and released fincli's legacy ``load_plug_dir``.
    """
    return _loader_load(path)


def _imported_modules(tree: ast.AST):
    """Yield (module_path, lineno) for every import in *tree*, however nested.

    ``from a.b import c`` yields both ``a.b`` and ``a.b.c`` so bans work at
    either granularity. Relative imports are skipped (a single-file plug has
    nothing to relatively import anyway).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            module = node.module or ""
            yield module, node.lineno
            for alias in node.names:
                yield f"{module}.{alias.name}", node.lineno


_SOURCE_IDS = [p.name for p in plug_source_files()]


def test_plugs_dir_is_not_empty():
    """Guard the suite itself: an empty plugs/ would silently skip everything."""
    assert plug_source_files(), f"no plugs found under {PLUGS_DIR}"


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


@pytest.mark.parametrize("path", plug_source_files(), ids=_SOURCE_IDS)
def test_exactly_one_finplug_subclass_per_file(path):
    """One installable unit per file: exactly one class extending FinPlug."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            (isinstance(base, ast.Name) and base.id == "FinPlug")
            or (isinstance(base, ast.Attribute) and base.attr == "FinPlug")
            for base in node.bases
        )
    ]
    assert len(classes) == 1, (
        f"{path.name} must define exactly one FinPlug subclass, found: {classes}"
    )


def test_every_plug_loads_through_the_real_loader():
    """No plug silently drops out (bad import, no FinPlug subclass, …)."""
    failures = [p.name for p in plug_source_files() if load_plug_file(p) is None]
    assert not failures, (
        f"Plug files exist but failed to load (see loader warnings above): {failures}"
    )


@pytest.mark.parametrize("path", plug_source_files(), ids=_SOURCE_IDS)
def test_plug_identity_matches_filename(path):
    """The install-URL contract: plugs/<name>.py is fetched by declared name."""
    assert path.stem == path.stem.lower(), (
        f"{path.name}: plug filenames must be lowercase (they become install URLs)"
    )
    lp = load_plug_file(path)
    assert lp is not None, f"{path.name} failed to load"
    inst = lp.instance
    assert inst.name == path.stem, (
        f"{path.name} declares name={inst.name!r} — filename and declared name "
        f"must match, or `fin plugs install {inst.name}` fetches the wrong file"
    )
    assert isinstance(inst.plug_type, PlugType), (
        f"{path.name} declares invalid plug_type={inst.plug_type!r}"
    )
    assert inst.version, f"{path.name} has an empty version"
    assert inst.description, f"{path.name} has an empty description"
