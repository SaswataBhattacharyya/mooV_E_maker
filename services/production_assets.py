"""Project-scoped production asset registry with safe one-copy ownership."""
from __future__ import annotations

import hashlib
import fcntl
import inspect
from functools import wraps
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


ROLE_KINDS = {
    "image_candidate": "image",
    "character_master": "image", "character_angle": "image", "expression": "image",
    "costume_state": "image", "world_master": "image", "location_angle": "image",
    "lighting_state": "image", "prop": "image", "scene_board": "image",
    "first_frame": "image", "last_frame": "image", "keyframe": "image",
    "action_reference_video": "video", "previous_cut_tail": "video",
    "voice_master": "audio", "voice_excerpt": "audio", "dialogue_take": "audio",
    "music_candidate": "audio", "sfx_candidate": "audio", "h3_native_audio": "audio",
    "project_video": "video", "project_audio": "audio", "project_image": "image",
}
SUFFIX_KIND = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
    ".mp4": "video", ".mov": "video", ".mkv": "video", ".webm": "video",
    ".wav": "audio", ".mp3": "audio", ".m4a": "audio", ".ogg": "audio",
    ".flac": "audio", ".aac": "audio",
}
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_IMAGE_PIXELS = 80_000_000
ID_PATTERN = re.compile(r"pa-[a-f0-9]{16}")


