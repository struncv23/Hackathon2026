from __future__ import annotations

import json
import os
from pathlib import Path

from .campaign import Campaign

PROGRESS_FILE = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "PyGameSachy"
    / "progress.json"
)


def load_unlocked_level() -> int:
    if not PROGRESS_FILE.exists():
        return 1

    data = _read_progress()
    level = data.get("unlocked_level")
    if level not in (1, 2):
        raise ValueError(f"Invalid unlocked level in {PROGRESS_FILE}")
    return level


def load_campaign() -> Campaign:
    if not PROGRESS_FILE.exists():
        return Campaign()
    data = _read_progress()
    return Campaign.from_dict(data.get("campaign"))


def _read_progress() -> dict[str, object]:
    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read game progress from {PROGRESS_FILE}") from error
    return data if isinstance(data, dict) else {}


def save_unlocked_level(level: int) -> None:
    if level not in (1, 2):
        raise ValueError(f"Unsupported unlocked level: {level}")

    data = _read_progress() if PROGRESS_FILE.exists() else {}
    data["unlocked_level"] = level
    _write_progress(data)


def save_campaign(campaign: Campaign) -> None:
    data = _read_progress() if PROGRESS_FILE.exists() else {}
    data["campaign"] = campaign.to_dict()
    _write_progress(data)


def _write_progress(data: dict[str, object]) -> None:
    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as error:
        raise RuntimeError(f"Cannot save game progress to {PROGRESS_FILE}") from error
