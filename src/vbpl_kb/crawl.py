import hashlib
from datetime import datetime, UTC
from vbpl_kb.state import StateStore
from vbpl_kb.vbpl_client import VBPLClient
from vbpl_kb.models import StatusObservation

class CrawlSummary:
    def __init__(self, detail_count: int, failed_ids: list[str], coverage: float):
        self.detail_count = detail_count
        self.failed_ids = failed_ids
        self.coverage = coverage

class DailyCrawler:
    def __init__(self, client: VBPLClient, store: StateStore):
        self.client = client
        self.store = store

    def run(self, revision: str) -> CrawlSummary:
        run_id = self.store.begin_run(revision)
        
        # Discover catalog IDs page-by-page
        catalog_ids: list[str] = []
        page = 1
        page_size = 100
        client_settings = getattr(self.client, "settings", None)
        max_pages = getattr(client_settings, "max_pages", None) if client_settings is not None else None
        
        while True:
            if max_pages is not None and page > max_pages:
                break
            try:
                page_docs = self.client.list_catalog_page(page, page_size)
                if not page_docs:
                    break
                for doc in page_docs:
                    if "id" in doc:
                        catalog_ids.append(str(doc["id"]))
                page += 1
            except Exception:
                # If fetching catalog page fails, we stop discovering but proceed to fetch detail for whatever we have
                break

        # Fetch detail for each discovered ID
        detail_count = 0
        failed_ids: list[str] = []
        
        for vbpl_id in catalog_ids:
            cursor = self.store.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM raw_snapshots WHERE run_id = ? AND vbpl_id = ? AND endpoint = 'detail'",
                (run_id, vbpl_id)
            )
            if cursor.fetchone():
                detail_count += 1
                continue

            try:
                detail = self.client.get_detail(vbpl_id)
                # Compute hash
                content_hash = hashlib.sha256(detail.raw_json.encode("utf-8")).hexdigest()
                # Record snapshot
                self.store.record_snapshot(run_id, vbpl_id, "detail", detail.raw_json, content_hash)
                # Record status observation
                obs = StatusObservation(
                    vbpl_id=vbpl_id,
                    eff_status=detail.eff_status,
                    eff_from=detail.eff_from,
                    checked_at=datetime.now(UTC),
                    content_hash=content_hash,
                    run_id=run_id
                )
                self.store.record_status(obs)
                detail_count += 1
            except Exception:
                failed_ids.append(vbpl_id)

        # Calculate coverage
        total = len(catalog_ids)
        coverage = detail_count / total if total > 0 else 1.0
        
        # Determine status
        status = "completed" if len(failed_ids) == 0 else "partial"
        self.store.finish_run(run_id, status, coverage)

        return CrawlSummary(
            detail_count=detail_count,
            failed_ids=failed_ids,
            coverage=coverage
        )
