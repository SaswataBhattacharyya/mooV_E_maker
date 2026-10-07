"""Persistent ECAPA identity store with project-first bounded ANN lookup.

The store persists centroids and provenance only; it never stores raw speech.
LanceDB is the preferred ANN backend. JSONL is an explicit portability fallback
and scans identity centroids (not all examples against all examples).
"""
from __future__ import annotations

import json
import math
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MODEL = "speechbrain/spkrec-ecapa-voxceleb"
MODEL_VERSION = "speechbrain-1.0.3-ecapa-voxceleb-v1"


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(float(x) ** 2 for x in vector)) or 1.0
    return [float(x) / norm for x in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return -1.0
    return sum(float(x) * float(y) for x, y in zip(_unit(a), _unit(b)))


def anonymous_alias(existing: set[str] | None = None) -> str:
    existing = existing or set()
    while True:
        alias = f"Character-{uuid.uuid4().hex[:4].upper()}"
        if alias not in existing:
            return alias


class VoiceStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.records_path = root / "identities.jsonl"
        self.audit_path = root / "decisions.jsonl"
        self.codex_audit_path = root / "codex_decisions.jsonl"
        self.links_path = root / "identity_links.jsonl"
        self.lance_path = root / "lancedb"

    def _read(self) -> list[dict[str, Any]]:
        if not self.records_path.exists():
            return []
        rows = [json.loads(line) for line in self.records_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        links = self._read_links()
        by_id = {row.get("voice_identity_id"): row for row in rows}
        for identity_id, row in by_id.items():
            canonical_id = self._resolve_link(str(identity_id), links)
            if canonical_id != identity_id and canonical_id in by_id:
                row["canonical_voice_identity_id"] = canonical_id
                row["identity_state"] = "codex_confirmed_match"
        return rows

    def _read_links(self) -> dict[str, str]:
        if not self.links_path.exists():
            return {}
        links: dict[str, str] = {}
        for line in self.links_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                links[str(record["current_identity_id"])] = str(record["canonical_identity_id"])
        return links

    @staticmethod
    def _resolve_link(identity_id: str, links: dict[str, str]) -> str:
        current, seen = identity_id, set()
        while current in links and current not in seen:
            seen.add(current)
            current = links[current]
        return current

    def _apply_links(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        links = self._read_links()
        for row in rows:
            identity_id = str(row.get("voice_identity_id", ""))
            canonical_id = self._resolve_link(identity_id, links)
            if canonical_id != identity_id:
                row["canonical_voice_identity_id"] = canonical_id
                row["identity_state"] = "codex_confirmed_match"
        return rows

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        tmp = self.records_path.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
        tmp.replace(self.records_path)

    def add_identity(self, *, project_id: str, video_id: str, speaker_id: str, embedding: list[float],
                     start_time_sec: float, end_time_sec: float, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
        rows = self._read()
        existing = next((row for row in rows if row.get("project_id") == project_id and row.get("video_id") == video_id and row.get("speaker_id") == speaker_id), None)
        if existing:
            examples = existing.setdefault("examples", [])
            repeated_example = any(item.get("video_id") == video_id
                and abs(float(item.get("start_time_sec", -1)) - float(start_time_sec)) < 0.01
                and abs(float(item.get("end_time_sec", -1)) - float(end_time_sec)) < 0.01 for item in examples)
            old_count = int(existing.get("example_count", 1))
            old = existing.get("centroid", [])
            if len(old) == len(embedding) and not repeated_example:
                existing["centroid"] = _unit([(float(a) * old_count + float(b)) / (old_count + 1) for a, b in zip(old, embedding)])
                existing["example_count"] = old_count + 1
                examples.append({"video_id": video_id, "start_time_sec": float(start_time_sec), "end_time_sec": float(end_time_sec)})
            self._write_records(rows)
            self._upsert_lance(existing)
            return existing
        identity_id = str(uuid.uuid4())
        aliases = {str(row.get("display_name")) for row in rows}
        row = {
            "voice_identity_id": identity_id, "character_id": str(uuid.uuid4()),
            "display_name": anonymous_alias(aliases), "project_id": project_id, "video_id": video_id,
            "speaker_id": speaker_id, "embedding_model": MODEL, "embedding_version": MODEL_VERSION,
            "dimension": len(embedding), "centroid": _unit(embedding), "example_count": 1,
            "examples": [{"video_id": video_id, "start_time_sec": float(start_time_sec), "end_time_sec": float(end_time_sec)}],
            "created_at": datetime.now(timezone.utc).isoformat(), "name_status": "anonymous",
            "evidence": evidence or {}, "identity_state": "unconfirmed_anonymous",
        }
        rows.append(row)
        self._write_records(rows)
        self._upsert_lance(row)
        return row

    def _upsert_lance(self, row: dict[str, Any]) -> None:
        if os.environ.get("VIDEO_AUDIO_ANALYZER_VOICE_STORE_ENABLE_LANCEDB", "0").lower() not in {"1", "true", "yes"}:
            return
        try:
            import lancedb
            db = lancedb.connect(str(self.lance_path))
            payload = [{**row, "vector": row["centroid"]}]
            if "voice_identities" not in db.table_names():
                db.create_table("voice_identities", data=payload)
            else:
                table = db.open_table("voice_identities")
                # A retry updates one centroid row by immutable identity ID;
                # it must not multiply the same identity in ANN results.
                try:
                    table.delete(f"voice_identity_id = '{row['voice_identity_id']}'")
                except Exception:
                    # Old LanceDB versions may not support delete predicates;
                    # the JSONL source of truth remains deduplicated and ANN
                    # candidates are deduplicated again at query time.
                    pass
                table.add(payload)
        except Exception:
            # JSONL remains the durable fallback and its backend is reported.
            pass

    def link_confirmed_identity(self, *, current_identity_id: str, canonical_identity_id: str,
                                decision_id: str, provenance: dict[str, Any]) -> dict[str, Any]:
        """Persist a Codex-confirmed, non-destructive alias link between UUIDs."""
        if not current_identity_id or not canonical_identity_id or current_identity_id == canonical_identity_id:
            raise ValueError("Identity links require two different immutable UUIDs")
        rows = self._read()
        current = next((row for row in rows if row.get("voice_identity_id") == current_identity_id), None)
        canonical = next((row for row in rows if row.get("voice_identity_id") == canonical_identity_id), None)
        if current is None or canonical is None:
            raise ValueError("Both current and candidate Voice Store UUIDs must exist")
        root_id = canonical.get("canonical_voice_identity_id") or canonical_identity_id
        if self._resolve_link(root_id, self._read_links()) == current_identity_id:
            raise ValueError("Identity link would create a cycle")
        record = {"current_identity_id": current_identity_id, "canonical_identity_id": root_id,
                  "decision_id": decision_id, "provenance": provenance,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        self.links_path.parent.mkdir(parents=True, exist_ok=True)
        with self.links_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        current["canonical_voice_identity_id"] = root_id
        current["identity_state"] = "codex_confirmed_match"
        current["identity_link"] = record
        return current

    def candidates(self, embedding: list[float], project_id: str, top_k: int = 8,
                   scope: str = "project_then_global", local_candidate_floor: float = 0.45) -> dict[str, Any]:
        top_k = max(1, min(int(top_k), 50))
        rows: list[dict[str, Any]] = []
        same: list[dict[str, Any]] = []
        backend = "jsonl_identity_centroid_fallback"
        global_ann: list[dict[str, Any]] | None = None
        # Preferred LanceDB path uses ANN with metadata filtering and bounded top-K.
        try:
            if os.environ.get("VIDEO_AUDIO_ANALYZER_VOICE_STORE_ENABLE_LANCEDB", "0").lower() not in {"1", "true", "yes"}:
                raise RuntimeError("LanceDB voice ANN is disabled; using bounded identity-centroid fallback")
            import lancedb
            db = lancedb.connect(str(self.lance_path))
            if "voice_identities" in db.table_names():
                table = db.open_table("voice_identities")
                same = table.search(_unit(embedding)).where(f"project_id = '{project_id.replace(chr(39), chr(39)*2)}'").limit(top_k).to_list()
                if scope != "project_only":
                    global_ann = table.search(_unit(embedding)).where(f"project_id != '{project_id.replace(chr(39), chr(39)*2)}'").limit(top_k).to_list()
                backend = "lancedb_ann"
            else:
                rows = self._read()
                same = [r for r in rows if r.get("project_id") == project_id and len(r.get("centroid", [])) == len(embedding)]
        except Exception:
            rows = self._read()
            same = [r for r in rows if r.get("project_id") == project_id and len(r.get("centroid", [])) == len(embedding)]
        same = self._deduplicate(self._apply_links(same), embedding)
        local = sorted(same, key=lambda row: -cosine(embedding, row.get("centroid", [])))[:top_k]
        if local and cosine(embedding, local[0].get("centroid", [])) >= local_candidate_floor:
            return {"scope_used": "project", "backend": backend, "top_k": top_k, "candidates": [self._candidate(r, embedding, project_id) for r in local]}
        if scope == "project_only":
            return {"scope_used": "project", "backend": backend, "top_k": top_k, "candidates": []}
        if global_ann is None:
            if not rows:
                rows = self._read()
            global_rows = [r for r in rows if r.get("project_id") != project_id and len(r.get("centroid", [])) == len(embedding)]
        else:
            global_rows = global_ann
        if global_ann is None:
            global_rows.sort(key=lambda row: -cosine(embedding, row.get("centroid", [])))
        global_rows = self._deduplicate(self._apply_links(global_rows), embedding)
        return {"scope_used": "global", "backend": backend, "top_k": top_k,
                "candidates": [self._candidate(r, embedding, project_id) for r in global_rows[:top_k]]}

    @staticmethod
    def _deduplicate(rows: list[dict[str, Any]], embedding: list[float]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            identity_id = str(row.get("voice_identity_id", ""))
            if not identity_id:
                continue
            group_id = str(row.get("canonical_voice_identity_id") or identity_id)
            prior = unique.get(group_id)
            if prior is None or cosine(embedding, row.get("centroid", [])) > cosine(embedding, prior.get("centroid", [])):
                unique[group_id] = row
        return list(unique.values())

    @staticmethod
    def _candidate(row: dict[str, Any], embedding: list[float], query_project: str) -> dict[str, Any]:
        return {"voice_identity_id": row["voice_identity_id"], "character_id": row.get("character_id"),
                "canonical_voice_identity_id": row.get("canonical_voice_identity_id", row["voice_identity_id"]),
                "display_name": row.get("display_name"), "source_project_id": row.get("project_id"),
                "source_video_id": row.get("video_id"), "similarity": cosine(embedding, row["centroid"]),
                "speaker_id": row.get("speaker_id"),
                "same_project": row.get("project_id") == query_project,
                "embedding_model": row.get("embedding_model"), "embedding_version": row.get("embedding_version"),
                "identity_evidence": {key: row.get("evidence", {}).get(key) for key in
                    ("trusted_name_match", "verified_character_id", "independent_visual_match")
                    if row.get("evidence", {}).get(key)}}

    def audit_decision(self, *, candidate: dict[str, Any], decision: str, reviewer: str,
                       project_id: str, video_id: str, timestamp_sec: float,
                       supporting_evidence: dict[str, Any], provenance: str) -> dict[str, Any]:
        if decision not in {"confirm_match", "reject_match", "keep_anonymous", "rename"}:
            raise ValueError(f"Unsupported identity decision: {decision}")
        if reviewer not in {"codex", "human_override", "test"}:
            raise ValueError("reviewer must identify an auditable decision authority")
        record = {"decision_id": str(uuid.uuid4()), "candidate_identity_id": candidate.get("voice_identity_id"),
                  "decision": decision, "reviewer": reviewer, "project_id": project_id, "video_id": video_id,
                  "timestamp_sec": float(timestamp_sec), "similarity": candidate.get("similarity"),
                  "embedding_model": candidate.get("embedding_model"), "embedding_version": candidate.get("embedding_version"),
                  "supporting_evidence": supporting_evidence, "merge_provenance": provenance,
                  "created_at": datetime.now(timezone.utc).isoformat()}
        target = self.codex_audit_path if reviewer == "codex" else self.audit_path
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record
