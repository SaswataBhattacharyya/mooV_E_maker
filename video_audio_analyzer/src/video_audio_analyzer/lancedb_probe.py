"""Bounded LanceDB connectivity probe used by the analyzer preflight.

It runs in a child process because a native Lance/LanceDB initialization hang
must never stall a video analysis job.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def main() -> None:
    root = Path(os.environ.get("LANCE_PROBE_DIR", tempfile.mkdtemp(prefix="vaa-lance-")))
    try:
        import lancedb
        db = lancedb.connect(str(root))
        table = db.create_table("probe", data=[{"id": "probe", "vector": [0.0, 1.0]}], mode="overwrite")
        table.search([0.0, 1.0]).limit(1).to_list()
        print(json.dumps({"status": "ready", "version": getattr(lancedb, "__version__", "unknown")}))
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}))


if __name__ == "__main__":
    main()
