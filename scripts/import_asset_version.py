"""Import an image file as a NEW version of an existing asset, held for a person's review.

    .venv/bin/python scripts/import_asset_version.py --data-dir data-flyover-live --handle underpass \\
        --file "~/Downloads/Some Image.png" --provenance "User-supplied AI-generated image; ..." [--description "..."]

The bytes are stored unchanged (the media store keys them by SHA-256; embedded metadata such as C2PA is
kept) and the source file is only read. The new version is NOT made current and is NOT pinned into shots:
a person approves it in the UI (Asset preparation) or via POST /api/asset-versions/{id}/choose.
Offline: no network call. It also prints any C2PA generator strings it finds, for the provenance record.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from studio.db import Database  # noqa: E402
from studio.media import MediaStore  # noqa: E402
from studio.ops import Ops  # noqa: E402


def c2pa_hints(data: bytes) -> list[str]:
    """Readable strings from a PNG caBX (C2PA) chunk that name the generator; best effort, not verification."""
    out, i = [], 8
    while data[:8] == b"\x89PNG\r\n\x1a\n" and i < len(data):
        n = int.from_bytes(data[i:i + 4], "big")
        if data[i + 4:i + 8] == b"caBX":
            text = {s.decode() for s in re.findall(rb"[ -~]{6,}", data[i + 8:i + 8 + n])}
            out += sorted(t for t in text if re.search(r"ChatGPT|gpt-image|OpenAI|Gemini|Google|Adobe|Firefly|"
                                                        r"Midjourney|trainedAlgorithmicMedia", t))[:8]
        i += 12 + n
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", required=True, type=Path)
    ap.add_argument("--handle", required=True)
    ap.add_argument("--file", required=True, type=Path)
    ap.add_argument("--provenance", required=True)
    ap.add_argument("--description")
    a = ap.parse_args()
    src = a.file.expanduser()
    data = src.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    db = Database(a.data_dir / "studio.db")
    ops, media = Ops(db), MediaStore(db, a.data_dir / "media")
    row = db.one("SELECT id FROM assets WHERE handle=?", a.handle.lstrip("@").lower())
    if not row:
        sys.exit(f"no asset @{a.handle} in {a.data_dir}")
    rec = media.put_image(data, src.name)
    if rec.sha256 != sha or media.path(rec).read_bytes() != data:
        sys.exit("stored bytes differ from the source file; aborting")
    asset = ops.add_asset_version(row["id"], media_sha=rec.sha256, description=a.description,
                                  provenance=a.provenance, hold_for_review=True)
    v = asset["versions"][0]
    print(f"@{a.handle} v{v['version']} imported: {rec.mime} {rec.width}x{rec.height}, {rec.bytes} bytes, sha256 {sha}")
    print(f"current version stays v{asset['current_version']}; v{v['version']} review: {v['review']} (not pinned)")
    print("source file unchanged:", hashlib.sha256(src.read_bytes()).hexdigest() == sha)
    print("C2PA hints:", c2pa_hints(data) or "none found")


if __name__ == "__main__":
    main()
