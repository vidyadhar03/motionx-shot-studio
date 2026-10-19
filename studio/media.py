"""Content-addressed media store (data/media/<sha256>.<ext>) with up-front image validation."""
from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .db import Database, now

IMAGE_MIME = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
MAX_UPLOAD_BYTES = 20_000_000


class MediaError(ValueError):
    pass


@dataclass(frozen=True)
class MediaRecord:
    sha256: str
    kind: str
    mime: str
    width: int | None
    height: int | None
    bytes: int
    rel_path: str


def _row_to_record(row: dict) -> MediaRecord:
    return MediaRecord(row["sha256"], row["kind"], row["mime"], row["width"], row["height"],
                       row["bytes"], row["rel_path"])


class MediaStore:
    def __init__(self, db: Database, root: Path):
        self.db, self.root = db, root
        root.mkdir(parents=True, exist_ok=True)

    def path(self, rec: MediaRecord) -> Path:
        return self.root / rec.rel_path

    def get(self, sha: str) -> MediaRecord | None:
        row = self.db.one("SELECT * FROM media WHERE sha256=?", sha)
        return _row_to_record(row) if row else None

    def _put(self, data: bytes, kind: str, mime: str, ext: str, width: int | None, height: int | None,
             original_name: str | None) -> MediaRecord:
        sha = hashlib.sha256(data).hexdigest()
        existing = self.get(sha)
        if existing:
            return existing
        rel = f"{sha}.{ext}"
        dest = self.root / rel
        if not dest.exists():
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
        with self.db.tx() as c:
            c.execute(
                "INSERT OR IGNORE INTO media(sha256,kind,mime,width,height,bytes,rel_path,original_name,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (sha, kind, mime, width, height, len(data), rel, original_name, now()))
        return self.get(sha)  # type: ignore[return-value]

    def put_image(self, data: bytes, original_name: str | None = None) -> MediaRecord:
        """Accepts PNG/JPEG/WEBP only. Dimension/aspect rules are checked later against the
        chosen workflow's declared capabilities, so the message can name that workflow."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise MediaError(f"image is {len(data)} bytes; the limit is {MAX_UPLOAD_BYTES}")
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                fmt, (w, h) = im.format, im.size
        except (UnidentifiedImageError, OSError) as e:
            raise MediaError(f"not a readable image: {e}") from None
        if fmt not in IMAGE_MIME:
            raise MediaError(f"image format {fmt} is not accepted; use PNG, JPEG or WEBP")
        mime, ext = IMAGE_MIME[fmt]
        return self._put(data, "image", mime, ext, w, h, original_name)

    def put_video(self, data: bytes, mime: str = "video/mp4", original_name: str | None = None) -> MediaRecord:
        ext = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}.get(mime, "bin")
        return self._put(data, "video", mime, ext, None, None, original_name)
