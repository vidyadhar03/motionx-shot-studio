"""Read-only project overview: one light row per shot with everything the Overview and Shots strip need.

No new business rules live here. Blockers come from `Planning.video_blockers` (the same check proposal
creation enforces); take review/selection/lock state is read straight from the rows. Nothing is written.
"""
from __future__ import annotations

from .db import Database
from .ops import Ops
from .planning import Planning


def project_overview(db: Database, ops: Ops, planning: Planning, pid: str) -> dict:
    ops.get_project(pid)
    shots = []
    for s in ops.list_shots(pid):
        takes = db.all("SELECT id, number, state, review, output_sha, adapter, is_paid, parent_take_id, created_at, "
                       "finished_at FROM takes WHERE shot_id=? ORDER BY number", s["id"])
        props = db.all("SELECT id, status, est_credits, is_paid, created_by, created_at, stale_reason, shot_revision "
                       "FROM proposals WHERE shot_id=? AND status IN ('pending','stale') ORDER BY created_at DESC", s["id"])
        shots.append({"id": s["id"], "title": s["title"], "scene_id": s["scene_id"], "order_idx": s["order_idx"],
                      "mode": s["mode"], "locked": bool(s["locked"]), "revision": s["revision"],
                      "duration_s": s["duration_s"], "selected_take_id": s["selected_take_id"],
                      "takes": takes, "open_proposal": props[0] if props else None,
                      "blockers": planning.video_blockers(s["id"])})
    return {"project_id": pid, "shots": shots}
