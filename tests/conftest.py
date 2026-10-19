from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from studio.config import ROOT, Settings
from studio.db import Database
from studio.execution.fake import FakeAdapter
from studio.generation import GenerationService
from studio.media import MediaStore
from studio.ops import Ops


def png(w: int = 640, h: int = 360, color=(40, 60, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


class PaidFake(FakeAdapter):
    """Fake backend that goes through every paid-path rule (key, budget, balance) without money."""
    is_paid = True
    name = "fake"


def make_settings(tmp: Path, **over) -> Settings:
    env = {"STUDIO_DATA_DIR": str(tmp), "STUDIO_WORKFLOWS_DIR": str(ROOT / "workflows"),
           "STUDIO_ADAPTER": "fake", "STUDIO_POLL_INTERVAL_S": "0.05", "STUDIO_FAKE_JOB_SECONDS": "0.3",
           "STUDIO_FAKE_RENDER": "copy", "STUDIO_SWEEP_INTERVAL_S": "0.2",
           "STUDIO_CHARGE_SETTLE_S": "0", "STUDIO_BUDGET_CREDITS": "700", "STUDIO_MAX_PAID_ATTEMPTS": "5"}
    env.update({k: str(v) for k, v in over.items()})
    return Settings.from_env(env)


class World:
    def __init__(self, tmp: Path, *, paid: bool = False, script=None, balance=None, **over):
        self.tmp = tmp
        self.settings = make_settings(tmp, **over)
        self.db = Database(self.settings.db_path)
        self.media = MediaStore(self.db, self.settings.media_dir)
        self.ops = Ops(self.db)
        cls = PaidFake if paid else FakeAdapter
        self.adapter = cls(self.settings.workflows_dir, tmp / "fake_backend.json",
                           job_seconds=self.settings.fake_job_seconds, render="copy", script=script)
        self.balance_calls = 0
        self._balance = balance
        self.service = GenerationService(self.db, self.ops, self.media, self.adapter, self.settings,
                                         balance_fn=self._balance_fn)

    def _balance_fn(self, key):
        self.balance_calls += 1
        if self._balance is None:
            return None
        return self._balance.pop(0) if isinstance(self._balance, list) else self._balance

    def shot(self, **fields) -> dict:
        project = self.ops.create_project("Night Walk", "A short", {"tone": "quiet noir", "palette": "sodium orange, ink blue"})
        frame = self.media.put_image(png())
        return self.ops.create_shot(project["id"], {"title": "Alley", "intention": "A woman waits under a lamp",
                                                    "action": "She looks up as a car passes", "framing": "wide",
                                                    "camera_move": "push_in", "lighting": "low_key_night",
                                                    "start_frame_sha": frame.sha256, **fields})


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)
