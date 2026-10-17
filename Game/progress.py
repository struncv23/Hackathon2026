from __future__ import annotations

import json
import os
from pathlib import Path

PROGRESS_FILE = (
    Path(os.environ.get("LOCALAPPDATA", Path.home()))
    / "PyGameSachy"
    / "progress.json"
)


def load_unlocked_level() -> int:
    if not PROGRESS_FILE.exists():
        return 1

    try:
        data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Cannot read game progress from {PROGRESS_FILE}") from error

    level = data.get("unlocked_level") if isinstance(data, dict) else None
    if level not in (1, 2):
        raise ValueError(f"Invalid unlocked level in {PROGRESS_FILE}")
    return level


def save_unlocked_level(level: int) -> None:
    if level not in (1, 2):
        raise ValueError(f"Unsupported unlocked level: {level}")

    try:
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_FILE.write_text(
            json.dumps({"unlocked_level": level}, indent=2),
            encoding="utf-8",
        )
    except OSError as error:
        raise RuntimeError(f"Cannot save game progress to {PROGRESS_FILE}") from error
