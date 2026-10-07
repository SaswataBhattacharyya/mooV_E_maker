#!/usr/bin/env python3
"""Trusted CLI boundary for Hermes to call Story Builder audio APIs."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = os.environ.get("STORY_BUILDER_URL", "http://127.0.0.1:3010").rstrip("/")


def request(method: str, path: str, payload=None, headers=None):
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers or ({"Content-Type": "application/json"} if body else {}))
    try:
        with urllib.request.urlopen(req, timeout=3600) as response: return json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Story Builder HTTP {exc.code}: {detail}") from exc


def multipart(fields: dict[str, str], files: dict[str, Path]):
    boundary = f"----story-builder-{uuid.uuid4().hex}"; chunks: list[bytes] = []
    for name, value in fields.items(): chunks += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()]
    for name, path in files.items():
        if not path.is_file(): raise RuntimeError(f"Input file does not exist: {path}")
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        chunks += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\nContent-Type: {mime}\r\n\r\n".encode(), path.read_bytes(), b"\r\n"]
    chunks += [f"--{boundary}--\r\n".encode()]
    return b"".join(chunks), {"Content-Type": f"multipart/form-data; boundary={boundary}"}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("action", choices=["blocks", "create-pipeline", "validate", "run", "status", "retry", "control-foley"]); parser.add_argument("--project"); parser.add_argument("--id"); parser.add_argument("--step"); parser.add_argument("--request"); args = parser.parse_args()
    payload = json.loads(Path(args.request).read_text()) if args.request else {}
    if args.action == "blocks": result = request("GET", "/api/automation/blocks")
    elif args.action == "create-pipeline": result = request("POST", f"/api/projects/{args.project}/automation/pipelines", payload)
    elif args.action == "validate": result = request("POST", f"/api/projects/{args.project}/automation/pipelines/{args.id}/validate")
    elif args.action == "run": result = request("POST", f"/api/projects/{args.project}/automation/pipelines/{args.id}/runs")
    elif args.action == "status": result = request("GET", f"/api/projects/{args.project}/automation/runs/{args.id}")
    elif args.action == "retry": result = request("POST", f"/api/projects/{args.project}/automation/runs/{args.id}/steps/{args.step}/retry")
    else:
        files = {key: Path(payload.pop(key)).resolve() for key in ("video", "reference_audio") if payload.get(key)}
        body, headers = multipart({"payload": json.dumps(payload)}, files)
        req = urllib.request.Request(BASE + f"/api/projects/{args.project}/music/control-foley/jobs", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3600) as response: result = json.loads(response.read().decode())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try: main()
    except Exception as exc: print(json.dumps({"status": "failed", "error": str(exc)})); sys.exit(1)
