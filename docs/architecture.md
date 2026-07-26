# VBPL Knowledge Base Architecture

**Status:** Current
**Applies to:** Pipeline, canonical PostgreSQL database, multi-resolution projections, release, connector, Onyx-overlay, and infrastructure changes.
**Use for:** Understanding component boundaries, code ownership, data flow, and implementation constraints.
**Do not use for:** Docker recovery commands or configuring the running Onyx Legal Agent.

## System boundary

The official VBPL public gateway API and canonical VBPL pages are the legal
source. The pipeline acquires and validates content-addressed evidence into a
canonical PostgreSQL legal database (18 canonical tables); the release builder
publishes complete multi-resolution sharded releases (Current, History, Evidence);
distinct custom Onyx connector instances index their respective views; Onyx provides
retrieval and chat. Onyx and the Hugging Face dataset never establish legal force.

## Data flow and ownership

```text
Official VBPL API and canonical pages
  -> Raw content-addressed evidence store (SHA-256) & PostgreSQL database (18 tables)
  -> Immutable instrument versions, ordered legal tree parsing, authority classification, & applicability envelopes
  -> Verified legal-reference graph and relation tokens
  -> Multi-resolution projection engine (Current, History, Evidence views)
  -> Checksummed sharded release manifests beneath data/exports/releases/<release-id>/
  -> Atomic active-release pointer (data/exports/active-release.json)
  -> Read-only export mount
  -> 3 VBPLExportConnector instances (vbpl_current, vbpl_history, vbpl_evidence)
  -> Onyx OpenSearch index with Schema-v2 metadata
  -> Scoped VBPL Legal Agent with multi-resolution retrieval
```

The crawler owns acquisition and resume. The database models and repositories own
canonical legal state. The release builder owns multi-resolution sharded export,
validation, and active-pointer promotion. The connector instances only stream JSONL
document shards for their configured view into Onyx. Onyx owns chunking, embedding,
indexing, retrieval, and the Chat UI.

## Implementation map

| Area | Primary files |
| --- | --- |
| Database models & advisory locking | `src/vbpl_kb/db.py`, `src/vbpl_kb/db_models.py`, `migrations/` |
| Content-addressed evidence store & repositories | `src/vbpl_kb/evidence.py`, `src/vbpl_kb/repositories.py` |
| Tree parsing & canonicalization | `src/vbpl_kb/legal_tree.py`, `src/vbpl_kb/canonicalize.py` |
| Legal semantics, authority & applicability | `src/vbpl_kb/legal_semantics.py`, `src/vbpl_kb/authority.py`, `src/vbpl_kb/applicability.py`, `src/vbpl_kb/references.py` |
| Multi-resolution projection engine | `src/vbpl_kb/projection_ids.py`, `src/vbpl_kb/projection.py` |
| Sharded releases, validation & promotion | `publish.py`, `src/vbpl_kb/releases.py` |
| Connector & Onyx integration | `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`, `scripts/verify-schema-v2-index.py` |
| Local Onyx lifecycle | `scripts/bootstrap-onyx.ps1`, `scripts/start-onyx.ps1`, `docker-compose.vbpl.yml` |

## Multi-resolution view contract

1. **Current View**: One-section documents for active, in-force legal articles and atomic provisions. Excludes repealed/expired instruments and stale observations.
2. **History View**: Immutable historical legal versions for point-in-time point-of-law analysis.
3. **Evidence View**: Verified evidence records, crawl logs, and acquisition metadata.

Each view is streamed independently by a dedicated connector instance (`vbpl_current`, `vbpl_history`, `vbpl_evidence`) bound to its respective Document Set.

## Dependency rules

The standard daily path is execution via `publish.py` followed by persistent connector sync. The host UI port is configurable with `ONYX_WEB_UI_PORT`; pipeline containers reach Onyx internally through the project-owned Docker network.
