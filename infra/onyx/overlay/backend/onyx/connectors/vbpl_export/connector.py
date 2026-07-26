import json
import hashlib
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Generator

from onyx.connectors.interfaces import LoadConnector, PollConnector, SlimConnector
from onyx.connectors.models import Document, TextSection, DocumentSource, SlimDocument
from onyx.configs.app_configs import INDEX_BATCH_SIZE


class VBPLExportConnectorError(Exception):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _projection_version(raw_doc: dict[str, Any]) -> int:
    value = raw_doc.get("projection_schema_version")
    if value is None:
        return 1
    if type(value) is not int:
        raise VBPLExportConnectorError("projection_schema_version must be an integer")
    if value not in (1, 2):
        raise VBPLExportConnectorError(
            f"Unsupported projection schema version: {value}"
        )
    return value


def _text_sections(raw_doc: dict[str, Any]) -> list[TextSection]:
    version = _projection_version(raw_doc)
    if version == 1:
        content = raw_doc.get("content")
        if not isinstance(content, str) or not content.strip():
            raise VBPLExportConnectorError("Schema-v1 content is empty")
        return [TextSection(text=content, link=raw_doc.get("link"))]
    raw_sections = raw_doc.get("sections")
    if not isinstance(raw_sections, list) or not raw_sections:
        raise VBPLExportConnectorError("Schema-v2 sections must be non-empty")
    sections: list[TextSection] = []
    seen: set[str] = set()
    for raw_section in raw_sections:
        section_id = raw_section.get("section_id")
        text = raw_section.get("text")
        link = raw_section.get("link")
        if not all(isinstance(value, str) and value for value in (section_id, text, link)):
            raise VBPLExportConnectorError("Invalid schema-v2 section")
        if section_id in seen:
            raise VBPLExportConnectorError(f"Duplicate section_id: {section_id}")
        seen.add(section_id)
        sections.append(TextSection(text=text, link=link, heading=section_id))
    return sections


class VBPLExportConnector(LoadConnector, PollConnector, SlimConnector):
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

    def _documents(
        self,
        changed_after: datetime | None = None,
        filter_doc_ids: set[str] | None = None,
    ) -> Generator[list[Document], None, None]:
        manifest_path, manifest_data = self._read_active_manifest()
        manifest_dir = manifest_path.parent

        doc_entries = manifest_data.get("documents", [])
        validated_raw_docs: list[tuple[dict[str, Any], dict[str, Any]]] = []

        for doc_entry in doc_entries:
            doc_id = doc_entry.get("document_id", "")
            if filter_doc_ids is not None and doc_id not in filter_doc_ids:
                continue

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

            _text_sections(raw_doc)
            validated_raw_docs.append((doc_entry, raw_doc))

        batch: list[Document] = []
        for doc_entry, raw_doc in validated_raw_docs:
            doc_id = raw_doc.get("document_id", "")
            metadata = raw_doc.get("metadata", {})
            title = metadata.get("title", doc_id)

            sections = _text_sections(raw_doc)

            updated_at_str = doc_entry.get("updated_at")
            doc_updated_at = None
            if updated_at_str:
                try:
                    doc_updated_at = datetime.fromisoformat(updated_at_str)
                except Exception:
                    pass

            sanitized_metadata: dict[str, Any] = {}
            for k, v in metadata.items():
                if isinstance(v, str) and (len(k) + len(v) > 240):
                    sanitized_metadata[k] = v[: 240 - len(k)] + "..."
                elif isinstance(v, list):
                    sanitized_metadata[k] = [
                        item[: 240 - len(k)] + "..." if isinstance(item, str) and (len(k) + len(item) > 240) else item
                        for item in v
                    ]
                else:
                    sanitized_metadata[k] = v

            batch.append(
                Document(
                    id=doc_id,
                    sections=sections,
                    source=DocumentSource.VBPL_EXPORT,
                    semantic_identifier=title,
                    metadata=sanitized_metadata,
                    doc_updated_at=doc_updated_at,
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
        manifest_path, _ = self._read_active_manifest()
        delta_path = manifest_path.parent / "delta-manifest.json"
        if delta_path.exists():
            try:
                delta_data = json.loads(delta_path.read_text(encoding="utf-8"))
                upsert_ids = set(delta_data.get("upsert_ids", []))
                if not upsert_ids:
                    return
                yield from self._documents(changed_after=None, filter_doc_ids=upsert_ids)
                return
            except Exception as e:
                raise VBPLExportConnectorError("Failed to parse delta-manifest.json") from e
        yield from self._documents(changed_after=datetime.fromtimestamp(start, UTC))

    def retrieve_all_slim_documents(self) -> Generator[list[SlimDocument], None, None]:
        _, manifest_data = self._read_active_manifest()
        doc_entries = manifest_data.get("documents", [])
        batch: list[SlimDocument] = []
        for doc_entry in doc_entries:
            doc_id = doc_entry.get("document_id")
            if doc_id:
                batch.append(SlimDocument(id=str(doc_id)))
                if len(batch) >= self.batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
