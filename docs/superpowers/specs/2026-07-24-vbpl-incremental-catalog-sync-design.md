# VBPL Incremental Catalog-to-Onyx Sync Design

**Status:** Approved design; implementation not started.

**Date:** 2026-07-24

## Goal

Update the internal Onyx VBPL corpus incrementally when the official VBPL
catalog gains, changes, or removes a document. Avoid detail retrieval,
normalization, embedding, and indexing for unchanged documents while retaining
the validated immutable full release required for recovery and legal evidence.

## Source capability and boundary

The official public catalog endpoint returns a stable `id`, `updatedDate`,
`effStatus`, `effTo`, document metadata, and `isNew`. The portal uses
`isNew=true` to list recently added documents. It does not publish a reliable
documented change cursor, `changedSince` query, or deletion/tombstone feed;
`updatedDate` can be null and is not a safe cursor.

Each run must therefore complete a metadata-only catalog scan. `isNew` is only
an optimization hint and must never be the sole change detector. Catalog
completion is the authority for detecting an absent ID; a partial scan cannot
create removals or advance a synchronization watermark.

The official VBPL API and canonical pages remain authoritative. The pipeline
continues to retain raw evidence, legal status verification time, source URL,
corpus revision, and provision structure. Onyx is an indexing and retrieval
consumer only.

## Architecture

```text
complete official VBPL catalog scan (metadata only)
  -> SQLite catalog observations and deterministic fingerprints
  -> new, changed, unchanged, and missing-ID classification
  -> official detail fetch only for new and changed IDs
  -> legal-status validation, normalization, provisions, and references
  -> checksummed immutable full candidate release + immutable delta batch
  -> atomic full-release pointer and promoted-delta ledger
  -> VBPL Export Connector incremental poll (upserts only)
  -> Onyx index; separate lightweight ID pruning for confirmed removals
```

The existing full release remains the only recovery and full-reindex input.
The delta batch is a transport optimization, not a replacement for the full
release. A connector reads only promoted data through the existing read-only
export mount.

## Persisted state

The implementation will add logically separate, append-preserving state:

- **Catalog observation:** one record per official ID per successful catalog
  scan, its deterministic catalog fingerprint, raw catalog metadata, and
  observation time.
- **Document version:** latest accepted detail fingerprint, content hash,
  index-metadata hash, audit-metadata hash, source-schema version,
  normalizer version, and projection version for each official ID.
- **Removal candidate:** an ID absent from one or more complete catalog scans,
  with the number of consecutive successful absences. It is cleared if the ID
  reappears.
- **Delta batch:** immutable promoted record containing source scan ID, full
  release ID, upserts, tombstones, checksums, pipeline-assigned `changed_at`,
  and indexing outcome/retry state.

The catalog fingerprint contains the fields whose change may affect the
indexed legal representation: stable ID, `updatedDate`, `effStatus`, `effTo`,
title, document number, document type, and other source catalog fields used by
normalization. It is computed from canonical JSON, not response ordering.

## Classification and actions

| Classification | Required action |
| --- | --- |
| New ID | Fetch official detail, validate, normalize, write full release entry and delta upsert. |
| Changed catalog fingerprint | Fetch official detail, validate, and produce an upsert only if a persisted representation hash changed. |
| Unchanged fingerprint | Do not fetch detail or emit an Onyx document. |
| First complete-scan absence | Record a removal candidate; do not remove it from Onyx. |
| Second consecutive complete-scan absence | Create a tombstone delta and permit Onyx pruning. |
| Partial/failed scan or failed changed-detail fetch | Do not promote a delta, advance the successful scan watermark, or increment absence counts. |

A detail 404, timeout, source schema error, unverified fallback, stale or
invalid legal-status evidence, or checksum failure is not deletion evidence.
It blocks the candidate and preserves the prior active release and index.

## Onyx connector contract

`load_from_state()` continues to emit the complete validated active release
only for first indexing, explicit recovery, or an approved full rebuild.

