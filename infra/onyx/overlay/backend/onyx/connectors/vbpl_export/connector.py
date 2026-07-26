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


class VBPLExportConnector(LoadConnector, PollConnector, SlimConnector):
    def __init__(
        self,
        corpus_view: str = "current",
        export_root: str = "/app/vbpl-export",
        batch_size: int = INDEX_BATCH_SIZE,
    ) -> None:
        if corpus_view not in ("current", "history", "evidence"):
            raise VBPLExportConnectorError(f"Invalid corpus_view: {corpus_view}")
        self.corpus_view = corpus_view
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

    def _parse_raw_doc(self, raw_doc: dict[str, Any]) -> Document:
        doc_id = raw_doc.get("document_id")
        if not doc_id:
            raise VBPLExportConnectorError("Missing document_id in document")

        schema_ver = raw_doc.get("projection_schema_version", 2)
        if schema_ver != 2:
            raise VBPLExportConnectorError(f"Unsupported projection schema version: {schema_ver}")

        raw_sections = raw_doc.get("sections", [])
        if not isinstance(raw_sections, list) or len(raw_sections) != 1:
            raise VBPLExportConnectorError("Document must contain exactly one section")

        sec_data = raw_sections[0]
        text = sec_data.get("text", "")
        link = sec_data.get("link", raw_doc.get("link", ""))
        heading = sec_data.get("section_id")

        metadata = raw_doc.get("metadata", {})
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

        title = sanitized_metadata.get("title", doc_id)
        section = TextSection(text=text, link=link, heading=heading)

        return Document(
            id=doc_id,
            sections=[section],
            source=DocumentSource.VBPL_EXPORT,
            semantic_identifier=title,
            metadata=sanitized_metadata,
        )

    def load_from_state(self) -> Generator[list[Document], None, None]:
        manifest_path, _ = self._read_active_manifest()
        view_dir = manifest_path.parent / self.corpus_view

        if not view_dir.exists():
            raise VBPLExportConnectorError(f"View directory missing: {view_dir}")

        shards = sorted(view_dir.glob("documents-*.jsonl"))
        if not shards:
            return

        batch: list[Document] = []
        for shard in shards:
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        raw_doc = json.loads(line_str)
                    except Exception as e:
                        raise VBPLExportConnectorError(f"Failed to parse line in {shard}") from e

                    doc = self._parse_raw_doc(raw_doc)
                    batch.append(doc)
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

        if batch:
            yield batch

    def poll_source(self, start: float, end: float) -> Generator[list[Document], None, None]:
        manifest_path, _ = self._read_active_manifest()
        view_dir = manifest_path.parent / self.corpus_view

        if not view_dir.exists():
            return

        delta_shards = sorted(view_dir.glob("delta-*.jsonl"))
        batch: list[Document] = []
        for shard in delta_shards:
            with open(shard, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        raw_doc = json.loads(line_str)
                    except Exception as e:
                        raise VBPLExportConnectorError(f"Failed to parse line in {shard}") from e

                    doc = self._parse_raw_doc(raw_doc)
                    batch.append(doc)
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

        if batch:
            yield batch

    def retrieve_all_slim_documents(self) -> Generator[list[SlimDocument], None, None]:
        manifest_path, _ = self._read_active_manifest()
        active_file = manifest_path.parent / self.corpus_view / "active-ids.jsonl"

        if not active_file.exists():
            return

        batch: list[SlimDocument] = []
        with open(active_file, "r", encoding="utf-8") as f:
            for line in f:
                doc_id = line.strip()
                if doc_id:
                    batch.append(SlimDocument(id=doc_id))
                    if len(batch) >= self.batch_size:
                        yield batch
                        batch = []

        if batch:
            yield batch
