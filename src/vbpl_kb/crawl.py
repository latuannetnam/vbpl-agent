import hashlib
import json
from datetime import datetime, UTC
from collections.abc import Callable
from vbpl_kb.state import StateStore
from vbpl_kb.vbpl_client import VBPLClient
from vbpl_kb.models import StatusObservation, CatalogEntry
from vbpl_kb.catalog import parse_catalog_entry, classify_catalog_changes
from vbpl_kb.vbpl_fallback import resolve_canonical_page


class CrawlSummary:
    def __init__(
        self,
        detail_count: int,
        failed_ids: list[str],
        coverage: float,
        catalog_complete: bool,
        fetched_detail_count: int = 0,
        changed_or_new_ids: list[str] | None = None,
        tombstone_ids: list[str] | None = None,
        candidate_ids: list[str] | None = None,
    ):
        self.detail_count = detail_count
        self.failed_ids = failed_ids
        self.coverage = coverage
        self.catalog_complete = catalog_complete
        self.fetched_detail_count = fetched_detail_count
        self.changed_or_new_ids = changed_or_new_ids if changed_or_new_ids is not None else []
        self.tombstone_ids = tombstone_ids if tombstone_ids is not None else []
        self.candidate_ids = candidate_ids if candidate_ids is not None else []


ProgressReporter = Callable[[str], None]


