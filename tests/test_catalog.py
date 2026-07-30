"""The committed catalog.json must always match the plugs on disk.

``fin plugs search`` reads the catalog published to GitHub Releases from
master builds, so a stale catalog means wrong search results. CI enforces
this with ``scripts/build_catalog.py --check``; this test catches the same
drift locally, before a push ever happens.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _build_catalog_module():
    """Import scripts/build_catalog.py (scripts/ is not a package)."""
    path = REPO_ROOT / "scripts" / "build_catalog.py"
    spec = importlib.util.spec_from_file_location("build_catalog", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_catalog_matches_plugs_on_disk():
    committed = (REPO_ROOT / "catalog.json").read_text(encoding="utf-8")
    generated = _build_catalog_module().build_catalog()
    assert committed == generated, (
        "catalog.json is out of date with plugs/ — regenerate it with "
        "`python3 scripts/build_catalog.py` and commit the result"
    )
