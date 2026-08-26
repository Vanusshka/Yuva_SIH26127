"""
Image/Video Service – handles upload I/O for the API layer.
Keeps file-system concerns out of the route handlers.
"""

from __future__ import annotations
import uuid
from pathlib import Path

from fastapi import UploadFile, HTTPException

from app.config import INPUT_DIR, MAX_UPLOAD_MB

_MAX_BYTES        = MAX_UPLOAD_MB * 1024 * 1024
_ALLOWED_IMAGES   = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
_ALLOWED_VIDEOS   = {".mp4", ".avi", ".mov", ".mkv", ".m4v", ".wmv", ".flv"}
# Keep legacy name for backward compat
_ALLOWED          = _ALLOWED_IMAGES


async def save_upload(file: UploadFile) -> Path:
    """
    Persist an uploaded IMAGE to INPUT_DIR with a unique filename.

    Returns the saved Path or raises HTTPException on validation error.
    """
    suffix = Path(file.filename or "upload.jpg").suffix.lower()
    if suffix not in _ALLOWED_IMAGES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type '{suffix}'. Allowed: {sorted(_ALLOWED_IMAGES)}",
        )

    contents = await file.read()
    if len(contents) > _MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Max allowed: {MAX_UPLOAD_MB} MB.",
        )

    unique_name = f"{uuid.uuid4().hex}{suffix}"
    dest        = INPUT_DIR / unique_name
    dest.write_bytes(contents)
    return dest


async def save_video_upload(file: UploadFile) -> Path:
    """
    Persist an uploaded VIDEO file to INPUT_DIR with a unique filename.

    Accepts: .mp4, .avi, .mov, .mkv, .m4v, .wmv, .flv
    Max size: 500 MB (videos are much larger than images)

    Returns the saved Path or raises HTTPException on validation error.
    """
    _MAX_VIDEO_BYTES = 500 * 1024 * 1024   # 500 MB hard limit for videos

    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in _ALLOWED_VIDEOS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported video format '{suffix}'. "
                f"Allowed: {sorted(_ALLOWED_VIDEOS)}"
            ),
        )

    contents = await file.read()
    if len(contents) > _MAX_VIDEO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Video too large ({len(contents) // (1024*1024)} MB). Max allowed: 500 MB.",
        )

    unique_name = f"video_{uuid.uuid4().hex}{suffix}"
    dest        = INPUT_DIR / unique_name
    dest.write_bytes(contents)
    return dest


def cleanup(path: Path) -> None:
    """Remove a temporary upload file (best-effort, no exception on failure)."""
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