class DailyCrawler:
    def __init__(
        self,
        client: VBPLClient,
        store: StateStore,
        progress: ProgressReporter | None = None,
    ):
        self.client = client
        self.store = store
        self.progress = progress

    def _report(self, message: str) -> None:
        if self.progress is not None:
            self.progress(message)

    def run(self, revision: str) -> CrawlSummary:
        run_id = self.store.begin_run(revision)

        # Retrieve baseline from latest successful catalog scan
        baseline_entries = self.store.latest_successful_catalog_entries()

        # Load existing entries for this run_id (in case of resumed/restarted run)
        existing_run_entries = self.store.get_catalog_entries_for_run(run_id)
        current_entries_map: dict[str, CatalogEntry] = {
            entry.vbpl_id: entry for entry in existing_run_entries
        }

        # Discover catalog IDs and entries page-by-page
        page = self.store.next_catalog_page(run_id)
        page_size = 100
        client_settings = getattr(self.client, "settings", None)
        max_pages = getattr(client_settings, "max_pages", None) if client_settings is not None else None

        catalog_complete = True

        while True:
            if max_pages is not None and page > max_pages:
                catalog_complete = False
                break
            try:
                page_docs = self.client.list_catalog_page(page, page_size)
                if not page_docs:
                    break
                page_ids: list[str] = []
                for doc in page_docs:
                    entry = parse_catalog_entry(doc)
                    if entry.vbpl_id:
                        current_entries_map[entry.vbpl_id] = entry
                        page_ids.append(entry.vbpl_id)
                self.store.record_catalog_page(run_id, page, page_ids)
                self._report(
                    f"crawl: catalog page {page} discovered; documents={len(current_entries_map)}"
                )
                page += 1
            except Exception:
                catalog_complete = False
                break

        # Persist unfinalized catalog entries for this run
        self.store.record_catalog_scan(
            run_id, list(current_entries_map.values()), complete=False
        )

        # Classify changes against baseline
        change_set = classify_catalog_changes(baseline_entries, current_entries_map)
        target_ids = list(change_set.changed_or_new_ids)

        fetched_detail_count = 0
        failed_ids: list[str] = []

        # Fetch detail ONLY for new or changed documents
        for processed_count, vbpl_id in enumerate(target_ids, start=1):
            cursor = self.store.conn.cursor()
            cursor.execute(
                "SELECT 1 FROM raw_snapshots WHERE run_id = ? AND vbpl_id = ? AND endpoint = 'detail'",
                (run_id, vbpl_id),
            )
            if cursor.fetchone():
                fetched_detail_count += 1
                continue

            try:
                detail = self.client.get_detail(vbpl_id)
                if not detail.title or not detail.eff_status:
                    resolution = resolve_canonical_page(
                        vbpl_id,
                        self.client.get_canonical_page(vbpl_id),
                        datetime.now(UTC),
                        detail.raw_data,
                    )
                    if not resolution.verified:
                        raise ValueError(resolution.reason)
                    if resolution.title is None or resolution.eff_status is None:
                        raise ValueError("fallback verification returned incomplete data")
                    detail.title = resolution.title
                    detail.eff_status = resolution.eff_status
                    detail.raw_data["title"] = resolution.title
                    detail.raw_data["effStatus"] = {"name": resolution.eff_status}
                    detail.raw_json = json.dumps({"data": detail.raw_data}, ensure_ascii=False)
                    self._report(
                        f"crawl: fallback verified {vbpl_id} (canonical_page)"
                    )

                content_hash = hashlib.sha256(detail.raw_json.encode("utf-8")).hexdigest()
                self.store.record_snapshot(run_id, vbpl_id, "detail", detail.raw_json, content_hash)

                obs = StatusObservation(
                    vbpl_id=vbpl_id,
                    eff_status=detail.eff_status,
                    eff_from=detail.eff_from,
                    checked_at=datetime.now(UTC),
                    content_hash=content_hash,
                    run_id=run_id,
                )
                self.store.record_status(obs)
                self.store.record_document_version(vbpl_id, content_hash, content_hash, run_id)
                fetched_detail_count += 1
            except Exception as exc:
                failed_ids.append(vbpl_id)
                reason = " ".join(str(exc).split())[:200]
                self._report(
                    f"crawl: failed {vbpl_id} ({type(exc).__name__}: {reason})"
                )

            if processed_count % 100 == 0:
                self._report(
                    f"crawl: fetched {fetched_detail_count}/{len(target_ids)} changed documents (failed={len(failed_ids)})"
                )

        # Audit observation for unchanged entries
        for unchanged_entry in change_set.unchanged_entries:
            latest_obs = self.store.latest_status(unchanged_entry.vbpl_id)
            if latest_obs:
                obs = StatusObservation(
                    vbpl_id=unchanged_entry.vbpl_id,
                    eff_status=latest_obs.eff_status,
                    eff_from=latest_obs.eff_from,
                    checked_at=datetime.now(UTC),
                    content_hash=latest_obs.content_hash,
                    run_id=run_id,
                )
                self.store.record_status(obs)

        detail_count = len(change_set.unchanged_entries) + fetched_detail_count
        total_docs = len(current_entries_map)
        candidate_ids: list[str] = []
        tombstone_ids: list[str] = []

        if catalog_complete and len(failed_ids) == 0:
            # Finalize catalog scan completeness
            self.store.record_catalog_scan(
                run_id, list(current_entries_map.values()), complete=True
            )
            candidates, tombstones = self.store.update_removal_candidates(
                set(current_entries_map.keys()), run_id
            )
            candidate_ids = candidates
            tombstone_ids = tombstones
            status = "completed"
            coverage = 1.0 if total_docs > 0 else 0.0
        else:
            status = "partial"
            coverage = detail_count / total_docs if total_docs > 0 and catalog_complete else 0.0

        self.store.finish_run(run_id, status, coverage)
        self._report(
            f"crawl: fetched {detail_count}/{total_docs} documents (failed={len(failed_ids)})"
        )
        self._report(
            f"crawl: {status}; documents={detail_count}/{total_docs} (failed={len(failed_ids)})"
        )

        return CrawlSummary(
            detail_count=detail_count,
            failed_ids=failed_ids,
            coverage=coverage,
            catalog_complete=catalog_complete,
            fetched_detail_count=fetched_detail_count,
            changed_or_new_ids=target_ids,
            tombstone_ids=tombstone_ids,
            candidate_ids=candidate_ids,
        )
