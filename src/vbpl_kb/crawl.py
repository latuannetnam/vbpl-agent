from collections.abc import Callable
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from typing import Any
from vbpl_kb.catalog import parse_catalog_entry, parse_vbpl_id_int
from vbpl_kb.models import CatalogEntry
from vbpl_kb.repositories import EvidenceRepository
from vbpl_kb.vbpl_client import VBPLClient
from vbpl_kb.vbpl_fallback import resolve_canonical_page


class CrawlSummary:
    def __init__(
        self,
        detail_count: int,
        failed_ids: list[str],
        coverage: float,
        catalog_complete: bool,
        fetched_detail_count: int = 0,
        changed_or_new_ids: list[int] | None = None,
        tombstone_ids: list[int] | None = None,
        candidate_ids: list[int] | None = None,
        cleared_ids: list[int] | None = None,
    ):
        self.detail_count = detail_count
        self.failed_ids = failed_ids
        self.coverage = coverage
        self.catalog_complete = catalog_complete
        self.fetched_detail_count = fetched_detail_count
        self.changed_or_new_ids = changed_or_new_ids if changed_or_new_ids is not None else []
        self.tombstone_ids = tombstone_ids if tombstone_ids is not None else []
        self.candidate_ids = candidate_ids if candidate_ids is not None else []
        self.cleared_ids = cleared_ids if cleared_ids is not None else []


ProgressReporter = Callable[[str], None]


class DailyCrawler:
    def __init__(
        self,
        client: VBPLClient,
        catalog: Any = None,
        evidence: Any = None,
        session: Session | None = None,
        progress: ProgressReporter | None = None,
    ) -> None:
        self.client = client
        self.catalog = catalog
        self.evidence = evidence
        self.session = session
        self.evidence_repo = EvidenceRepository(session) if session else None
        self.progress = progress

    def _report(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def run(self, revision: str) -> CrawlSummary:
        scan_id = self.catalog.begin_scan()

        current_entries: list[CatalogEntry] = []
        page = 1
        page_size = 100
        client_settings = getattr(self.client, "settings", None)
        max_pages = getattr(client_settings, "max_pages", None) if client_settings is not None else None

        catalog_complete = True
        reason = ""

        while True:
            if max_pages is not None and page > max_pages:
                catalog_complete = False
                reason = f"Reached max_pages limit: {max_pages}"
                break
            try:
                raw_bytes, page_docs = self.client.list_catalog_page_with_raw(page, page_size)
                if not page_docs:
                    break

                # Retain evidence for catalog page
                url = f"{getattr(self.client.settings, 'vbpl_gateway_url', 'https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public')}/doc/all"
                ev_obj = self.evidence.put(
                    raw_bytes,
                    media_type="application/json",
                    official_url=url,
                    endpoint="catalog",
                    corpus_revision=revision,
                )
                if self.evidence_repo:
                    self.evidence_repo.persist_evidence_metadata(ev_obj)

                for doc in page_docs:
                    entry = parse_catalog_entry(doc)
                    if entry.vbpl_id:
                        current_entries.append(entry)

                self._report(f"crawl: catalog page {page} discovered; documents={len(current_entries)}")
                page += 1
            except Exception as exc:
                catalog_complete = False
                reason = f"Catalog page discovery failed at page {page}: {exc}"
                break

        if not catalog_complete:
            self.catalog.fail_scan(scan_id, reason)
            return CrawlSummary(
                detail_count=0,
                failed_ids=[],
                coverage=0.0,
                catalog_complete=False,
            )

        entries_by_id = {parse_vbpl_id_int(e.vbpl_id): str(e.vbpl_id) for e in current_entries}
        # Complete scan & compute change set
        change_set = self.catalog.complete_scan(scan_id, current_entries)
        target_ids = change_set.upsert_ids

        fetched_detail_count = 0
        failed_ids: list[str] = []

        # Fetch detail for changed or new documents
        for processed_count, vbpl_id_int in enumerate(target_ids, start=1):
            vbpl_id = entries_by_id.get(vbpl_id_int, str(vbpl_id_int))
            try:
                raw_bytes, detail = self.client.get_detail_with_raw(vbpl_id)
                detail_url = f"{getattr(self.client.settings, 'vbpl_gateway_url', 'https://vbpl-bientap-gateway.moj.gov.vn/api/qtdc/public')}/doc/{vbpl_id}"

                if not detail.title or not detail.eff_status:
                    html_bytes, canonical_html = self.client.get_canonical_page_with_raw(vbpl_id)
                    page_url = f"https://vbpl.vn/van-ban/chi-tiet/--{vbpl_id}"
                    ev_html = self.evidence.put(
                        html_bytes,
                        media_type="text/html",
                        official_url=page_url,
                        endpoint="canonical_page",
                        corpus_revision=revision,
                    )
                    if self.evidence_repo:
                        self.evidence_repo.persist_evidence_metadata(ev_html)
                        self.evidence_repo.record_dependency("instrument", vbpl_id, ev_html.hash_sha256)

                    resolution = resolve_canonical_page(
                        vbpl_id,
                        canonical_html,
                        datetime.now(timezone.utc),
                        detail.raw_data,
                    )
                    if not resolution.verified or not resolution.title or not resolution.eff_status:
                        raise ValueError("fallback verification returned incomplete data")

                    detail.title = resolution.title
                    detail.eff_status = resolution.eff_status

                ev_detail = self.evidence.put(
                    raw_bytes,
                    media_type="application/json",
                    official_url=detail_url,
                    endpoint="detail",
                    corpus_revision=revision,
                )
                if self.evidence_repo:
                    self.evidence_repo.persist_evidence_metadata(ev_detail)
                    self.evidence_repo.record_dependency("instrument", vbpl_id, ev_detail.hash_sha256)

                fetched_detail_count += 1
            except Exception as exc:
                failed_ids.append(vbpl_id)
                reason = " ".join(str(exc).split())[:200]
                self._report(f"crawl: failed {vbpl_id} ({type(exc).__name__}: {reason})")

            if processed_count % 100 == 0:
                self._report(
                    f"crawl: fetched {fetched_detail_count}/{len(target_ids)} changed documents (failed={len(failed_ids)})"
                )

        detail_count = len(current_entries) - len(failed_ids)
        total_docs = len(current_entries)
        coverage = detail_count / total_docs if total_docs > 0 else 1.0

        return CrawlSummary(
            detail_count=detail_count,
            failed_ids=failed_ids,
            coverage=coverage,
            catalog_complete=catalog_complete and len(failed_ids) == 0,
            fetched_detail_count=fetched_detail_count,
            changed_or_new_ids=target_ids,
            tombstone_ids=change_set.tombstone_ids,
            candidate_ids=change_set.removal_candidate_ids,
            cleared_ids=change_set.cleared_ids,
        )
