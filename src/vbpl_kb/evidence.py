from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import tempfile
from typing import BinaryIO


class InvalidEvidenceHashError(ValueError):
    """Raised when an invalid hash or path traversal attempt is detected."""
    pass


HASH_REGEX = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class EvidenceObject:
    hash_sha256: str
    media_type: str
    official_url: str
    endpoint: str
    acquired_at: datetime
    corpus_revision: str
    size_bytes: int


class EvidenceStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def _get_path_for_hash(self, hash_sha256: str) -> Path:
        if not HASH_REGEX.match(hash_sha256):
            raise InvalidEvidenceHashError(f"Invalid SHA-256 hash string: {hash_sha256}")
        first_two = hash_sha256[:2]
        return self.base_dir / "sha256" / first_two / hash_sha256

    def put(
        self,
        content: bytes,
        *,
        media_type: str,
        official_url: str,
        endpoint: str,
        corpus_revision: str,
        acquired_at: datetime | None = None,
    ) -> EvidenceObject:
        acquired_at = acquired_at or datetime.now(timezone.utc)
        hash_sha256 = hashlib.sha256(content).hexdigest()
        target_path = self._get_path_for_hash(hash_sha256)

        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic write via temporary file
            with tempfile.NamedTemporaryFile("wb", dir=target_path.parent, delete=False) as tmp_f:
                tmp_f.write(content)
                tmp_f.flush()
                os.fsync(tmp_f.fileno())
                tmp_name = tmp_f.name

            # Atomic replace
            os.replace(tmp_name, target_path)

        return EvidenceObject(
            hash_sha256=hash_sha256,
            media_type=media_type,
            official_url=official_url,
            endpoint=endpoint,
            acquired_at=acquired_at,
            corpus_revision=corpus_revision,
            size_bytes=len(content),
        )

    def open(self, hash_sha256: str) -> BinaryIO:
        target_path = self._get_path_for_hash(hash_sha256)
        if not target_path.exists():
            raise FileNotFoundError(f"Evidence object not found: {hash_sha256}")

        f = open(target_path, "rb")
        content = f.read()
        f.seek(0)
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != hash_sha256:
            f.close()
            raise ValueError(f"Corrupted evidence file content hash mismatch: {actual_hash} != {hash_sha256}")
        return f
