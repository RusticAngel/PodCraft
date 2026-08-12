import hashlib
import os
import uuid
from typing import Optional


def stable_token(*parts: str) -> str:
    """Deterministic 32-char hex token from string parts.

    Python's built-in hash() is randomized per-process; this gives stable
    filenames across runs, which is required for reproducible output paths.
    """
    raw = "|".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def safe_filename(original: str, prefix: str = "") -> str:
    """Sanitize an uploaded filename and keep it unique."""
    base = os.path.basename(original or "file")
    name, ext = os.path.splitext(base)
    ext = ext.lower() if ext else ".bin"
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in name)[:60]
    token = stable_token(prefix, base, uuid.uuid4().hex)
    return f"{prefix}{safe}_{token[:8]}{ext}"


def ensure_dirs(*paths: str) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)


def safe_join(directory: str, filename: str) -> Optional[str]:
    """Return a path inside `directory`, or None if filename escapes it."""
    path = os.path.realpath(os.path.join(directory, filename))
    if not path.startswith(os.path.realpath(directory)):
        return None
    return path