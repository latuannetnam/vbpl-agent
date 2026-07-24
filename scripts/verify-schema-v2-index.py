"""
Script to verify Schema-v2 metadata completeness across 10 random documents directly from Onyx index.
"""
import sys
import json
import random

CORE_SCHEMA_V2_KEYS = {
    "hierarchy_regime",
    "article4_order",
    "normative_form",
    "authority_group",
    "issuer_type",
    "classification_status",
    "classification_source",
    "classification_version",
    "is_normative",
    "legal_status_raw",
    "legal_status_normalized",
    "verified_at",
    "status_source",
    "effective_from",
    "effective_to",
    "jurisdiction_level",
    "jurisdiction_code",
    "jurisdiction_name",
    "transitional_until",
    "source_url",
    "corpus_revision",
    "status_evidence_hash",
    "citation_structure",
    "document_number",
    "title",
}


def main() -> None:
    if len(sys.argv) > 1:
        doc_ids = sys.argv[1:]
    else:
        doc_ids = [
            "178717", "175440", "178314", "176730", "178716",
            "176696", "175258", "178340", "179644", "184843"
        ]

    print(f"Verifying {len(doc_ids)} random document IDs against Onyx OpenSearch index:")
    print(f"IDs: {doc_ids}\n")

    try:
        from onyx.db.engine.sql_engine import SqlEngine, get_session
        from onyx.db.search_settings import get_current_search_settings
        from onyx.document_index.factory import get_default_document_index
        from onyx.document_index.interfaces_new import DocumentSectionRequest
        from onyx.context.search.models import IndexFilters

        SqlEngine.init_engine(pool_size=5, max_overflow=10)
        
        passed_count = 0
        failed_count = 0

        for session in get_session():
            search_settings = get_current_search_settings(session)
            index = get_default_document_index(search_settings, None, db_session=session)

            for idx, doc_id in enumerate(doc_ids, start=1):
                clean_id = doc_id.replace("vbpl:", "")
                full_doc_id = f"vbpl:{clean_id}"
                reqs = [
                    DocumentSectionRequest(document_id=full_doc_id, section_id="dieu-1"),
                    DocumentSectionRequest(document_id=full_doc_id, section_id="toan-van"),
                ]
                chunks = index.id_based_retrieval(reqs, filters=IndexFilters(access_control_list=None))
                
                if not chunks:
                    print(f"[{idx}/{len(doc_ids)}] FAIL - {full_doc_id} -> No chunks found in index")
                    failed_count += 1
                    continue

                chunk = chunks[0]
                meta = chunk.metadata or {}
                missing_keys = CORE_SCHEMA_V2_KEYS - set(meta.keys())

                if missing_keys:
                    print(f"[{idx}/{len(doc_ids)}] FAIL - {full_doc_id} -> Missing core keys: {missing_keys}")
                    failed_count += 1
                else:
                    rel_tokens = meta.get("relation_tokens") or []
                    print(f"[{idx}/{len(doc_ids)}] PASS - {full_doc_id}")
                    print(f"   Title: {meta.get('title', '')[:75]}...")
                    print(f"   Authority: {meta.get('authority_group')} (Order {meta.get('article4_order')}) | Status: {meta.get('legal_status_normalized')} | Relations: {len(rel_tokens)} tokens\n")
                    passed_count += 1
            break

        print(f"==========================================")
        print(f"Schema-v2 Metadata Verification Summary:")
        print(f"Passed: {passed_count}/{len(doc_ids)}")
        print(f"Failed: {failed_count}/{len(doc_ids)}")
        print(f"==========================================")

    except Exception as e:
        print(f"Error executing verification script: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
