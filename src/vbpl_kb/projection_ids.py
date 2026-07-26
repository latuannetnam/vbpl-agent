import hashlib


def hash_string(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def build_current_article_id(official_source_id: str, materialized_path: str) -> str:
    path_hash = hash_string(materialized_path)
    return f"vbpl:{official_source_id}:current:article:{path_hash}"


def build_current_atomic_id(official_source_id: str, materialized_path: str) -> str:
    path_hash = hash_string(materialized_path)
    return f"vbpl:{official_source_id}:current:atomic:{path_hash}"


def build_current_relation_id(official_source_id: str, logical_edge_hash: str) -> str:
    return f"vbpl:{official_source_id}:current:relation:{logical_edge_hash[:16]}"


def build_history_article_id(official_source_id: str, version_hash: str, materialized_path: str) -> str:
    path_hash = hash_string(materialized_path)
    return f"vbpl:{official_source_id}:history:{version_hash[:16]}:article:{path_hash}"


def build_history_atomic_id(official_source_id: str, version_hash: str, materialized_path: str) -> str:
    path_hash = hash_string(materialized_path)
    return f"vbpl:{official_source_id}:history:{version_hash[:16]}:atomic:{path_hash}"


def build_history_relation_id(official_source_id: str, version_hash: str, logical_edge_hash: str) -> str:
    return f"vbpl:{official_source_id}:history:{version_hash[:16]}:relation:{logical_edge_hash[:16]}"


def build_evidence_doc_id(official_source_id: str, evidence_kind: str, evidence_hash: str) -> str:
    return f"vbpl:{official_source_id}:evidence:{evidence_kind}:{evidence_hash}"
