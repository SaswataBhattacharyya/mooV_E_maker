"""CPU-side media probing and job-owned video staging for local H3 R2V.

Inputs to this module must already be authorized by a project/repertoire
resolver. Source files are read only. ComfyUI receives only unique normalized
clips, and cleanup trusts a per-owner manifest plus content hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)
FPS = 24
MIN_REFERENCE_SECONDS = 2.0
MAX_REFERENCE_SECONDS = 15.0
OWNER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,120}$")
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. -]{0,254}$")


class H3MediaError(RuntimeError):
    def __init__(self, code: str, message: str, *, context: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.context = dict(context or {})

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "context": self.context}


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    video_codec: str
    width: int
    height: int
    frame_rate: float
    has_audio: bool
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None


@dataclass(frozen=True)
class StagedVideo:
    asset_id: str
    filename: str
    sha256: str
    source_sha256: str
    source_start_sec: float
    source_end_sec: float
    duration_seconds: float
    fps: int
    has_audio: bool
    probe: MediaProbe
    owner_id: str


@dataclass(frozen=True)
class StagedAsset:
    asset_id: str
    media_type: str
    filename: str
    sha256: str
    source_sha256: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    owner_id: str


def _run(command: list[str], *, timeout: int, stage: str) -> subprocess.CompletedProcess[str]:
    LOGGER.info("H3 media command start stage=%s executable=%s timeout=%d", stage, command[0], timeout)
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise H3MediaError("media_command_timeout", f"{stage} exceeded its {timeout}-second timeout.", context={"stage": stage, "timeout_seconds": timeout}) from exc
    except OSError as exc:
        raise H3MediaError("media_tool_unavailable", f"Could not start {command[0]} for {stage}: {exc}", context={"stage": stage, "executable": command[0]}) from exc
    if result.returncode:
        raise H3MediaError("media_command_failed", f"{stage} failed with exit code {result.returncode}.", context={"stage": stage, "exit_code": result.returncode, "stderr": result.stderr[-3000:]})
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rate(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_media(path: Path, *, ffprobe: str = "ffprobe", timeout_seconds: int = 30) -> MediaProbe:
    source = Path(path)
    if not source.is_file():
        raise H3MediaError("source_media_missing", "Authorized source media is missing.", context={"path": str(source)})
    result = _run([
        ffprobe, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,sample_rate,channels",
        "-of", "json", str(source),
    ], timeout=timeout_seconds, stage="ffprobe")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise H3MediaError("ffprobe_invalid_json", "FFprobe returned invalid JSON.", context={"path": str(source)}) from exc
    streams = data.get("streams", [])
    video = next((row for row in streams if row.get("codec_type") == "video"), None)
    if video is None:
        raise H3MediaError("video_stream_missing", "Selected reference has no video stream.", context={"path": str(source)})
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    try:
        duration = float(data.get("format", {}).get("duration", 0.0))
        width, height = int(video.get("width", 0)), int(video.get("height", 0))
    except (TypeError, ValueError) as exc:
        raise H3MediaError("media_probe_incomplete", "FFprobe did not return usable duration or dimensions.", context={"path": str(source)}) from exc
    frame_rate = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate"))
    if duration <= 0 or width <= 0 or height <= 0 or frame_rate <= 0:
        raise H3MediaError("media_probe_incomplete", "FFprobe returned non-positive video metadata.", context={"path": str(source), "duration": duration, "width": width, "height": height, "frame_rate": frame_rate})
    return MediaProbe(duration, str(video.get("codec_name", "unknown")), width, height, frame_rate,
                      audio is not None, str(audio.get("codec_name")) if audio else None,
                      int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
                      int(audio["channels"]) if audio and audio.get("channels") else None)


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _register_staged_file(
    *, source: Path, staged_path: Path, temp_path: Path, owner_id: str,
    asset_id: str, media_type: str, owner_root: Path, input_dir: Path,
    extra: dict[str, Any] | None = None,
) -> tuple[str, str]:
    manifest = _load_owner_manifest(owner_root, owner_id, input_dir)
    source_digest = sha256_file(source)
    if staged_path.exists():
        raise H3MediaError("duplicate_staging_entry", "This owner already has a staged file with the same content identity; use a new attempt ID.", context={"owner_id": owner_id, "filename": staged_path.name})
    try:
        os.replace(temp_path, staged_path)
        staged_digest = sha256_file(staged_path)
        if media_type == "image" and staged_digest != source_digest:
            staged_path.unlink(missing_ok=True)
            raise H3MediaError("staged_image_hash_mismatch", "Staged image bytes differ from the authorized source.", context={"asset_id": asset_id})
        row = {"asset_id": asset_id, "media_type": media_type, "filename": staged_path.name,
               "sha256": staged_digest, "source_sha256": source_digest}
        row.update(extra or {})
        manifest["entries"].append(row)
        _atomic_json(owner_root / owner_id / "owner_manifest.json", manifest)
    except OSError:
        staged_path.unlink(missing_ok=True)
        raise
    return source_digest, staged_digest


def _probe_image(path: Path, *, ffprobe: str, timeout_seconds: int) -> tuple[int, int]:
    result = _run([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)], timeout=timeout_seconds, stage="ffprobe_image")
    try:
        streams = json.loads(result.stdout).get("streams", [])
        stream = next((row for row in streams if row.get("codec_type") == "video"), None)
        width, height = int(stream["width"]), int(stream["height"])
    except (json.JSONDecodeError, StopIteration, KeyError, TypeError, ValueError) as exc:
        raise H3MediaError("image_probe_failed", "Selected reference is not a readable image with dimensions.", context={"path": str(path)}) from exc
    if width <= 0 or height <= 0:
        raise H3MediaError("image_probe_failed", "Image has invalid dimensions.", context={"path": str(path), "width": width, "height": height})
    return width, height


def _probe_audio(path: Path, *, ffprobe: str, timeout_seconds: int) -> tuple[float, str, int | None, int | None]:
    result = _run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,sample_rate,channels", "-of", "json", str(path)], timeout=timeout_seconds, stage="ffprobe_audio")
    try:
        data = json.loads(result.stdout)
        stream = next(row for row in data.get("streams", []) if row.get("codec_type") == "audio")
        duration = float(data.get("format", {}).get("duration", 0))
        sample_rate = int(stream["sample_rate"]) if stream.get("sample_rate") else None
        channels = int(stream["channels"]) if stream.get("channels") else None
        codec = str(stream.get("codec_name", "unknown"))
    except (json.JSONDecodeError, StopIteration, KeyError, TypeError, ValueError) as exc:
        raise H3MediaError("audio_probe_failed", "Selected reference has no readable audio stream or duration.", context={"path": str(path)}) from exc
    if duration <= 0:
        raise H3MediaError("audio_probe_failed", "Audio duration must be positive.", context={"path": str(path), "duration": duration})
    return duration, codec, sample_rate, channels


def _load_owner_manifest(owner_root: Path, owner_id: str, input_dir: Path) -> dict[str, Any]:
    manifest_path = owner_root / owner_id / "owner_manifest.json"
    if not manifest_path.is_file():
        return {"schema_version": 1, "owner_id": owner_id, "comfy_input_dir": str(input_dir.resolve()), "entries": []}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise H3MediaError("owner_manifest_invalid", "Could not read job-owned media manifest.", context={"owner_id": owner_id, "path": str(manifest_path)}) from exc
    if data.get("owner_id") != owner_id or Path(data.get("comfy_input_dir", "")).resolve() != input_dir.resolve():
        raise H3MediaError("owner_manifest_scope_mismatch", "Job media manifest does not own this ComfyUI input directory.", context={"owner_id": owner_id})
    return data


def stage_video_reference(
    source_path: Path,
    *,
    asset_id: str,
    owner_id: str,
    comfy_input_dir: Path,
    owner_root: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
    include_audio: bool = False,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    timeout_seconds: int = 300,
) -> StagedVideo:
    """Create a 24-fps H.264/AAC clip with a same-source audio excerpt.

    When an interval is absent, a source no longer than 15 seconds is staged
    whole. Long sources require an explicit interval. The source is never
    modified; output ownership is recorded before the function returns.
    """
    if not OWNER_ID_RE.fullmatch(owner_id) or not ASSET_ID_RE.fullmatch(asset_id):
        raise H3MediaError("unsafe_media_owner", "Run/asset IDs contain unsupported characters.", context={"owner_id": owner_id, "asset_id": asset_id})
    source = Path(source_path).resolve()
    probe = probe_media(source, ffprobe=ffprobe, timeout_seconds=min(timeout_seconds, 60))
    if (start_sec is None) != (end_sec is None):
        raise H3MediaError("incomplete_video_interval", "Start and end times must be provided together.", context={"asset_id": asset_id})
    start = 0.0 if start_sec is None else float(start_sec)
    end = probe.duration_seconds if end_sec is None else float(end_sec)
    duration = end - start
    if start < 0 or end > probe.duration_seconds + 0.05 or duration < MIN_REFERENCE_SECONDS or duration > MAX_REFERENCE_SECONDS:
        raise H3MediaError("video_interval_out_of_bounds", "Reference excerpt must be 2–15 seconds and lie inside the source video.", context={"asset_id": asset_id, "source_duration": probe.duration_seconds, "start_sec": start, "end_sec": end, "excerpt_duration": duration})
    if include_audio and not probe.has_audio:
        raise H3MediaError("paired_audio_missing", "Paired soundtrack was requested, but the selected video has no audio stream.", context={"asset_id": asset_id})

    input_dir = Path(comfy_input_dir).resolve()
    input_dir.mkdir(parents=True, exist_ok=True)
    owner_dir = Path(owner_root).resolve() / owner_id
    owner_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_owner_manifest(Path(owner_root).resolve(), owner_id, input_dir)
    source_digest = sha256_file(source)
    clip_identity = hashlib.sha256(f"{asset_id}:{source_digest}:{start:.6f}:{end:.6f}".encode()).hexdigest()[:12]
    filename = f"sb_{owner_id[:48]}_{asset_id[:48]}_{clip_identity}.mp4"
    if not SAFE_FILENAME.fullmatch(filename):
        raise H3MediaError("unsafe_staged_filename", "Generated staging filename is invalid.", context={"filename": filename})
    final_path = input_dir / filename
    if final_path.exists() or any(row.get("filename") == filename for row in manifest.get("entries", [])):
        raise H3MediaError("duplicate_staging_entry", "This owner already has a staged file with the same content identity; use a new attempt ID.", context={"owner_id": owner_id, "filename": filename})
    temp_path = input_dir / f".sb_{uuid.uuid4().hex}.tmp.mp4"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{duration:.6f}", "-map", "0:v:0", "-vf", "fps=24", "-r", "24", "-fps_mode", "cfr", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    if include_audio:
        command += ["-map", "0:a:0", "-af", "aresample=async=1:first_pts=0", "-c:a", "aac", "-b:a", "192k", "-ar", "32000"]
    else:
        command += ["-an"]
    command += ["-movflags", "+faststart", str(temp_path)]
    LOGGER.info("Staging H3 video reference owner=%s asset=%s source_hash=%s interval=%.3f-%.3f paired_audio=%s source_fps=%.3f",
                owner_id, asset_id, source_digest[:16], start, end, include_audio, probe.frame_rate)
    try:
        _run(command, timeout=timeout_seconds, stage="normalize_reference_video")
        staged_probe = probe_media(temp_path, ffprobe=ffprobe, timeout_seconds=min(timeout_seconds, 60))
        if abs(staged_probe.frame_rate - FPS) > 0.02:
            raise H3MediaError("staged_fps_mismatch", "Normalized reference did not probe as 24 fps.", context={"actual_fps": staged_probe.frame_rate})
        if include_audio and not staged_probe.has_audio:
            raise H3MediaError("staged_audio_missing", "Normalized reference lost its paired soundtrack.", context={"asset_id": asset_id})
        if abs(staged_probe.duration_seconds - duration) > 0.15:
            raise H3MediaError("staged_duration_mismatch", "Normalized reference duration differs from the selected interval.", context={"requested_seconds": duration, "actual_seconds": staged_probe.duration_seconds})
        os.replace(temp_path, final_path)
    finally:
        temp_path.unlink(missing_ok=True)

    staged_hash = sha256_file(final_path)
    manifest["entries"].append({
        "asset_id": asset_id, "media_type": "video", "filename": filename, "sha256": staged_hash,
        "source_sha256": source_digest, "source_start_sec": start,
        "source_end_sec": end, "include_audio": include_audio,
    })
    try:
        _atomic_json(Path(owner_root).resolve() / owner_id / "owner_manifest.json", manifest)
    except OSError:
        final_path.unlink(missing_ok=True)
        raise
    staged = StagedVideo(asset_id, filename, staged_hash, source_digest, start, end,
                         staged_probe.duration_seconds, FPS, staged_probe.has_audio,
                         staged_probe, owner_id)
    LOGGER.info("Staged H3 video reference owner=%s asset=%s file=%s sha256=%s duration=%.3f fps=%d audio=%s",
                owner_id, asset_id, filename, staged_hash[:16], staged.duration_seconds, FPS, staged.has_audio)
    return staged


def stage_image_reference(
    source_path: Path,
    *,
    asset_id: str,
    owner_id: str,
    comfy_input_dir: Path,
    owner_root: Path,
    ffprobe: str = "ffprobe",
    timeout_seconds: int = 30,
) -> StagedAsset:
    """Copy a validated image into ComfyUI input under this job's ownership."""
    if not OWNER_ID_RE.fullmatch(owner_id) or not ASSET_ID_RE.fullmatch(asset_id):
        raise H3MediaError("unsafe_media_owner", "Run/asset IDs contain unsupported characters.", context={"owner_id": owner_id, "asset_id": asset_id})
    source = Path(source_path).resolve()
    if not source.is_file() or source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise H3MediaError("unsupported_image", "Reference image must be a readable PNG, JPEG or WEBP file.", context={"asset_id": asset_id})
    width, height = _probe_image(source, ffprobe=ffprobe, timeout_seconds=timeout_seconds)
    input_dir = Path(comfy_input_dir).resolve()
    owner_base = Path(owner_root).resolve()
    owner_dir = owner_base / owner_id
    input_dir.mkdir(parents=True, exist_ok=True)
    owner_dir.mkdir(parents=True, exist_ok=True)
    manifest = _load_owner_manifest(owner_base, owner_id, input_dir)
    source_digest = sha256_file(source)
    existing = next((row for row in manifest.get("entries", [])
                     if row.get("asset_id") == asset_id and row.get("media_type") == "image"
                     and row.get("source_sha256") == source_digest), None)
    if existing:
        staged_path = input_dir / str(existing.get("filename", ""))
        if (staged_path.parent.resolve() == input_dir and staged_path.is_file()
                and sha256_file(staged_path) == existing.get("sha256")):
            return StagedAsset(asset_id, "image", staged_path.name, existing["sha256"],
                               source_digest, None, int(existing.get("width", width)),
                               int(existing.get("height", height)), owner_id)
        raise H3MediaError("staged_image_integrity_failed",
            "An idempotent staged image is missing or its bytes changed; refusing to replace it.",
            context={"asset_id": asset_id, "owner_id": owner_id})
    identity = hashlib.sha256(f"{asset_id}:{source_digest}".encode()).hexdigest()[:12]
    filename = f"sb_{owner_id[:48]}_{asset_id[:48]}_{identity}{source.suffix.lower()}"
    staged_path = input_dir / filename
    temp_path = input_dir / f".sb_{uuid.uuid4().hex}.tmp{source.suffix.lower()}"
    try:
        shutil.copyfile(source, temp_path)
        source_hash, staged_hash = _register_staged_file(source=source, staged_path=staged_path,
            temp_path=temp_path, owner_id=owner_id, asset_id=asset_id, media_type="image",
            owner_root=owner_base, input_dir=input_dir, extra={"width": width, "height": height})
    finally:
        temp_path.unlink(missing_ok=True)
    LOGGER.info("Staged H3 image owner=%s asset=%s file=%s sha256=%s dimensions=%dx%d",
                owner_id, asset_id, filename, staged_hash[:16], width, height)
    return StagedAsset(asset_id, "image", filename, staged_hash, source_hash, None, width, height, owner_id)


