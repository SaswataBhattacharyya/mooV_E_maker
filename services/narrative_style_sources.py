"""Safe text extraction with page/line evidence locators for style references."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


MAX_SOURCE_BYTES = 10 * 1024 * 1024
MAX_EXTRACTED_CHARS = 1_500_000
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}


class StyleSourceError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def _text_blocks(text: str, *, locator_prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    lines = text.splitlines()
    start: int | None = None
    collected: list[str] = []
    for index, line in enumerate(lines, 1):
        if line.strip():
            if start is None:
                start = index
            collected.append(line)
        elif collected:
            rows.append({"locator": f"{locator_prefix}{start}-{index - 1}", "text": "\n".join(collected)})
            start, collected = None, []
    if collected and start is not None:
        rows.append({"locator": f"{locator_prefix}{start}-{len(lines)}", "text": "\n".join(collected)})
    return rows


def extract_style_source(filename: str, content: bytes, *, max_bytes: int = MAX_SOURCE_BYTES) -> dict[str, Any]:
    """Extract bounded PDF/Markdown/plain text and retain stable evidence locators.

    This function does not persist files or call an LLM. PDF extraction uses the
    installed ``pdftotext`` executable with stdin/stdout, so the supplied filename
    is never interpreted as a command or temporary path.
    """
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise StyleSourceError("unsupported_style_source", "Narrative style sources must be PDF, Markdown (.md), or text (.txt); video and image files are not accepted here.")
    if not isinstance(content, bytes) or not content:
        raise StyleSourceError("empty_style_source", "The selected style source is empty.")
    if len(content) > max_bytes:
        raise StyleSourceError("style_source_too_large", f"Style source exceeds the {max_bytes}-byte upload limit.")
    digest = hashlib.sha256(content).hexdigest()
    if suffix == ".pdf":
        executable = shutil.which("pdftotext")
        if not executable:
            raise StyleSourceError("pdf_extractor_unavailable", "PDF text extraction is unavailable because pdftotext is not installed; Markdown and text sources remain available.")
        try:
            extracted = subprocess.run([executable, "-layout", "-enc", "UTF-8", "-", "-"],
                                       input=content, capture_output=True, timeout=30, check=False)
        except subprocess.TimeoutExpired as exc:
            raise StyleSourceError("pdf_extraction_timeout", "PDF text extraction exceeded 30 seconds.") from exc
        except OSError as exc:
            raise StyleSourceError("pdf_extraction_failed", f"Could not start pdftotext: {exc}") from exc
        if extracted.returncode != 0:
            detail = extracted.stderr.decode("utf-8", errors="replace")[:400]
            raise StyleSourceError("invalid_pdf", f"PDF text extraction failed: {detail or 'invalid or encrypted PDF'}")
        decoded = extracted.stdout.decode("utf-8", errors="replace")
        if "\ufffd" in decoded:
            raise StyleSourceError("pdf_text_encoding_invalid", "PDF text could not be decoded reliably as UTF-8.")
        pages = decoded.split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        blocks = []
        for page_number, page in enumerate(pages, 1):
            blocks.extend(_text_blocks(page, locator_prefix=f"page:{page_number}:line:"))
        source_type = "pdf"
    else:
        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise StyleSourceError("style_source_encoding_invalid", "Markdown/text sources must be UTF-8 encoded.") from exc
        blocks = _text_blocks(decoded, locator_prefix="line:")
        source_type = "markdown" if suffix == ".md" else "text"
    total_chars = sum(len(row["text"]) for row in blocks)
    if total_chars > MAX_EXTRACTED_CHARS:
        raise StyleSourceError("style_source_text_too_large", f"Extracted text exceeds the {MAX_EXTRACTED_CHARS}-character processing limit.")
    if not blocks:
        raise StyleSourceError("style_source_no_text", "No readable text was found in this source.")
    return {"source_id": f"style-source-{digest[:16]}", "sha256": digest,
            "filename": Path(filename).name, "source_type": source_type,
            "byte_length": len(content), "text_character_count": total_chars,
            "evidence_blocks": blocks}


def _source_paths(root: Path, source_id: str) -> tuple[Path, Path]:
    if not isinstance(source_id, str) or not source_id.startswith("style-source-") or len(source_id) != 29 or not all(char in "0123456789abcdef" for char in source_id[13:]):
        raise StyleSourceError("invalid_style_source_id", "Style source ID has an invalid format.")
    directory = (Path(root).resolve() / "sources").resolve()
    if not directory.is_relative_to(Path(root).resolve()):
        raise StyleSourceError("invalid_style_source_root", "Style source storage escaped its configured root.")
    return directory / f"{source_id}.source", directory / f"{source_id}.json"


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".style-source-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def store_style_source(root: Path, filename: str, content: bytes) -> dict[str, Any]:
    """Store one hash-addressed source; repeated identical uploads reuse its bytes."""
    extracted = extract_style_source(filename, content)
    source_path, metadata_path = _source_paths(root, extracted["source_id"])
    if metadata_path.exists() or source_path.exists():
        try:
            saved = json.loads(metadata_path.read_text(encoding="utf-8"))
            existing = source_path.read_bytes()
        except (OSError, json.JSONDecodeError) as exc:
            raise StyleSourceError("style_source_store_corrupt", f"Existing style source record is incomplete: {exc}") from exc
        if saved.get("sha256") != extracted["sha256"] or hashlib.sha256(existing).hexdigest() != extracted["sha256"]:
            raise StyleSourceError("style_source_hash_conflict", "Existing style source ID does not match its stored bytes.")
        return {**saved, "deduplicated": True}
    metadata = {key: value for key, value in extracted.items() if key != "evidence_blocks"}
    metadata["evidence_blocks"] = extracted["evidence_blocks"]
    try:
        _atomic_write(source_path, content)
        _atomic_write(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"))
    except OSError as exc:
        raise StyleSourceError("style_source_store_failed", f"Could not persist style source: {exc}") from exc
    return {**metadata, "deduplicated": False}


def list_style_sources(root: Path) -> list[dict[str, Any]]:
    directory = (Path(root).resolve() / "sources").resolve()
    if not directory.is_dir():
        return []
    results = []
    for path in sorted(directory.glob("style-source-*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            source_path, _ = _source_paths(root, str(value.get("source_id", "")))
            if hashlib.sha256(source_path.read_bytes()).hexdigest() != value.get("sha256"):
                continue
            results.append({key: item for key, item in value.items() if key != "evidence_blocks"})
        except (OSError, json.JSONDecodeError, StyleSourceError):
            continue
    return results
