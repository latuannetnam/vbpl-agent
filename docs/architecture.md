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
  -> normalization and legal-status verification
  -> reference resolution
  -> checksummed candidate release
  -> atomic active-release pointer
  -> read-only export mount
  -> VBPL Export Connector
  -> Onyx index
  -> scoped VBPL Legal Agent
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
| Schema, normalization, and references | `src/vbpl_kb/models.py`, `src/vbpl_kb/normalize.py`, `src/vbpl_kb/references.py` |
| Document projection and releases | `src/vbpl_kb/publish.py`, `src/vbpl_kb/releases.py` |
| Legacy diagnostic publisher and connector trigger | `src/vbpl_kb/onyx.py`, `src/vbpl_kb/connector_control.py` |
| Onyx custom connector and frontend overlay | `infra/onyx/overlay/` |
| Local Onyx lifecycle | `scripts/bootstrap-onyx.ps1`, `scripts/start-onyx.ps1`, `infra/onyx/docker-compose.vbpl-*.yml` |

## Release and connector contract

The pipeline writes a candidate release beneath an immutable revision directory,
validates coverage and checksums, then atomically updates
`active-release.json`. The connector reads only the pointed-to active release
through `/app/vbpl-export`; it never reads candidate or temporary paths. A
connector failure preserves the existing index and is retried without deleting
or recreating the connector.

`VBPLExportConnector` implementations must yield `list[Document]` batches from
`poll_source()` and `load_from_state()` using `self.batch_size`. Export
connectors yield every document in the complete promoted manifest and do not
discard records with `changed_after`. The backend, background worker, and web
frontend overlay must be updated together when a custom source changes;
`scripts/bootstrap-onyx.ps1` builds `api_server`, `background`, and
`web_server`.

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