def stage_audio_reference(
    source_path: Path,
    *,
    asset_id: str,
    owner_id: str,
    comfy_input_dir: Path,
    owner_root: Path,
    start_sec: float | None = None,
    end_sec: float | None = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    timeout_seconds: int = 120,
) -> StagedAsset:
    """Normalize a standalone reference excerpt to mono 32 kHz PCM WAV."""
    if not OWNER_ID_RE.fullmatch(owner_id) or not ASSET_ID_RE.fullmatch(asset_id):
        raise H3MediaError("unsafe_media_owner", "Run/asset IDs contain unsupported characters.", context={"owner_id": owner_id, "asset_id": asset_id})
    source = Path(source_path).resolve()
    source_duration, _, _, _ = _probe_audio(source, ffprobe=ffprobe, timeout_seconds=min(timeout_seconds, 30))
    if (start_sec is None) != (end_sec is None):
        raise H3MediaError("incomplete_audio_interval", "Audio excerpt start and end must be provided together.", context={"asset_id": asset_id})
    start = 0.0 if start_sec is None else float(start_sec)
    end = source_duration if end_sec is None else float(end_sec)
    duration = end - start
    if start < 0 or end > source_duration + 0.05 or duration < MIN_REFERENCE_SECONDS or duration > MAX_REFERENCE_SECONDS:
        raise H3MediaError("audio_interval_out_of_bounds", "Standalone H3 reference audio must be 2–15 seconds and lie inside the source.", context={"asset_id": asset_id, "source_duration": source_duration, "start_sec": start, "end_sec": end})
    input_dir = Path(comfy_input_dir).resolve()
    owner_base = Path(owner_root).resolve()
    owner_dir = owner_base / owner_id
    input_dir.mkdir(parents=True, exist_ok=True)
    owner_dir.mkdir(parents=True, exist_ok=True)
    _load_owner_manifest(owner_base, owner_id, input_dir)
    source_digest = sha256_file(source)
    identity = hashlib.sha256(f"{asset_id}:{source_digest}:{start:.6f}:{end:.6f}".encode()).hexdigest()[:12]
    filename = f"sb_{owner_id[:48]}_{asset_id[:48]}_{identity}.wav"
    staged_path = input_dir / filename
    temp_path = input_dir / f".sb_{uuid.uuid4().hex}.tmp.wav"
    command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.6f}", "-i", str(source), "-t", f"{duration:.6f}", "-vn", "-ac", "1", "-ar", "32000", "-c:a", "pcm_s16le", str(temp_path)]
    try:
        _run(command, timeout=timeout_seconds, stage="normalize_reference_audio")
        staged_duration, codec, sample_rate, channels = _probe_audio(temp_path, ffprobe=ffprobe, timeout_seconds=min(timeout_seconds, 30))
        if sample_rate != 32000 or channels != 1 or codec != "pcm_s16le":
            raise H3MediaError("staged_audio_format_mismatch", "Normalized voice reference must be mono 32 kHz PCM WAV.", context={"sample_rate": sample_rate, "channels": channels, "codec": codec})
        source_hash, staged_hash = _register_staged_file(source=source, staged_path=staged_path,
            temp_path=temp_path, owner_id=owner_id, asset_id=asset_id, media_type="audio",
            owner_root=owner_base, input_dir=input_dir,
            extra={"source_start_sec": start, "source_end_sec": end, "duration_seconds": staged_duration,
                   "sample_rate": sample_rate, "channels": channels, "codec": codec})
    finally:
        temp_path.unlink(missing_ok=True)
    LOGGER.info("Staged H3 standalone audio owner=%s asset=%s file=%s sha256=%s duration=%.3f rate=%d channels=%d",
                owner_id, asset_id, filename, staged_hash[:16], staged_duration, sample_rate, channels)
    return StagedAsset(asset_id, "audio", filename, staged_hash, source_hash, staged_duration, None, None, owner_id)


