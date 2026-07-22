# VBPL Knowledge Base: Onyx CE Custom Connector Design

**Status:** Approved for implementation planning
**Date:** 2026-07-22
**Scope:** Internal Release 1

## Purpose

Provide an internal Vietnamese legal-document knowledge base backed by official
VBPL data. Users work only through Onyx Community Edition (CE) Chat and a
dedicated VBPL Legal Agent. Every legal conclusion must be grounded in retrieved
official material and state the evidence used to establish legal status.

The official VBPL API and canonical VBPL pages remain the source of truth. Onyx
is the search, retrieval, and conversation layer only.

## Decisions

- Use Onyx CE only. Do not rely on the Business/Enterprise Search Mode UI.
- Release 1 exposes stock Onyx Chat UI and a scoped `VBPL Legal Agent`; it does
  not expose a standalone search-only interface.
- Replace the production direct `/onyx-api/ingestion` publisher with a project
  custom Onyx connector that reads a Docker shared volume.
- Use a single persistent connector with daily incremental polling.
- Use complete connector re-indexing only for recovery or intentional full
  corpus refreshes.
- Defer blue/green connector replacement and global index switchover. They are
  too expensive for the daily 37k-document refresh workload.
- Treat legal-status claims as fail-closed per document: a document with an
  unverified, conflicting, or stale status is never described as currently
  effective.

## Architecture

```text
Official VBPL API + canonical VBPL pages
  -> crawl cache and SQLite run state
  -> normalize, validate legal status, resolve legal references
  -> immutable candidate release (documents + checksummed manifest)
  -> atomic active-release pointer
  -> read-only shared Docker volume
  -> VBPL Export Connector in custom Onyx CE backend image
  -> Onyx search index
  -> VBPL Legal Agent in Onyx Chat UI
```

The crawler/pipeline owns all source acquisition, normalisation, validation,
and release publication. The connector owns only reading an already-complete
export and turning it into Onyx `Document` objects. Onyx owns chunking,
embedding, indexing, retrieval, citations in its source panel, and the Chat UI.

## Source release contract

The pipeline writes all files for a revision beneath a candidate directory and
does not expose it to the connector while it is being created. A release has:

- `release_id`, creation time, source catalog coverage, and schema version;
- document files with content hashes;
- a JSONL/JSON manifest containing one entry per document;
- validation results and aggregate counts;
- a manifest checksum.

Only after all validation succeeds does the pipeline atomically replace a small
`active-release.json` pointer. The pointer names the immutable release and
contains the expected manifest checksum. The connector accepts only a complete
release whose pointer, manifest, and per-document checksums agree. It must
never read temporary or candidate paths.

Candidate validation requires no duplicate official IDs, valid manifest and
content checksums, and an explicit outcome for every fetched record. A source
record may be indexed with `unknown` status, but a malformed or unavailable
record must be visible in coverage and run diagnostics rather than silently
discarded.

## Normalized document and legal status

Each indexed legal instrument has a stable official VBPL identity and canonical
VBPL URL. Its normalized source record contains:

- official ID, number/symbol, title, issuer, and relevant dates;
- canonical URL and raw-source checksum;
- `legal_status_raw`, preserving the official label without reinterpretation;
- `legal_status_normalized`: `in_force`, `partially_repealed`, `repealed`,
  `expired`, `suspended`, `not_yet_effective`, or `unknown`;
- `status_source`, `verified_at`, and status-evidence checksum;
- article/section text retaining headings such as `Điều 3`;
- outbound legal references and a document content hash.

The status source is either the official API field or an explicit canonical-page
fallback. Current-status claims require a verified normalized status within the
configured daily freshness window. Missing, contradictory, or unparseable
evidence becomes `unknown`: the source remains available as historical material
but cannot support a claim that it is currently effective.

## Cross-reference model

References are extracted deterministically from source text. Each has a source
document and article/section, original quoted reference, normalized target
number/symbol where possible, resolved official target ID/URL where possible,
and one of `amends`, `supplements`, `replaces`, `repeals`, `guides`,
`refers_to`, or `unresolved`.

A mere reference never changes the source document's legal status. Status is
derived only from official status evidence. Unresolved references remain
searchable and are reported as unresolved rather than guessed.

## Onyx custom connector

The current Onyx connector registry is static, so this is a small source
extension built into a derivative Onyx CE image, not a runtime plugin setting.
The project commits connector code, tests, a source overlay/patch, and an Onyx
revision lock. The downloaded upstream checkout remains ignored.

The `VBPL Export Connector` has no external credentials and receives one fixed
read-only export root.

