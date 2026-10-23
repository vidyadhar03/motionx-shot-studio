"""Workspace tools: where it is, what older data folders contain, and consolidating them into it.

    .venv/bin/python scripts/workspace.py where
    .venv/bin/python scripts/workspace.py scan                 # classify ./data* folders (read-only)
    .venv/bin/python scripts/workspace.py consolidate --source data --source data-flyover-live
    .venv/bin/python scripts/workspace.py verify               # re-check the last consolidation's backups
    .venv/bin/python scripts/workspace.py rollback             # move the canonical workspace aside (no deletion)

Sources are only read. Backups go to <app data>/backups/<timestamp>/. Stop the app before consolidating.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.consolidate import ConsolidationConflict, classify, import_one, verify  # noqa: E402
from studio.workspace import app_data_dir, default_workspace_dir, ensure_marker  # noqa: E402


def cmd_where(_: argparse.Namespace) -> None:
    ws = default_workspace_dir()
    print("canonical workspace:", ws)
    print("  database:", ws / "studio.db", "(exists)" if (ws / "studio.db").exists() else "(not created yet)")
    print("  media:   ", ws / "media")
    print("backups:            ", app_data_dir() / "backups")


def cmd_scan(_: argparse.Namespace) -> None:
    for d in sorted(ROOT.glob("data*")):
        if (d / "studio.db").exists():
            info = classify(d)
            names = ", ".join(p["name"] for p in info["projects"]) or "-"
            print(f"{d.name:<20} {info['class']:<36} projects: {names}")
            print(f"{'':<20} paid takes {info['paid_takes']}, fake takes {info['fake_takes']}, spend rows "
                  f"{info['spend_rows']}, live LLM rows {info['live_llm_rows']}, paid images {info['paid_images']}")


def cmd_consolidate(a: argparse.Namespace) -> None:
    target = default_workspace_dir()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = app_data_dir() / "backups" / stamp
    ensure_marker(target, "canonical")
    results = []
    for src in a.source:
        src_dir = (ROOT / src).resolve() if not Path(src).is_absolute() else Path(src)
        info = classify(src_dir)
        if info["class"] != "real" and not a.include_non_real:
            sys.exit(f"{src}: classified '{info['class']}'; refusing to import it into the canonical workspace "
                     "(pass --include-non-real if you really mean it)")
        try:
            r = import_one(src_dir, target, backup_root, src_dir.name)
        except ConsolidationConflict as e:
            print(json.dumps(e.conflicts, indent=1, default=str))
            sys.exit(f"{src}: {e}. Resolve these explicitly; the canonical workspace was not changed by this source.")
        results.append(r)
        ins = {k: v for k, v in r.inserted.items() if v}
        print(f"{src}: backup {r.backup}\n  inserted {ins or 'nothing (already present)'}\n"
              f"  media copied {r.media_copied}, already present {r.media_present}")
        for x in r.resolved:
            print(f"  resolved duplicate media {x['sha256'][:12]}: kept {x['kept']}, ignored {x['ignored']}")
    print("\nverification:")
    for r in results:
        v = verify(Path(r.backup) / "studio.db", target)
        print(f"  {r.label}: rows checked {v['rows_checked']}, missing {len(v['missing'])}, bad media "
              f"{len(v['bad_media'])}, FK violations {v['foreign_key_violations']}")
        if v["missing"] or v["bad_media"] or v["foreign_key_violations"]:
            sys.exit("verification FAILED; see above")
    (backup_root / "RUN.json").write_text(json.dumps({"target": str(target), "sources": a.source,
                                                      "results": [r.__dict__ for r in results]}, indent=2) + "\n")
    print(f"\ncanonical workspace: {target}\nbackups: {backup_root}")


def cmd_verify(_: argparse.Namespace) -> None:
    target = default_workspace_dir()
    runs = sorted((app_data_dir() / "backups").glob("*/RUN.json"))
    if not runs:
        sys.exit("no consolidation runs recorded")
    run = json.loads(runs[-1].read_text())
    for r in run["results"]:
        v = verify(Path(r["backup"]) / "studio.db", target)
        print(f"{r['label']}: rows checked {v['rows_checked']}, missing {len(v['missing'])}, bad media "
              f"{len(v['bad_media'])}, FK violations {v['foreign_key_violations']}")
    c = sqlite3.connect(target / "studio.db")
    print("projects:", [r[0] for r in c.execute("SELECT name FROM projects ORDER BY created_at")])
    print("import runs recorded:", c.execute("SELECT COUNT(*) FROM workspace_imports").fetchone()[0])


def cmd_rollback(_: argparse.Namespace) -> None:
    ws = default_workspace_dir()
    if not ws.exists():
        sys.exit("no canonical workspace to roll back")
    aside = ws.with_name(f"workspace.rolled-back-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    ws.rename(aside)
    print(f"moved {ws} -> {aside}. The source folders were never changed; to use one directly, start the app with "
          "STUDIO_DATA_DIR=<folder> (isolated), or run consolidate again.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("where"); sub.add_parser("scan"); sub.add_parser("verify"); sub.add_parser("rollback")
    c = sub.add_parser("consolidate")
    c.add_argument("--source", action="append", required=True, help="a data folder (relative to the repo or absolute)")
    c.add_argument("--include-non-real", action="store_true", help="also allow test/rehearsal folders (not recommended)")
    a = ap.parse_args()
    {"where": cmd_where, "scan": cmd_scan, "consolidate": cmd_consolidate, "verify": cmd_verify,
     "rollback": cmd_rollback}[a.cmd](a)


if __name__ == "__main__":
    main()
