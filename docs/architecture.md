# VBPL Knowledge Base Architecture

**Status:** Current
**Applies to:** Pipeline, release, connector, Onyx-overlay, and infrastructure changes.
**Use for:** Understanding component boundaries, code ownership, data flow, and implementation constraints.
**Do not use for:** Docker recovery commands or configuring the running Onyx Legal Agent.

## System boundary

The official VBPL public gateway API and canonical VBPL pages are the legal
source. The pipeline acquires and validates that evidence; the release exporter
publishes complete immutable releases; the custom Onyx connector indexes an
already-promoted release; Onyx provides retrieval and chat. Onyx and the Hugging
Face dataset never establish legal force.

## Data flow and ownership

```text
Official VBPL API and canonical pages
  -> raw snapshots and SQLite state
  -> normalization, authority classification, applicability envelope, and deterministic provision splitting
  -> verified legal-reference graph and relation tokens
  -> checksummed schema-v2 candidate release
  -> atomic active-release pointer
  -> read-only export mount
  -> VBPL Export Connector (schema-v2 section-preserving)
  -> Onyx index
  -> scoped VBPL Legal Agent with staged authority bundle retrieval
```

The crawler owns acquisition and resume. The normalizer and state layer own
recorded evidence. The release layer owns validation and active-pointer
promotion. The connector only converts a complete active release into Onyx
documents. Onyx owns chunking, embedding, indexing, retrieval, and the Chat UI.

## Implementation map

| Area | Primary files |
| --- | --- |
| Settings and CLI | `src/vbpl_kb/config.py`, `src/vbpl_kb/cli.py` |
| Official API and canonical-page fallback | `src/vbpl_kb/vbpl_client.py`, `src/vbpl_kb/vbpl_fallback.py` |
| Crawl and persisted source state | `src/vbpl_kb/crawl.py`, `src/vbpl_kb/state.py` |
| Schema, normalization, authority & provisions | `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `src/vbpl_kb/authority.py`, `src/vbpl_kb/applicability.py`, `src/vbpl_kb/provisions.py` |
| References and legal relationship graph | `src/vbpl_kb/references.py` |
| Document projection, evaluation & releases | `src/vbpl_kb/publish.py`, `src/vbpl_kb/releases.py`, `src/vbpl_kb/evaluate.py`, `src/vbpl_kb/acceptance.py` |
| Connector trigger & Onyx chat client | `src/vbpl_kb/onyx.py`, `src/vbpl_kb/connector_control.py`, `src/vbpl_kb/onyx_chat.py` |
| Onyx custom connector and frontend overlay | `infra/onyx/overlay/` |
| Local Onyx lifecycle | `scripts/bootstrap-onyx.ps1`, `scripts/start-onyx.ps1`, `infra/onyx/docker-compose.vbpl-*.yml` |

## Release, connector, and incremental sync contract

The pipeline enumerates the complete official VBPL catalog page-by-page and computes a canonical metadata fingerprint per document. Only newly observed or materially changed fingerprints trigger a detail fetch and normalized-document update. Two consecutive successful complete catalog scans are required before a missing document becomes a confirmed tombstone; an incomplete or failing catalog scan produces no tombstones.

The pipeline writes candidate releases beneath immutable revision directories, validates coverage, schemas, and checksums, and updates `active-release.json`. Each promoted release publishes an immutable full manifest plus a separate `delta-manifest.json` recording upsert document IDs and tombstone IDs.

`VBPLExportConnector` implements `LoadConnector`, `PollConnector`, and `SlimConnector`. `load_from_state()` streams the full active release. `poll_source()` reads promoted delta manifests for incremental upserts. `retrieve_all_slim_documents()` returns all active document IDs from the active full release, allowing Onyx to prune confirmed tombstones during indexing.
The backend, background worker, and web frontend overlay must be updated together when a custom source changes; `scripts/bootstrap-onyx.ps1` builds `api_server`, `background`, and `web_server`.

## Dependency rules

The standard daily path is `run-daily` followed by the persistent VBPL Export
Connector. `publish-legacy` is diagnostic-only; do not add a production
dependency on direct Onyx ingestion APIs. The exported corpus is mounted
read-only in the connector services. The host UI port is configurable with
`ONYX_WEB_UI_PORT`; pipeline containers reach Onyx internally through the
project-owned Docker network, not a host UI URL.

## Background

Historical plans and specifications preserve the rationale for prior decisions.
This document is the current implementation instruction; consult a historical
record only when this document identifies an unresolved decision that it does
not describe.