def cleanup_owned_media(owner_id: str, *, comfy_input_dir: Path, owner_root: Path) -> dict[str, Any]:
    """Delete only hash-matching files listed in the requested owner's manifest."""
    if not OWNER_ID_RE.fullmatch(owner_id):
        raise H3MediaError("unsafe_media_owner", "Run ID contains unsupported characters.", context={"owner_id": owner_id})
    input_dir = Path(comfy_input_dir).resolve()
    owner_dir = Path(owner_root).resolve() / owner_id
    manifest = _load_owner_manifest(Path(owner_root).resolve(), owner_id, input_dir)
    removed: list[str] = []
    retained: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for row in manifest.get("entries", []):
        name = row.get("filename", "")
        path = input_dir / name
        if not SAFE_FILENAME.fullmatch(name) or path.parent.resolve() != input_dir or not path.is_file():
            skipped.append({"filename": str(name), "reason": "missing_or_unsafe"})
            continue
        if sha256_file(path) != row.get("sha256"):
            retained.append(row)
            skipped.append({"filename": name, "reason": "hash_changed"})
            continue
        path.unlink()
        removed.append(name)
    manifest["entries"] = retained
    _atomic_json(owner_dir / "owner_manifest.json", manifest)
    result = {"owner_id": owner_id, "removed": removed, "skipped": skipped, "remaining_owned_files": len(retained)}
    LOGGER.info("Cleaned H3 media staging owner=%s removed=%d skipped=%d retained=%d",
                owner_id, len(removed), len(skipped), len(retained))
    return result