class ProductionAssetError(ValueError):
    def __init__(self, code: str, message: str, *, asset_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.asset_id = asset_id

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": str(self)}
        if self.asset_id:
            result["asset_id"] = self.asset_id
        return result


def _validate_project_id(project_id: str) -> None:
    if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", project_id):
        raise ProductionAssetError("invalid_project_id", "Project identifier has an invalid format.")


def project_root(storage_projects_root: Path, project_id: str) -> Path:
    _validate_project_id(project_id)
    root = Path(storage_projects_root).resolve()
    target = (root / project_id).resolve()
    if not target.is_relative_to(root):
        raise ProductionAssetError("unsafe_project_path", "Project path escapes the configured storage root.")
    return target


def _manifest_path(root: Path) -> Path:
    return root / "production" / "assets.json"


def _serialized_mutation(function):
    """Lock the whole read/modify/write transaction, including byte ownership."""
    signature = inspect.signature(function)
    @wraps(function)
    def locked(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        root = project_root(bound.arguments["storage_projects_root"], bound.arguments["project_id"])
        directory = root / "production"
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / ".assets.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                return function(*args, **kwargs)
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return locked


def _read_manifest(root: Path) -> dict[str, Any]:
    path = _manifest_path(root)
    if not path.exists():
        return {"schema_version": 1, "assets": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionAssetError("asset_manifest_corrupt", f"Project asset manifest could not be read: {exc}") from exc
    if value.get("schema_version") != 1 or not isinstance(value.get("assets"), list):
        raise ProductionAssetError("asset_manifest_invalid", "Project asset manifest has an unsupported schema.")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(prefix=".production-assets-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _signature_kind(data: bytes, suffix: str) -> str | None:
    if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image"
    if suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"):
        return "image"
    if suffix == ".webp" and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"
    if suffix in {".mp4", ".mov", ".m4a", ".aac"} and len(data) >= 12 and data[4:8] == b"ftyp":
        return "video" if suffix in {".mp4", ".mov"} else "audio"
    if suffix == ".wav" and data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio"
    if suffix == ".flac" and data.startswith(b"fLaC"):
        return "audio"
    if suffix == ".ogg" and data.startswith(b"OggS"):
        return "audio"
    if suffix == ".mp3" and (data.startswith(b"ID3") or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0)):
        return "audio"
    if suffix in {".mkv", ".webm"} and data.startswith(b"\x1aE\xdf\xa3"):
        return "video"
    return None


def _probe_media(path: Path, kind: str) -> dict[str, Any]:
    if kind == "image":
        try:
            from PIL import Image
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
        except Exception as exc:
            raise ProductionAssetError("invalid_image", f"Image could not be verified: {exc}") from exc
        if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
            raise ProductionAssetError("image_dimensions_unsupported", f"Image dimensions are invalid or exceed {MAX_IMAGE_PIXELS} pixels.")
        return {"width": width, "height": height}
    command = ["ffprobe", "-v", "error", "-show_entries", "format=duration,format_name:stream=codec_type,codec_name,width,height,sample_rate,channels", "-of", "json", str(path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        if completed.returncode != 0:
            raise ProductionAssetError("media_probe_failed", f"ffprobe rejected this media: {completed.stderr[:300]}")
        data = json.loads(completed.stdout)
    except subprocess.TimeoutExpired as exc:
        raise ProductionAssetError("media_probe_timeout", "Media validation exceeded 30 seconds.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionAssetError("media_probe_unavailable", f"Could not validate media with ffprobe: {exc}") from exc
    streams = data.get("streams", [])
    actual_kind = "video" if any(row.get("codec_type") == "video" for row in streams) else "audio" if any(row.get("codec_type") == "audio" for row in streams) else None
    if actual_kind != kind:
        raise ProductionAssetError("media_type_mismatch", f"File extension indicates {kind}, but probed streams indicate {actual_kind or 'no audio/video stream'}.")
    format_data = data.get("format", {})
    return {"duration_seconds": float(format_data["duration"]) if format_data.get("duration") else None,
            "format": format_data.get("format_name"),
            "streams": [{key: row.get(key) for key in ("codec_type", "codec_name", "width", "height", "sample_rate", "channels")} for row in streams]}


def probe_media(path: Path, kind: str) -> dict[str, Any]:
    """Public, typed media probe shared with production validation adapters."""
    if kind not in {"image", "audio", "video"}:
        raise ProductionAssetError("invalid_media_kind", "Media probe kind must be image, audio, or video.")
    return _probe_media(Path(path), kind)


def _public(record: dict[str, Any], project_id: str) -> dict[str, Any]:
    safe = {key: value for key, value in record.items() if key not in {"relative_path", "external_content_url"}}
    if str(record.get("source", "")).startswith("external_video_repertoire_"):
        safe["content_url"] = record.get("external_content_url")
    else:
        safe["content_url"] = f"/api/projects/{project_id}/production/v2/assets/{record['asset_id']}/content"
    return safe


def list_assets(storage_projects_root: Path, project_id: str, *, kind: str | None = None,
                role: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    root = project_root(storage_projects_root, project_id)
    if kind is not None and kind not in {"image", "video", "audio"}:
        raise ProductionAssetError("invalid_asset_filter", "kind must be image, video, or audio.")
    if not 1 <= limit <= 100 or offset < 0:
        raise ProductionAssetError("invalid_pagination", "limit must be 1–100 and offset must be non-negative.")
    assets = _read_manifest(root)["assets"]
    filtered = [row for row in assets if (kind is None or row.get("kind") == kind)
                and (role is None or role in row.get("roles", []))]
    filtered.sort(key=lambda row: row.get("created_at", ""), reverse=True)
    page = [_public(row, project_id) for row in filtered[offset:offset + limit]]
    return {"assets": page, "total": len(filtered), "limit": limit, "offset": offset}


@_serialized_mutation
def register_upload(storage_projects_root: Path, project_id: str, *, filename: str, content: bytes,
                    role: str, provenance_notes: str = "",
                    metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    root = project_root(storage_projects_root, project_id)
    if role not in ROLE_KINDS:
        raise ProductionAssetError("invalid_asset_role", f"Unsupported project asset role {role!r}.")
    if not isinstance(content, bytes) or not content:
        raise ProductionAssetError("empty_asset", "Uploaded asset is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ProductionAssetError("asset_too_large", f"Uploaded asset exceeds {MAX_UPLOAD_BYTES} bytes.")
    safe_name = Path(filename or "").name
    suffix = Path(safe_name).suffix.lower()
    kind = SUFFIX_KIND.get(suffix)
    if kind is None:
        raise ProductionAssetError("unsupported_asset_format", "Supported uploads are PNG/JPEG/WEBP, MP4/MOV/MKV/WEBM, and WAV/MP3/M4A/OGG/FLAC/AAC.")
    if ROLE_KINDS[role] != kind and role not in {f"project_{kind}"}:
        raise ProductionAssetError("asset_role_type_mismatch", f"Role {role!r} requires {ROLE_KINDS[role]} media, not {kind}.")
    if _signature_kind(content[:32], suffix) != kind:
        raise ProductionAssetError("asset_signature_mismatch", "File bytes do not match the declared extension/media kind.")
    digest = hashlib.sha256(content).hexdigest()
    metadata = {} if metadata is None else metadata
    if not isinstance(metadata, dict) or len(json.dumps(metadata, ensure_ascii=False)) > 16_000:
        raise ProductionAssetError("asset_metadata_invalid", "Asset metadata must be an object no larger than 16 KB.")
    manifest = _read_manifest(root)
    for record in manifest["assets"]:
        if record.get("sha256") == digest and record.get("source") == "project_upload":
            roles = list(record.get("roles", []))
            changed = False
            if role not in roles:
                roles.append(role)
                record["roles"] = roles
                changed = True
            existing_metadata = record.setdefault("metadata", {})
            if not isinstance(existing_metadata, dict):
                existing_metadata = {}
                record["metadata"] = existing_metadata
            for key, value in metadata.items():
                if key in existing_metadata and existing_metadata[key] != value:
                    raise ProductionAssetError("asset_metadata_conflict",
                        "Identical uploaded bytes already have different structured metadata; use a distinct recording file.")
                existing_metadata[key] = value
                changed = True
            if changed:
                _atomic_json(_manifest_path(root), manifest)
            return {**_public(record, project_id), "deduplicated": True}
    asset_id = f"pa-{uuid.uuid4().hex[:16]}"
    inputs_root = (root / "inputs" / "production_assets").resolve()
    inputs_root.mkdir(parents=True, exist_ok=True)
    target = (inputs_root / f"{asset_id}{suffix}").resolve()
    if not target.is_relative_to(root.resolve()):
        raise ProductionAssetError("unsafe_asset_path", "Asset upload path escapes its project root.")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{asset_id}-", suffix=".tmp", dir=inputs_root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    try:
        media = _probe_media(target, kind)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    record = {"asset_id": asset_id, "project_id": project_id, "kind": kind, "roles": [role],
              "filename": safe_name, "media_type": mimetypes.guess_type(safe_name)[0] or "application/octet-stream",
              "sha256": digest, "size_bytes": len(content), "source": "project_upload",
              "relative_path": target.relative_to(root.resolve()).as_posix(), "media": media,
              "metadata": metadata,
              "provenance_notes": str(provenance_notes or "")[:2000],
              "created_at": datetime.now(timezone.utc).isoformat()}
    manifest["assets"].append(record)
    _atomic_json(_manifest_path(root), manifest)
    return {**_public(record, project_id), "deduplicated": False}


@_serialized_mutation
def register_output(storage_projects_root: Path, output_root: Path, project_id: str, *,
                    relative_path: str, role: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Index an existing generated output without copying or accepting absolute paths."""
    root = project_root(storage_projects_root, project_id)
    if role not in ROLE_KINDS:
        raise ProductionAssetError("invalid_asset_role", f"Unsupported project asset role {role!r}.")
    project_output = (Path(output_root).resolve() / project_id).resolve()
    candidate = (project_output / relative_path).resolve()
    if not candidate.is_relative_to(project_output) or not candidate.is_file():
        raise ProductionAssetError("asset_output_not_found", "Generated asset path is missing or outside this project's output directory.")
    suffix = candidate.suffix.lower()
    kind = SUFFIX_KIND.get(suffix)
    if kind != ROLE_KINDS[role] and role != f"project_{kind}":
        raise ProductionAssetError("asset_role_type_mismatch", "Generated output format does not match the requested asset role.")
    digest = _sha256_file(candidate)
    metadata = {} if metadata is None else metadata
    if not isinstance(metadata, dict) or len(json.dumps(metadata, ensure_ascii=False)) > 16_000:
        raise ProductionAssetError("asset_metadata_invalid", "Asset metadata must be an object no larger than 16 KB.")
    manifest = _read_manifest(root)
    canonical = None
    for record in list(manifest["assets"]):
        if record.get("sha256") == digest and record.get("source") == "project_output":
            canonical = canonical or record
            if record.get("metadata", {}) != metadata:
                continue
            if role not in record["roles"]:
                record["roles"].append(role)
                _atomic_json(_manifest_path(root), manifest)
            return {**_public(record, project_id), "deduplicated": True}
    asset_id = f"pa-{uuid.uuid4().hex[:16]}"
    record = {"asset_id": asset_id, "project_id": project_id, "kind": kind, "roles": [role],
              "filename": candidate.name, "media_type": mimetypes.guess_type(candidate.name)[0] or "application/octet-stream",
              "sha256": digest, "size_bytes": candidate.stat().st_size, "source": "project_output",
              "relative_path": candidate.relative_to(project_output).as_posix(), "media": _probe_media(candidate, kind),
              "metadata": metadata or {}, "created_at": datetime.now(timezone.utc).isoformat()}
    if canonical is not None:
        # Distinct attempts keep distinct provenance while sharing one byte owner.
        for key in ("relative_path", "filename", "media_type", "media", "size_bytes"):
            record[key] = canonical[key]
    manifest["assets"].append(record)
    _atomic_json(_manifest_path(root), manifest)
    return {**_public(record, project_id), "deduplicated": canonical is not None}


@_serialized_mutation
def accept_image_candidate(storage_projects_root: Path, project_id: str, asset_id: str, *,
                           role: str, actor: str = "user", entity_id: str | None = None) -> dict[str, Any]:
    """Add an approved production role to an existing image candidate, without copying bytes."""
    root = project_root(storage_projects_root, project_id)
    if role not in ROLE_KINDS or ROLE_KINDS[role] != "image" or role == "image_candidate":
        raise ProductionAssetError("invalid_candidate_role", "An accepted image must be promoted to a registered non-candidate image role.")
    if not ID_PATTERN.fullmatch(asset_id):
        raise ProductionAssetError("asset_not_found", "Project image candidate was not found.", asset_id=asset_id)
    manifest = _read_manifest(root)
    record = next((row for row in manifest["assets"] if row.get("asset_id") == asset_id), None)
    if record is None or record.get("kind") != "image" or "image_candidate" not in record.get("roles", []):
        raise ProductionAssetError("not_an_image_candidate", "Only a registered project image candidate can be accepted.", asset_id=asset_id)
    if record.get("source") != "project_output":
        raise ProductionAssetError("candidate_source_invalid", "Only generated project-output images can be promoted.", asset_id=asset_id)
    metadata = record.setdefault("metadata", {})
    job = metadata.get("production_image_job")
    if not isinstance(job, dict) or job.get("status") != "completed":
        raise ProductionAssetError("candidate_job_incomplete", "The candidate's durable image job must be completed before acceptance.", asset_id=asset_id)
    if role not in record["roles"]:
        record["roles"].append(role)
    if entity_id is not None:
        if role not in {"character_master", "world_master"} or not str(entity_id).strip():
            raise ProductionAssetError("master_identity_invalid", "Only character/world master acceptance can include a canon identity.", asset_id=asset_id)
        identity_field = "character_id" if role == "character_master" else "world_id"
        existing_identity = metadata.get(identity_field)
        if existing_identity and existing_identity != entity_id:
            raise ProductionAssetError("master_identity_conflict", "This master already belongs to a different canon identity; register a separate asset.", asset_id=asset_id)
        metadata[identity_field] = str(entity_id)
    job["accepted"] = True
    metadata["approval_status"] = "accepted"
    job["accepted_role"] = role
    job["accepted_by"] = str(actor)[:80]
    job["accepted_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(_manifest_path(root), manifest)
    return {**_public(record, project_id), "deduplicated": True}


@_serialized_mutation
def link_repertoire_asset(storage_projects_root: Path, project_id: str, *,
                          repertoire_kind: str, external_asset_id: str,
                          get_video_asset: Callable[[str], dict[str, Any]],
                          get_audio_assets: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    """Persist an ID-only pointer to shared Video Repertoire media, never copy it."""
    root = project_root(storage_projects_root, project_id)
    if repertoire_kind == "video":
        source = get_video_asset(external_asset_id)
        content_url = f"/api/video-repertoire/assets/{external_asset_id}/content"
        kind = "video"
        roles = ["action_reference_video"]
        label = source.get("title") or source.get("filename") or external_asset_id
    elif repertoire_kind == "audio":
        source = next((row for row in get_audio_assets() if row.get("asset_id") == external_asset_id and row.get("available")), None)
        if source is None:
            raise ProductionAssetError("repertoire_asset_not_found", "Selected Video Repertoire audio asset is missing or unavailable.")
        content_url = source.get("content_url")
        kind = "audio"
        roles = [str(source.get("category") or "project_audio")]
        label = source.get("label") or source.get("filename") or external_asset_id
    else:
        raise ProductionAssetError("invalid_repertoire_kind", "repertoire_kind must be video or audio.")
    link_id = "pa-" + hashlib.sha256(f"{repertoire_kind}:{external_asset_id}".encode()).hexdigest()[:16]
    manifest = _read_manifest(root)
    for row in manifest["assets"]:
        if row.get("asset_id") == link_id:
            return {**_public(row, project_id), "deduplicated": True}
    record = {"asset_id": link_id, "project_id": project_id, "kind": kind, "roles": roles,
              "filename": str(source.get("filename") or label), "source": f"external_video_repertoire_{repertoire_kind}",
              "external_asset_id": external_asset_id, "external_content_url": content_url,
              "source_label": str(label), "sha256": source.get("sha256"), "size_bytes": source.get("size", 0),
              "media": source.get("media", {}),
              "created_at": datetime.now(timezone.utc).isoformat()}
    manifest["assets"].append(record)
    _atomic_json(_manifest_path(root), manifest)
    return {**_public(record, project_id), "deduplicated": False}


def resolve_content(storage_projects_root: Path, output_root: Path, project_id: str, asset_id: str) -> tuple[Path, str, str]:
    root = project_root(storage_projects_root, project_id)
    if not ID_PATTERN.fullmatch(asset_id):
        raise ProductionAssetError("asset_not_found", "Project asset was not found.", asset_id=asset_id)
    manifest = _read_manifest(root)
    record = next((row for row in manifest["assets"] if row.get("asset_id") == asset_id), None)
    if record is None:
        raise ProductionAssetError("asset_not_found", "Project asset was not found.", asset_id=asset_id)
    source = record.get("source")
    if source == "project_upload":
        allowed_root = (root / "inputs" / "production_assets").resolve()
        path = (root / str(record.get("relative_path", ""))).resolve()
        if not path.is_relative_to(allowed_root):
            raise ProductionAssetError("unsafe_asset_path", "Uploaded asset record points outside its allowed input directory.", asset_id=asset_id)
    elif source == "project_output":
        allowed_root = (Path(output_root).resolve() / project_id).resolve()
        path = (allowed_root / str(record.get("relative_path", ""))).resolve()
        if not path.is_relative_to(allowed_root):
            raise ProductionAssetError("unsafe_asset_path", "Generated asset record points outside its project output directory.", asset_id=asset_id)
    elif str(source).startswith("external_video_repertoire_"):
        raise ProductionAssetError("external_asset_content", "External assets are served by their owning Video Repertoire content route; they are not copied into project storage.", asset_id=asset_id)
    else:
        raise ProductionAssetError("asset_source_invalid", "Asset record has an unknown storage owner.", asset_id=asset_id)
    if not path.is_file():
        raise ProductionAssetError("asset_file_missing", "Registered project asset file is missing.", asset_id=asset_id)
    return path, str(record.get("media_type") or "application/octet-stream"), str(record.get("filename") or path.name)


@_serialized_mutation
def assign_master_identity(storage_projects_root: Path, project_id: str, asset_id: str, *, role: str, entity_id: str) -> dict[str, Any]:
    """Bind a master to its canon identity once; changing it requires a new asset."""
    if role not in {"character_master", "world_master"} or not entity_id:
        raise ProductionAssetError("master_identity_invalid", "Select a character or world for this master.")
    root = project_root(storage_projects_root, project_id)
    manifest = _read_manifest(root)
    record = next((row for row in manifest["assets"] if row.get("asset_id") == asset_id), None)
    if not record or record.get("kind") != "image" or role not in record.get("roles", []):
        raise ProductionAssetError("asset_role_type_mismatch", "Only a registered master image can be assigned this identity.")
    field = "character_id" if role == "character_master" else "world_id"
    metadata = record.setdefault("metadata", {})
    if metadata.get(field) and metadata[field] != entity_id:
        raise ProductionAssetError("master_identity_conflict", "This master already belongs to a different canon identity; register a separate asset.")
    metadata[field] = entity_id
    _atomic_json(_manifest_path(root), manifest)
    return _public(record, project_id)


def get_asset_record(storage_projects_root: Path, project_id: str, asset_id: str) -> dict[str, Any]:
    """Return one project-scoped private record for backend validation only."""
    root = project_root(storage_projects_root, project_id)
    if not isinstance(asset_id, str) or not ID_PATTERN.fullmatch(asset_id):
        raise ProductionAssetError("asset_not_found", "Project asset was not found.", asset_id=str(asset_id))
    record = next((row for row in _read_manifest(root)["assets"] if row.get("asset_id") == asset_id), None)
    if record is None:
        raise ProductionAssetError("asset_not_found", "Project asset was not found.", asset_id=asset_id)
    return dict(record)
