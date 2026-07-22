import json
import hashlib
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Generator

from onyx.connectors.interfaces import LoadConnector, PollConnector
from onyx.connectors.models import Document, TextSection, DocumentSource
from onyx.configs.app_configs import INDEX_BATCH_SIZE


class VBPLExportConnectorError(Exception):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class VBPLExportConnector(LoadConnector, PollConnector):
    def __init__(self, export_root: str = "/app/vbpl-export", batch_size: int = INDEX_BATCH_SIZE) -> None:
        self.export_root = Path(export_root)
        self.batch_size = batch_size

    def load_credentials(self, credentials: dict[str, Any]) -> dict[str, Any] | None:
        return None

    def _read_active_manifest(self) -> tuple[Path, dict[str, Any]]:
        active_pointer = self.export_root / "active-release.json"
        if not active_pointer.exists():
            raise VBPLExportConnectorError(f"Active release pointer not found: {active_pointer}")

        try:
            pointer_data = json.loads(active_pointer.read_text(encoding="utf-8"))
        except Exception as e:
            raise VBPLExportConnectorError("Failed to parse active-release.json") from e

        manifest_path = Path(pointer_data.get("manifest_path", ""))
        if not manifest_path.exists():
            # Fallback to local path relative to export_root if manifest_path in container differs
            manifest_path = self.export_root / "releases" / pointer_data.get("release_id", "") / "manifest.json"

        if not manifest_path.exists():
            raise VBPLExportConnectorError(f"Manifest file not found: {manifest_path}")

        expected_sha = pointer_data.get("manifest_sha256", "")
        if expected_sha and _sha256_file(manifest_path) != expected_sha:
            raise VBPLExportConnectorError("Manifest checksum mismatch")

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise VBPLExportConnectorError("Failed to parse manifest JSON") from e

        return manifest_path, manifest_data

    def _documents(self, changed_after: datetime | None = None) -> Generator[list[Document], None, None]:
        manifest_path, manifest_data = self._read_active_manifest()
        manifest_dir = manifest_path.parent

        batch: list[Document] = []
        for doc_entry in manifest_data.get("documents", []):

            rel_path = doc_entry.get("relative_path", "")
            doc_file = manifest_dir / rel_path
            if not doc_file.exists():
                raise VBPLExportConnectorError(f"Document file missing: {doc_file}")

            expected_sha = doc_entry.get("sha256", "")
            if expected_sha and _sha256_file(doc_file) != expected_sha:
                raise VBPLExportConnectorError(f"Document checksum mismatch: {doc_file}")

            try:
                raw_doc = json.loads(doc_file.read_text(encoding="utf-8"))
            except Exception as e:
                raise VBPLExportConnectorError(f"Failed to parse document JSON: {doc_file}") from e

            doc_id = raw_doc.get("document_id", "")
            content = raw_doc.get("content", "")
            link = raw_doc.get("link", "")
            metadata = raw_doc.get("metadata", {})
            title = metadata.get("title", doc_id)

            updated_at_str = doc_entry.get("updated_at")
            doc_updated_at = None
            if updated_at_str:
                try:
                    doc_updated_at = datetime.fromisoformat(updated_at_str)
                except Exception:
                    pass

            batch.append(
                Document(
                    id=doc_id,
                    sections=[TextSection(text=content)],
                    source=DocumentSource.VBPL_EXPORT,
                    semantic_identifier=title,
                    metadata=metadata,
                    doc_updated_at=doc_updated_at,
                    link=link,
                )
            )
            if len(batch) >= self.batch_size:
                yield batch
                batch = []

        if batch:
            yield batch

    def load_from_state(self) -> Generator[list[Document], None, None]:
        yield from self._documents(changed_after=None)

    def poll_source(self, start: float, end: float) -> Generator[list[Document], None, None]:
        yield from self._documents(changed_after=datetime.fromtimestamp(start, UTC))
