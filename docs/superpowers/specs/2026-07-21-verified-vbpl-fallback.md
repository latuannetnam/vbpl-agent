# Verified VBPL fallback and quarantine

## Objective

Keep the active legal knowledge base usable when official VBPL detail API
records are incomplete, without inferring a legal status from editorial or
workflow fields.

## Resolution policy

1. Use the official detail API as the primary title and legal-status source.
2. When `title` or `effStatus.name` is missing, fetch only that document's
   canonical `vbpl.vn` page.
3. Accept a fallback only when the canonical page contains an explicit title and
   an explicit legal-effect label. Record the page URL, method, and timestamp
   alongside the resolved values.
4. Never derive legal effect from `status`, `reviewStatus`, `isEffectAllDocument`,
   publication flags, or a prior snapshot.
5. If either required value remains unverified, record a quarantine outcome with
   ID, missing fields, source URLs, and reason. The raw API response remains in
   the local audit store.

## Promotion policy

- A document is publishable only when title and legal status were explicitly
  verified in the current run.
- A malformed document is excluded from the active corpus, rather than blocking
  publication of other verified documents.
- A previously active document that cannot be currently verified is removed from
  the active Onyx projection and retained only in audit/quarantine state.
- Run status reports verified, fallback-verified, and quarantined counts. It is
  `completed` when catalog discovery completes, even when quarantined records
  exist; the quality report makes the exclusion explicit.

## Provenance and operations

- Onyx metadata adds `status_source_url` and `status_source_method` (`api` or
  `canonical_page`).
- Docker logs emit fallback success and quarantine events with document IDs and
  reasons, never response bodies or secrets.
- Daily retries reuse prior raw snapshots only when their current-run resolution
  outcome was verified; quarantined entries are retried.

## Acceptance criteria

- The current malformed IDs are either fallback-verified from canonical VBPL or
  quarantined with the exact missing field.
- No indexed document has an inferred legal status.
- Verified documents from a partially malformed catalog are published.
- Existing active projections for newly quarantined documents are deleted.
- Tests cover API resolution, canonical fallback success, quarantine, promotion,
  and deletion safety.