`poll_source(start, end)` reads promoted delta batches with
`changed_at` inside the Onyx window and emits only upsert documents. The
pipeline assigns `changed_at` at successful promotion; it does not use the
possibly absent or unreliable VBPL `updatedDate` as the connector cursor.
Stable document identities remain `vbpl:<official-id>`.

Confirmed removals are enumerated through an ID-only pruning path. The custom
connector should implement Onyx's slim-ID interface when the pinned Onyx
version permits it; otherwise, its existing pruning fallback must enumerate
the active full manifest without embedding documents. In either case, a
tombstone is eligible for Onyx removal only after the two-scan confirmation.

If an Onyx indexing or pruning attempt fails, the promoted immutable delta
remains pending and is retried unchanged. The pipeline must not create a new
delta, rebuild the whole corpus, delete the connector, or clear an index to
recover.

## Metadata and schema evolution

Three independently versioned fingerprints define work scope:

- **Content hash:** document text or provision structure changed; reprocess
  the Onyx document.
- **Index-metadata hash:** retrieval-relevant metadata, legal status, source
  link, or citation metadata changed; send an Onyx upsert without treating it
  as a new document identity.
- **Audit-metadata hash:** provenance-only metadata changed; preserve it in
  local evidence without needless Onyx work.

Every document version and delta records `source_schema_version`,
`normalizer_version`, and `projection_schema_version`.

Backward-compatible source additions are normalized incrementally. A required
source-field rename/removal or unparseable type quarantines the affected
document and blocks the delta promotion until an adapter and regression
fixtures support both shapes. A change that alters a stable document ID,
section boundaries, embedding text, or the meaning of indexed metadata is a
breaking projection migration and requires an explicit approved full
re-index; it must not be silently mixed into ordinary deltas.

## Failure and rollback semantics

- Only a complete catalog and a fully validated candidate may update the
  successful scan watermark.
- The active full-release pointer is atomically promoted only after checksum,
  schema, and legal-evidence validation.
- Failed candidates leave the prior full release, promoted-delta cursor, and
  Onyx corpus in place.
- Local raw evidence and tombstones are retained. A removed source document is
  removed from Onyx retrieval, not erased from the audit trail.
- Rollback atomically restores the previous validated full-release pointer and
  replays the corresponding approved delta/full re-index procedure; it never
  deletes SQLite state, raw snapshots, releases, the connector, the Onyx index,
  or Docker volumes.

## Verification requirements

Focused tests must demonstrate:

1. A new ID causes one detail fetch and one delta upsert.
2. A changed catalog fingerprint fetches detail; an unchanged representation
   emits no document.
3. Content, index-metadata, and audit-metadata changes follow their distinct
   update paths.
4. One absence does not remove a document; two consecutive complete absences
   create exactly one tombstone; reappearance clears the candidate.
5. A partial catalog, detail error, invalid legal-status evidence, source
   schema incompatibility, checksum failure, or failed Onyx attempt cannot
   advance a cursor or remove a document.
6. Retrying an already-promoted delta is idempotent.
7. `poll_source()` returns only delta upserts in its time window, while
   `load_from_state()` returns the complete validated active release.
8. A breaking projection version blocks incremental publication and requires
   the explicit full-reindex path.

The implementation must run the repository's focused tests and the required
full pytest, Ruff, and mypy verification set before commit.

## Documentation completion requirement

After the incremental synchronization behavior has been implemented and
verified, update `AGENTS.md` and the current canonical documentation that owns
the affected architecture, development workflow, and operations. Document the
actual supported catalog-reconciliation, delta, deletion-confirmation,
recovery, and full-reindex behavior; do not update current guidance in advance
of implementation. Keep `AGENTS.md` and README as concise entrypoints and do
not route coding agents to this dated design specification as implementation
guidance.

## Out of scope

- Treating the Hugging Face dataset as current-law or change-feed authority.
- Inferring legal effects from ordinary citations or catalog metadata.
- Deleting historical evidence or infrastructure state to recover a run.
- Replacing the validated export connector with the legacy direct-ingestion
  API.
- Promising an event/webhook feed from VBPL where the official public service
  has not exposed one.
