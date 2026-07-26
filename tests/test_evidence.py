from datetime import datetime, timezone
import pytest
from vbpl_kb.evidence import EvidenceStore, InvalidEvidenceHashError


def test_evidence_store_put_deduplicates_by_sha256(tmp_path) -> None:
    store = EvidenceStore(base_dir=tmp_path)
    content = b"<html><body>Test VBPL Content</body></html>"

    obj1 = store.put(
        content,
        media_type="text/html",
        official_url="https://vbpl.vn/detail/123",
        endpoint="detail",
        corpus_revision="rev-001",
    )
    obj2 = store.put(
        content,
        media_type="text/html",
        official_url="https://vbpl.vn/detail/123",
        endpoint="detail",
        corpus_revision="rev-001",
    )

    assert obj1.hash_sha256 == obj2.hash_sha256
    assert len(obj1.hash_sha256) == 64
    assert obj1.size_bytes == len(content)

    # Check path layout: /base_dir/sha256/<first-two>/<sha256>
    first_two = obj1.hash_sha256[:2]
    expected_path = tmp_path / "sha256" / first_two / obj1.hash_sha256
    assert expected_path.exists()
    assert expected_path.read_bytes() == content


def test_evidence_store_open_verifies_checksum(tmp_path) -> None:
    store = EvidenceStore(base_dir=tmp_path)
    content = b"Official response payload"
    obj = store.put(
        content,
        media_type="application/json",
        official_url="https://vbpl.vn/api/detail/1",
        endpoint="detail",
        corpus_revision="rev-001",
    )

    with store.open(obj.hash_sha256) as f:
        read_bytes = f.read()
    assert read_bytes == content


def test_evidence_store_rejects_path_traversal(tmp_path) -> None:
    store = EvidenceStore(base_dir=tmp_path)

    with pytest.raises(InvalidEvidenceHashError):
        store.open("../../../etc/passwd")

    with pytest.raises(InvalidEvidenceHashError):
        store.open("invalid_hash_len")
