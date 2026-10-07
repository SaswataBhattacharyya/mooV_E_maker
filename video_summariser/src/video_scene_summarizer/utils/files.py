from __future__ import annotations

import fcntl
import json
import logging
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


LOGGER = logging.getLogger(__name__)


@contextmanager
def locked_file(path: Path, mode: str) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open(mode, encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield handle
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_unique_line(path: Path, value: str) -> bool:
    normalized = value.strip()
    if not normalized:
        return False
    with locked_file(path, "a+") as handle:
        handle.seek(0)
        existing = {line.strip() for line in handle if line.strip()}
        if normalized in existing:
            return False
        handle.seek(0, 2)
        if handle.tell() > 0:
            handle.write("\n")
        handle.write(normalized)
        return True


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def safe_delete(path: Path) -> None:
    if path.exists():
        LOGGER.info("Deleting %s", path)
        path.unlink()
