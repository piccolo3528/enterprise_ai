"""Original uploaded files on local disk (ARCHITECTURE §4.9).

Files are stored as `{UPLOAD_DIR}/{kb_id}/{document_id}.{ext}`: a name the server chose, so the
user's filename (which could contain "..", slashes or reserved names) never touches the
filesystem. UPLOAD_DIR is outside anything the web server serves.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from app.core.errors import PayloadTooLargeError

logger = logging.getLogger("app.storage")

_COPY_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class SavedFile:
    partial: Path  # where the bytes are now; `promote` moves them to the final name
    relative_path: str  # what the database stores, e.g. "<kb_id>/<doc_id>.pdf"
    size_bytes: int
    sha256: str


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def path_of(self, relative_path: str) -> Path:
        path = (self.root / relative_path).resolve()
        # Defence in depth: stored paths are always server-generated, but never follow one
        # outside the upload folder.
        if not path.is_relative_to(self.root):
            raise ValueError("stored path escapes the upload folder")
        return path

    def save_partial(
        self, source: BinaryIO, kb_id: uuid.UUID, document_id: uuid.UUID, ext: str, max_bytes: int
    ) -> SavedFile:
        """Copy the upload to a temporary name, counting bytes and hashing as it goes.

        The size is checked while copying, not trusted from the request, and the SHA-256 (for
        duplicate detection) costs no second read of the file.
        """
        relative = f"{kb_id}/{document_id}.{ext}"
        partial = self.path_of(relative).with_name(f".{document_id}.{ext}.part")
        partial.parent.mkdir(parents=True, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        try:
            with partial.open("wb") as out:
                while chunk := source.read(_COPY_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise PayloadTooLargeError(
                            f"The file is larger than {max_bytes // (1024 * 1024)} MB."
                        )
                    digest.update(chunk)
                    out.write(chunk)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return SavedFile(partial, relative, size, digest.hexdigest())

    def promote(self, saved: SavedFile) -> None:
        """Give the file its final name (atomic on the same disk)."""
        os.replace(saved.partial, self.path_of(saved.relative_path))

    def delete(self, relative_path: str) -> None:
        try:
            self.path_of(relative_path).unlink(missing_ok=True)
        except OSError:
            # The database row is already gone; a leftover file is harmless and is logged.
            logger.warning("Could not delete stored file %s", relative_path, exc_info=True)

    def discard(self, saved: SavedFile) -> None:
        saved.partial.unlink(missing_ok=True)

    def delete_knowledge_base(self, kb_id: uuid.UUID) -> None:
        folder = self.path_of(str(kb_id))
        if folder.exists():
            shutil.rmtree(folder, onexc=_log_failure)


def _log_failure(_function, path, _exc) -> None:
    logger.warning("Could not delete %s", path)
