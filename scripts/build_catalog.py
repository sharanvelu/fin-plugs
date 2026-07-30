#!/usr/bin/env python3
"""Generate catalog.json — the machine-readable index of every plug.

``fin plugs search`` reads the catalog published on GitHub Releases (an
incremental version per master build, plus the rolling ``latest`` whose asset
is always replaced), so the file must always match the plugs on disk. CI
publishes it on every push to master and rejects PRs where the committed copy
drifts; never hand-edit. The plug *files* themselves are always served from
the master branch — ``files_base_url`` records that base.

Every ``plugs/<name>.py`` is loaded through the real fincli loader and
described as::

    {"name", "type", "version", "description", "commands", "file"}

Output is deterministic — plugs sorted by name, stable key order, 2-space
indent, trailing newline, no timestamps — so regeneration is a no-op when
nothing changed.

Usage:
    python3 scripts/build_catalog.py           # rewrite catalog.json
    python3 scripts/build_catalog.py --check   # exit 1 if catalog.json is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # flat-layout fincli (fin-v2 in development)
    from fincli.plugs.loader import load_plug_file as _loader_load
except ImportError:  # released fincli: legacy dir loader with a type argument
    from fincli.plugs.base import PlugType
    from fincli.plugs.loader import load_plug_dir as _legacy_load

    def _loader_load(py):
        # The PlugType argument is a placeholder; the catalog entry records
        # the declared instance.plug_type.
        return _legacy_load(py.with_suffix(""), PlugType.APP)


REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGS_DIR = REPO_ROOT / "plugs"
CATALOG = REPO_ROOT / "catalog.json"

SCHEMA_VERSION = 1

#: Where each entry's ``file`` path resolves from. Installs always fetch plug
#: files from the master branch, no matter which catalog release is read.
FILES_BASE_URL = "https://raw.githubusercontent.com/sharanvelu/fin-plugs/master"


def build_catalog() -> str:
    """Return the catalog JSON document for the plugs currently on disk."""
    entries = []
    for path in sorted(PLUGS_DIR.glob("*.py")):
        lp = _loader_load(path)
        if lp is None:
            sys.exit(
                f"error: {path.relative_to(REPO_ROOT)} failed to load — "
                "fix the plug (see loader warning above) and rerun"
            )
        inst = lp.instance
        entries.append(
            {
                "name": inst.name,
                "type": inst.plug_type.value,
                "version": inst.version,
                "description": inst.description,
                "commands": sorted(inst.commands()),
                "file": f"plugs/{path.name}",
            }
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "files_base_url": FILES_BASE_URL,
        "plugs": entries,
    }
    return json.dumps(document, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="don't write; exit 1 if the committed catalog.json is stale",
    )
    args = parser.parse_args()

    generated = build_catalog()
    committed = CATALOG.read_text(encoding="utf-8") if CATALOG.exists() else None

    if args.check:
        if committed != generated:
            print(
                "catalog.json is out of date — regenerate it with "
                "`python3 scripts/build_catalog.py` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print("catalog.json is up to date.")
        return 0

    if committed == generated:
        print("catalog.json already up to date.")
        return 0
    CATALOG.write_text(generated, encoding="utf-8")
    print(
        f"wrote {CATALOG.relative_to(REPO_ROOT)} "
        f"({len(json.loads(generated)['plugs'])} plugs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
