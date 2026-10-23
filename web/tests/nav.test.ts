import { test } from "node:test";
import assert from "node:assert/strict";
import { formatHash, parseHash, readSaved, resolveStart, writeSaved } from "../src/nav.ts";

const mem = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }; };

test("hash round trip", () => {
  const r = { project: "prj_1", section: "shots" as const, item: "shot_9" };
  assert.deepEqual(parseHash(formatHash(r)), r);
  assert.deepEqual(parseHash("#/prj_1/nonsense"), { project: "prj_1" });
  assert.deepEqual(parseHash(""), {});
});

test("last project, section and shot are remembered per workspace and per project", () => {
  const s = mem();
  writeSaved("/ws/a", "p1", { section: "shots", shot: "sh1" }, s);
  writeSaved("/ws/a", "p2", { section: "assets", asset: "boy" }, s);
  writeSaved("/ws/b", "px", { section: "overview" }, s);
  const a = readSaved("/ws/a", s);
  assert.equal(a.project, "p2"); assert.equal(a.byProject?.p1.shot, "sh1");
  assert.equal(readSaved("/ws/b", s).project, "px");
  assert.deepEqual(readSaved("/ws/none", s), {});
  s.setItem("motionx.lastProject:/ws/old", "legacy1");                      // the earlier version's key still works
  assert.equal(readSaved("/ws/old", s).project, "legacy1");
});

test("start resolution prefers the URL, then memory, then defaults, and survives deleted things", () => {
  const saved = { project: "p1", byProject: { p1: { section: "shots" as const, shot: "sh1" } } };
  assert.deepEqual(resolveStart({}, saved, ["p1", "p2"], "p2"), { project: "p1", section: "shots", item: "sh1", notes: [] });
  assert.equal(resolveStart({ project: "p2", section: "assets", item: "boy" }, saved, ["p1", "p2"], "p2").item, "boy");
  const gone = resolveStart({}, saved, ["p2"], "p2");
  assert.equal(gone.project, "p2"); assert.equal(gone.section, "overview"); assert.equal(gone.notes.length, 1);
  assert.deepEqual(resolveStart({}, {}, [], null), { project: null, section: "overview", item: null, notes: [] });
  assert.equal(resolveStart({ section: "overview", item: "x" }, saved, ["p1"], "p1").item, null);
});