- `LoadConnector` reads every document in the active release for bootstrap or
  an operator-requested complete re-index.
- `PollConnector` reads only documents changed since the last successful
  release/poll window for daily sync.
- Release 1 intentionally omits automatic `SlimConnector` pruning. A VBPL
  catalog disappearance must not erase historical legal material; status
  changes are emitted as document updates instead.

Connector documents use the official VBPL ID as their stable identifier,
canonical VBPL URL as link/source metadata, article-headed content, and
structured status/reference metadata. The background worker receives the
read-only export mount. API and worker services use the same derivative backend
image; the web UI, model servers, and data stores do not receive the mount.

## Daily sync and recovery

```text
schedule
  -> crawl/resume local cache
  -> build and validate candidate release
  -> atomically update active pointer
  -> trigger connector poll
  -> wait for indexing success and validate results
  -> store release/run outcome in SQLite and stdout logs
```

Network failures retry with bounded backoff and resume from cached document
state. A candidate validation failure does not update the active pointer. A
connector failure preserves the already-indexed corpus, is recorded visibly,
and may be retried; it must not automatically delete or recreate the connector.
Full recovery uses Onyx's complete connector re-index after the source export
is corrected.

Normal connector re-indexing is not an index-wide atomic revision switch: Onyx
updates the active index as batches finish. Release 1 therefore guarantees an
atomic *source-export* switch and per-document status fail-closed behavior, not
an atomic whole-index snapshot. Sync runs should use an off-hours window.

## Agent and citation contract

The `VBPL Legal Agent` is explicitly scoped to the VBPL connector/document set
and uses Internal Search only. Web search, code execution, and write actions
are disabled for it.

Its instructions require that every legal conclusion:

- use retrieved VBPL evidence;
- include document number/title, relevant article or section, legal-status
  label, verification date, and canonical VBPL URL;
- distinguish a document's own legal status from references to other documents;
- return `not established from indexed official sources` when evidence is
  absent, conflicting, or stale;
- never present `unknown` status as currently effective.

Onyx's normal source/citation panel remains available. Structured citation text
in the response makes the evidence portable into internal legal notes.

## Deployment and provider model

The repository owns `infra/onyx/` configuration, the Onyx revision lock,
connector overlay, custom Dockerfile, and lifecycle scripts. The downloaded
`.onyx/onyx/` source checkout and persistent `data/vbpl/` state remain ignored.
Bootstrap verifies the pinned revision, applies the committed overlay, and
builds the custom image. An Onyx upgrade is deliberate: update the lock, rebuild,
and run connector compatibility tests.

Onyx Standard is used for its connector workers and indexing services. Only the
configured web UI port is exposed to the host; OpenSearch, Postgres, Redis,
MinIO, and model services stay on the private Compose network. The host GPU is
assigned only to Onyx indexing/inference model-server containers when enabled.

The Chat UI may use approved cloud and on-premise providers. Provider selection
does not alter retrieval, legal-status verification, or citation rules.
Credentials remain in uncommitted environment files and must be redacted from
logs.

## Security boundary

Release 1 is an internal, trusted-user system with one operational administrator.
It includes local/private Docker volumes, limited host exposure, read-only source
exports, uncommitted secrets, and run-level audit records. It deliberately
defers SSO, SCIM, source ACL synchronization, enterprise credential encryption,
SIEM/query-history integration, query hooks, and a cryptographic index-wide
revision gate. These are future hardening items, not claims made by Release 1.

## Acceptance criteria

1. A fresh bootstrap indexes a representative VBPL sample through the connector
   rather than the direct ingestion API.
2. A daily incremental update changes a legal status and the agent cites the
   new status and verification date.
3. A missing-status document is searchable as `unknown`, but the agent refuses
   to call it currently effective.
4. A cross-reference query returns source provision and resolved/unresolved
   target without inventing legal effect.
5. An interrupted crawl resumes without refetching successful cached records.
6. Candidate validation failure leaves the previous active export unchanged.
7. Connector failure preserves prior indexed documents and produces an
   operator-visible failure record.
8. One cloud and one on-premise model pass the same grounded-citation test.
9. The UI provides normal Chat and the VBPL Legal Agent without relying on
   gated Search Mode.

## Non-goals for Release 1

- Stock Onyx standalone Search Mode/Search-only UI.
- Daily blue/green full-corpus connector replacement.
- Daily global search-index switchover.
- Automatic deletion of legal documents absent from a single crawl.
- Automated legal advice or unsupported claims of current legal force.
