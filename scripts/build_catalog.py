#!/usr/bin/env python3
"""Generate catalog.json — the machine-readable index of every plug.

``fin plugs search`` fetches ``catalog.json`` from this repo's master branch
by raw URL, so the file must always match the plugs on disk. CI regenerates
it on every push to master and rejects PRs where it drifts; never hand-edit.

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
import inspect
import json
import sys
from pathlib import Path

from fincli.plugs.base import PlugType
from fincli.plugs.loader import load_plug_dir

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGS_DIR = REPO_ROOT / "plugs"
CATALOG = REPO_ROOT / "catalog.json"

SCHEMA_VERSION = 1

#: Released fincli still takes a PlugType argument; flat-layout fincli
#: doesn't (it trusts the declared ``instance.plug_type``). Support both
#: during the transition.
_LOADER_TAKES_TYPE = "plug_type" in inspect.signature(load_plug_dir).parameters


def build_catalog() -> str:
    """Return the catalog JSON document for the plugs currently on disk."""
    entries = []
    for path in sorted(PLUGS_DIR.glob("*.py")):
        # Where the loader still takes a PlugType it's a placeholder;
        # the entry records the declared instance.plug_type.
        if _LOADER_TAKES_TYPE:
            lp = load_plug_dir(path.with_suffix(""), PlugType.APP)
        else:
            lp = load_plug_dir(path.with_suffix(""))
        if lp is None:
            sys.exit(f"error: {path.relative_to(REPO_ROOT)} failed to load — "
                     "fix the plug (see loader warning above) and rerun")
        inst = lp.instance
        entries.append({
            "name": inst.name,
            "type": inst.plug_type.value,
            "version": inst.version,
            "description": inst.description,
            "commands": sorted(inst.commands()),
            "file": f"plugs/{path.name}",
        })
    document = {"schema_version": SCHEMA_VERSION, "plugs": entries}
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
    print(f"wrote {CATALOG.relative_to(REPO_ROOT)} "
          f"({len(json.loads(generated)['plugs'])} plugs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
