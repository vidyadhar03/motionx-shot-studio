"""Consolidate separate data folders into the canonical workspace, safely and repeatably.

For each source folder:
  1. Back up: a consistent SQLite copy via the backup API (includes any WAL state) plus every media file,
     into <backups>/<timestamp>/<label>/. The source folder itself is only read.
  2. Stage: open a copy of that backup with the app's Database class, so its schema is upgraded on the copy.
  3. Import, in one transaction on the target:
       - text/composite-key rows: absent -> insert with the same ids; present and identical -> skip;
         present but different -> CONFLICT (nothing is written; the run stops and lists them).
       - auto-numbered rows (take events, agent messages/tool calls/usage): matched on all columns except the
         number; absent -> inserted in source order with a new number; present -> skip.
     Media files are copied by content hash first and verified (sha256 of the bytes == the recorded hash).
     foreign_key_check must pass before COMMIT.
  4. Record the run in workspace_imports.
Running it again with the same sources inserts nothing new (no duplicate projects or accounting rows).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .db import Database, new_id, now

# Parents before children; anything not listed is refused rather than silently skipped.
TABLE_ORDER = ["projects", "media", "scenes", "assets", "asset_versions", "shots", "shot_revisions", "proposals",
               "takes", "take_events", "feedback", "decisions", "spend", "agent_threads", "agent_messages",
               "agent_tool_calls", "agent_usage", "agent_billing", "plans", "plan_revisions", "plan_links",
               "asset_requirements", "asset_version_reviews", "asset_version_restrictions", "asset_generations"]
NOT_IMPORTED = {"workspace_imports", "sqlite_sequence"}
# Media rows are content-addressed: the same sha256 is the same bytes. When two folders recorded the same file,
# only these metadata columns may differ; the first-imported row is kept and the duplicate is reported.
MEDIA_METADATA_ONLY = {"created_at", "original_name"}


class ConsolidationConflict(RuntimeError):
    def __init__(self, conflicts: list[dict]):
        super().__init__(f"{len(conflicts)} conflicting record(s); nothing was imported")
        self.conflicts = conflicts


@dataclass
class ImportReport:
    label: str
    source: str
    backup: str
    inserted: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    media_copied: int = 0
    media_present: int = 0
    resolved: list[dict] = field(default_factory=list)   # explicit duplicate resolutions (never silent)


def _sha_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _conn(path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(path, isolation_level=None)
    c.row_factory = sqlite3.Row
    return c


def _table_info(c: sqlite3.Connection, table: str) -> tuple[list[str], list[str]]:
    info = c.execute(f"PRAGMA table_info({table})").fetchall()
    cols = [r["name"] for r in info]
    pk = [r["name"] for r in sorted((r for r in info if r["pk"]), key=lambda r: r["pk"])]
    return cols, pk


def _is_serial(c: sqlite3.Connection, table: str) -> bool:
    sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()["sql"]
    return "AUTOINCREMENT" in sql.upper()


def backup_source(src_dir: Path, dest: Path) -> Path:
    """Consistent copy of <src>/studio.db (WAL included) and all media files. Returns the backup db path."""
    dest.mkdir(parents=True, exist_ok=False)
    src_db = src_dir / "studio.db"
    out = dest / "studio.db"
    s = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
    d = sqlite3.connect(out)
    try:
        s.backup(d)
    finally:
        d.close(); s.close()
    if (src_dir / "media").is_dir():
        shutil.copytree(src_dir / "media", dest / "media")
    counts = {}
    c = _conn(out)
    for (t,) in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
        counts[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    c.close()
    (dest / "BACKUP.json").write_text(json.dumps({
        "source": str(src_dir), "made_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "studio_db_sha256": _sha_file(out), "row_counts": counts,
        "media_files": sorted(p.name for p in (dest / "media").glob("*")) if (dest / "media").is_dir() else []},
        indent=2) + "\n")
    return out


def _stage(backup_db: Path, tmp: Path) -> Path:
    staged = tmp / "staged.db"
    shutil.copy2(backup_db, staged)
    Database(staged)                       # schema upgrade on the copy only
    return staged


def import_one(src_dir: Path, target_dir: Path, backup_root: Path, label: str) -> ImportReport:
    backup_db = backup_source(src_dir, backup_root / label)
    report = ImportReport(label, str(src_dir), str(backup_db.parent))
    target_dir.mkdir(parents=True, exist_ok=True)
    Database(target_dir / "studio.db")    # create/upgrade the target schema
    with tempfile.TemporaryDirectory() as tmp:
        staged = _stage(backup_db, Path(tmp))
        s, t = _conn(staged), _conn(target_dir / "studio.db")
        try:
            src_tables = {r[0] for r in s.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            unknown = src_tables - set(TABLE_ORDER) - NOT_IMPORTED
            if unknown:
                raise RuntimeError(f"source has tables this tool doesn't know how to import: {sorted(unknown)}")
            # Media files first (content-addressed, idempotent), verified against their recorded hash.
            media_root = backup_db.parent / "media"
            for m in s.execute("SELECT sha256, rel_path FROM media"):
                src_f, dst_f = media_root / m["rel_path"], target_dir / "media" / m["rel_path"]
                if not src_f.is_file():
                    raise RuntimeError(f"media file missing in backup: {m['rel_path']}")
                if _sha_file(src_f) != m["sha256"]:
                    raise RuntimeError(f"media bytes don't match their recorded hash: {m['rel_path']}")
                if dst_f.exists():
                    if _sha_file(dst_f) != m["sha256"]:
                        raise RuntimeError(f"target already has different bytes at {dst_f}")
                    report.media_present += 1
                else:
                    dst_f.parent.mkdir(parents=True, exist_ok=True)
                    tmp_f = dst_f.with_suffix(dst_f.suffix + ".importing")
                    shutil.copy2(src_f, tmp_f)
                    if _sha_file(tmp_f) != m["sha256"]:
                        raise RuntimeError(f"copy verification failed for {m['rel_path']}")
                    tmp_f.replace(dst_f)
                    report.media_copied += 1
            conflicts: list[dict] = []
            t.execute("PRAGMA foreign_keys=OFF")
            t.execute("BEGIN IMMEDIATE")
            for table in TABLE_ORDER:
                if table not in src_tables:
                    continue
                s_cols, _ = _table_info(s, table)
                t_cols, pk = _table_info(t, table)
                missing = set(s_cols) - set(t_cols)
                if missing:
                    raise RuntimeError(f"{table}: target lacks columns {sorted(missing)}")
                serial = _is_serial(t, table)
                cols = [c for c in s_cols if not (serial and c == "id")]
                ins, skip = 0, 0
                order = " ORDER BY id" if serial else ""
                for row in s.execute(f"SELECT {', '.join(s_cols)} FROM {table}{order}"):
                    vals = {c: row[c] for c in s_cols}
                    if serial:
                        where = " AND ".join(f"{c} IS ?" for c in cols)
                        hit = t.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", [vals[c] for c in cols]).fetchone()
                        if hit:
                            skip += 1
                            continue
                    else:
                        where = " AND ".join(f"{c} = ?" for c in pk)
                        cur = t.execute(f"SELECT {', '.join(s_cols)} FROM {table} WHERE {where}", [vals[c] for c in pk]).fetchone()
                        if cur is not None:
                            diff = [c for c in s_cols if cur[c] != vals[c]]
                            if diff and table == "media" and set(diff) <= MEDIA_METADATA_ONLY:
                                report.resolved.append({"table": "media", "sha256": vals["sha256"],
                                                        "kept": {c: cur[c] for c in diff},
                                                        "ignored": {c: vals[c] for c in diff},
                                                        "rule": "same content hash; kept the first-imported metadata"})
                                skip += 1
                            elif diff:
                                conflicts.append({"table": table, "key": {c: vals[c] for c in pk}, "columns": diff})
                            else:
                                skip += 1
                            continue
                    t.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                              [vals[c] for c in cols])
                    ins += 1
                report.inserted[table], report.skipped[table] = ins, skip
            if conflicts:
                t.execute("ROLLBACK")
                raise ConsolidationConflict(conflicts)
            bad = t.execute("PRAGMA foreign_key_check").fetchall()
            if bad:
                t.execute("ROLLBACK")
                raise RuntimeError(f"foreign key check failed after import: {[tuple(r) for r in bad[:5]]}")
            t.execute("INSERT INTO workspace_imports(id,source_path,source_label,backup_path,inserted,skipped,media_copied,at) "
                      "VALUES (?,?,?,?,?,?,?,?)", (new_id("imp"), str(src_dir), label, report.backup,
                                                   json.dumps(report.inserted),
                                                   json.dumps({**report.skipped, "_resolved": report.resolved}),
                                                   report.media_copied, now()))
            t.execute("COMMIT")
        finally:
            s.close(); t.close()
    return report


def verify(src_backup_db: Path, target_dir: Path) -> dict:
    """Every row of a (backed-up) source exists identically in the target; snapshots and media bytes intact."""
    with tempfile.TemporaryDirectory() as tmp:
        staged = _stage(src_backup_db, Path(tmp))
        s, t = _conn(staged), _conn(target_dir / "studio.db")
        try:
            missing, checked = [], 0
            src_tables = {r[0] for r in s.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in TABLE_ORDER:
                if table not in src_tables:
                    continue
                s_cols, pk = _table_info(s, table)
                serial = _is_serial(t, table)
                cols = [c for c in s_cols if not (serial and c == "id")]
                keys = cols if serial else pk
                cmp = cols if serial else [c for c in s_cols if not (table == "media" and c in MEDIA_METADATA_ONLY)]
                for row in s.execute(f"SELECT {', '.join(s_cols)} FROM {table}"):
                    where = " AND ".join(f"{c} IS ?" for c in cmp)
                    ok = t.execute(f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", [row[c] for c in cmp]).fetchone()
                    checked += 1
                    if not ok:
                        missing.append({"table": table, "key": {k: row[k] for k in keys[:3]}})
            bad_media = []
            for m in t.execute("SELECT sha256, rel_path FROM media"):
                f = target_dir / "media" / m["rel_path"]
                if not f.is_file() or _sha_file(f) != m["sha256"]:
                    bad_media.append(m["rel_path"])
            return {"rows_checked": checked, "missing": missing, "bad_media": bad_media,
                    "foreign_key_violations": len(t.execute("PRAGMA foreign_key_check").fetchall())}
        finally:
            s.close(); t.close()


def classify(folder: Path) -> dict:
    """Read-only signals to tell real work from rehearsals (opens the db read-only; never migrates it)."""
    c = sqlite3.connect(f"file:{folder / 'studio.db'}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    info = {
        "folder": str(folder),
        "projects": [dict(r) for r in c.execute("SELECT id, name FROM projects ORDER BY created_at")],
        "paid_takes": q("SELECT COUNT(*) FROM takes WHERE is_paid=1"),
        "fake_takes": q("SELECT COUNT(*) FROM takes WHERE adapter='fake'"),
        "spend_rows": q("SELECT COUNT(*) FROM spend") if "spend" in tables else 0,
        "live_llm_rows": q("SELECT COUNT(*) FROM agent_usage WHERE live=1") if "agent_usage" in tables else 0,
        "paid_images": q("SELECT COUNT(*) FROM asset_generations WHERE is_paid=1 AND status='succeeded'")
        if "asset_generations" in tables else 0,
    }
    c.close()
    if info["paid_takes"] or info["spend_rows"] or info["paid_images"]:
        info["class"] = "real"
    elif info["live_llm_rows"]:
        info["class"] = "test (fake video, real LLM usage)"
    else:
        info["class"] = "rehearsal (fake only)"
    return info
