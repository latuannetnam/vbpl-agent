# VBPL FalkorDB Graph-Augmented Search Design

**Status:** Approved in design discussion; pending written-spec review
**Date:** 2026-07-30
**Scope:** Mandatory relationship-graph augmentation for the VBPL Legal Current
and VBPL Legal Historical agents running in Onyx Community Edition (CE).

## 1. Purpose

Improve retrieval recall for legally related instruments and provisions,
especially amendments, supplements, repeals, replacements, legal bases, and
implementation guidance. The graph must help assemble a complete authority
bundle even when related provisions do not share enough wording to rank highly
in ordinary semantic or keyword search.

The graph is a derived retrieval index. It never establishes legal force,
current status, applicability, or a legal-effect relationship. PostgreSQL,
official VBPL evidence, and the validated release pipeline remain authoritative.

## 2. Approved decisions

- Graph augmentation is mandatory for every VBPL Legal Agent query.
- Both instrument-level and provision-level relationships are in scope.
- Current-law and point-in-time historical queries are in scope.
- Evidence records support and audit graph edges but are not an independent
  graph-expansion corpus.
- A graph failure, stale graph, revision mismatch, incomplete traversal, or
  missing graph target in Onyx blocks a legal conclusion.
- MVP latency is measured and reported but is not a pass/fail gate.
- The user experience remains the native Onyx CE Chat UI. The design does not
  depend on the standalone Search UI.
- One visible `internal_search` action performs two deterministic retrieval
  phases with mandatory graph expansion between them.
- The Onyx CE overlay enforces the sequence in backend code. Agent prompts do
  not enforce correctness-critical tool ordering.

## 3. Non-goals

- Replacing PostgreSQL as the canonical legal database.
- Replacing Onyx/OpenSearch as the content retrieval and citation system.
- Allowing an LLM to generate arbitrary Cypher.
- Treating text-extracted relationship candidates as verified legal effects.
- Serving the VBPL Evidence view as an answer corpus for ordinary legal
  questions.
- Enabling Onyx Search UI in CE.
- Blue/green Onyx index deployment or a latency service-level objective in the
  MVP.

## 4. Existing system boundary

The existing flow is:

```text
Official VBPL API and canonical pages
  -> retained raw evidence
  -> canonical PostgreSQL legal database
  -> validated multi-resolution release
  -> VBPL Export Connectors
  -> Onyx/OpenSearch
  -> scoped VBPL Legal Agents in native Chat UI
```

The repository already provides canonical instruments, immutable versions,
ordered legal nodes, applicability envelopes, verified legal relations,
multi-resolution projection IDs, and source-grounded Onyx acceptance. The new
graph layer projects those existing contracts; it does not introduce a second
legal-semantics pipeline.

## 5. Architecture

### 5.1 Canonical PostgreSQL

PostgreSQL remains the source of truth for:

- instruments and immutable instrument versions;
- provision structure and stable legal-node identifiers;
- authority classification and applicability;
- official status observations and freshness;
- verified and unresolved legal relations;
- retained evidence hashes and source references.

Only relationships accepted by the canonical legal-data policy can become
searchable graph edges.

### 5.2 Graph Projector

The Graph Projector creates a release-scoped FalkorDB graph named from the
release identifier, such as `vbpl_<release_id>`. It reads canonical data and the
candidate release manifest after release validation but before release
promotion.

The projector:

- writes deterministic nodes and edges;
- records `release_id` and `corpus_revision` as graph metadata;
- uses idempotent upserts keyed by stable canonical identifiers;
- validates referential integrity, temporal ranges, evidence fields, and
  expected node and edge counts;
- never mutates an older release-scoped graph;
- supports full rebuild from PostgreSQL and retained evidence.

FalkorDB is therefore disposable and rebuildable. It is not a backup of legal
evidence or the system of record.

### 5.3 FalkorDB

FalkorDB stores relationship topology and the metadata required for bounded
filtering. It does not store the full legal corpus.

Production queries use only parameterized, approved templates. Each template
defines:

- allowed start-node labels;
- allowed relationship types and directions;
- maximum legal hops;
- maximum result and path counts;
- temporal and status predicates;
- query timeout and completeness behavior.

The service account has no authority to write through the retrieval interface.
Graph administration and projection use a separate credential and private
network path.

### 5.4 Graph Retrieval Service

The Graph Retrieval Service is the only runtime component allowed to query
FalkorDB. It exposes typed operations rather than raw Cypher:

- expand seed provisions and instruments;
- assemble an authority bundle;
- follow amendment, supplement, repeal, replacement, legal-basis, citation,
  and implementation-guidance paths;
- resolve the graph view at a supplied `as_of` time;
- return canonical endpoint identifiers, legal paths, and evidence references.

It also maps canonical graph endpoints to stable Onyx projection document IDs.
Provision endpoints map deterministically through the existing projection-ID
functions. Instrument-only endpoints are mapped through the active release
manifest to a bounded set of candidate projection IDs for query-scoped
reranking.

### 5.5 Graph-augmented Internal Search

Onyx CE native Chat already invokes the built-in `internal_search` action. The
project-owned overlay supplies `VBPLGraphAugmentedSearchTool`, a VBPL-specific
implementation selected for agents scoped to `VBPL-current` or `VBPL-history`.
The backend always enables and forces this implementation for those agents,
regardless of client-side action toggles. Users cannot bypass graph retrieval
by changing a Chat UI selection.

This implementation preserves:

- tool name `internal_search`;
- `SearchDocsResponse`;
- Onyx citation processing and Chat UI;
- `vbpl_export` source type and Document Set restrictions;
- user access checks and index filters.

Non-VBPL agents continue using the stock Search Tool.

The overlay must not rely on the public Search UI or on two LLM-selected tool
calls. The pinned CE source supports repeated search calls, but
`forced_tool_id` forces only the first tool cycle and the public search filters
do not expose stable document-ID filtering. Deterministic graph augmentation
therefore occurs inside one backend-controlled `internal_search` invocation.

## 6. Graph model

### 6.1 Nodes

#### `Instrument`

Stable identity for an official VBPL instrument.

Required properties:

- `official_source_id`
- `document_number`
- `normative_form`
- `issuer`
- `official_url`

#### `InstrumentVersion`

Immutable legal version of an instrument.

Required properties:

- `version_id`
- `status`
- `status_verified_at`
- `effective_from`
- `effective_to`
- `authority_order`
- `jurisdiction`
- `corpus_revision`
- `current_eligible`

#### `Provision`

Version-specific article, clause, point, or other canonical legal node.

Required properties:

- `node_id`
- `materialized_path`
- `node_type`
- `display_label`
- `content_hash`
- `parse_status`
- applicability fields needed by approved traversal templates

### 6.2 Structural edges

- `Instrument -[:HAS_VERSION]-> InstrumentVersion`
- `InstrumentVersion -[:CONTAINS]-> Provision`

Structural edges do not consume the legal-hop budget.

### 6.3 Legal edges

Allowed legal relationship types are:

- `LEGAL_BASIS`
- `AMENDS`
- `SUPPLEMENTS`
- `REPEALS`
- `REPLACES`
- `GUIDES_IMPLEMENTATION`
- `CITES`

An edge may connect two instruments, two provisions, or mixed-precision
endpoints when official evidence identifies only one endpoint at provision
precision. The projector must not manufacture provision precision.

Every legal edge contains:

- `logical_edge_id`
- `relation_type`
- `evidence_hash`
- `evidence_kind`
- `evidence_reference`
- `is_verified_effect`
- `resolution_state`
- `searchable`
- `effective_from`
- `effective_to`
- `corpus_revision`

Only `searchable=true` edges with an accepted resolution state and official
evidence participate in retrieval. Unknown, unmapped, heuristic, or
text-candidate relationships remain outside the serving graph.

A traversable `CITES` edge establishes only an evidence-backed citation
relationship. It does not become a verified amendment, repeal, replacement, or
other legal effect, and the reranker must not treat it as one.

## 7. Runtime retrieval flow

### 7.1 Query context

The backend determines:

- current-law mode when the user supplies no historical time;
- historical mode and `as_of` for an explicit point-in-time question;
- exact instrument numbers and provision coordinates through deterministic
  parsing.

Exact parsing creates seeds only. It does not infer legal relationships.

### 7.2 Retrieval phase 1

The existing Onyx search pipeline runs inside `internal_search` with:

- `source_type=["vbpl_export"]`;
- the Current Document Set for current-law mode;
- the Current and History Document Sets for historical mode;
- the normal user access and corpus filters.

It returns ranked seed chunks retaining stable `document_id`, metadata, and
provision coordinates. Deterministically parsed identifiers supplement, but do
not replace, these search seeds.

### 7.3 Mandatory graph expansion

The overlay sends the following typed request to the Graph Retrieval Service:

```json
{
  "query_id": "opaque-request-id",
  "release_id": "release-id",
  "corpus_revision": "revision",
  "mode": "current-or-history",
  "as_of": "ISO-8601-or-null",
  "seed_document_ids": ["vbpl:..."],
  "seed_instrument_ids": ["178717"],
  "seed_provision_ids": ["node:..."],
  "allowed_relation_types": ["AMENDS", "LEGAL_BASIS"],
  "max_legal_hops": 2,
  "max_candidates": 30
}
```

The service checks release and graph metadata before traversal. It returns:

```json
{
  "release_id": "release-id",
  "corpus_revision": "revision",
  "complete": true,
  "canonical_candidates": [],
  "exact_document_ids": [],
  "scoped_candidate_document_ids": [],
  "relation_paths": [],
  "evidence_references": [],
  "excluded_candidates": []
}
```

`complete=false` is a blocking result, not a partial success.

### 7.4 Retrieval phase 2

The overlay uses Onyx's internal DocumentIndex interfaces:

- `id_based_retrieval()` for provision-precise target documents;
- a bounded hybrid search restricted to graph-approved stable document IDs for
  instrument-only targets.

This phase retains the original `vbpl_export`, Document Set, revision, and user
access restrictions. Graph IDs never bypass Onyx access control.

### 7.5 Merge, rerank, and answer gate

The overlay merges:

- phase-one semantic and keyword results;
- exact parsed matches;
- graph-expanded phase-two results.

It deduplicates by document and chunk identity, then reranks for query
relevance, temporal applicability, provision precision, and authority-bundle
coverage. A global numeric authority boost must not independently decide which
legal provision controls.

The normal Onyx citation pipeline receives one unified `SearchDocsResponse`.
The LLM may generate an answer only after the backend records successful
Internal Search and graph evidence.

A valid empty graph expansion is distinct from an operational failure. When no
verified seed or legal basis is found, the agent returns the repository's
required verified-basis refusal. A graph timeout, stale graph, or incomplete
result raises a non-recoverable backend error that bypasses ordinary LLM tool
retry and aborts the request before answer generation. No partial answer tokens
may be emitted first.

## 8. Release readiness

The daily publication sequence is:

1. Build and validate the candidate release.
2. Build and validate its immutable FalkorDB graph.
3. Promote `active-release.json`.
4. Synchronize Current and History connectors into Onyx.
5. Reconcile indexed document counts and revision metadata with each release
   manifest.
6. Run Schema-v2 verification and graph-integrity checks.
7. Atomically update `data/exports/retrieval-ready.json`.

`retrieval-ready.json` contains:

- `release_id`
- `corpus_revision`
- `graph_name`
- manifest checksums
- Onyx reconciliation result
- graph validation result
- `verified_at`

Every query requires the active release, retrieval-ready pointer, graph
metadata, and retrieved Onyx document metadata to agree. A mismatch fails
closed.

During connector synchronization the MVP does not serve a potentially mixed
index. Blue/green indexing is deferred. If candidate indexing or verification
fails, readiness is not advanced. Recovery preserves PostgreSQL volumes,
evidence, releases, and release-scoped graphs.

## 9. Failure handling

| Condition | Required behavior |
| --- | --- |
| No seed or no verified relation | Valid empty result; return verified-basis refusal when no corpus support exists |
| Graph unavailable or timed out | Abort the chat request before answer generation |
| Graph revision differs from active release | Abort and report stale graph |
| Traversal reaches a configured limit | Return `complete=false`; fail closed |
| Graph target is absent from Onyx | Record integrity failure; fail closed |
| Current-law status evidence is stale or unknown | Refuse a current-law conclusion |
| Historical evidence does not cover `as_of` | Refuse the point-in-time conclusion |
| Unverified or unknown relation | Exclude it from serving traversal |
| Connector sync or reconciliation fails | Do not advance retrieval readiness |

Failures are observable and retryable but never silently converted to
LLM-only answers.

## 10. Audit and security

Each query records:

- opaque query or trace identifier;
- release and graph revisions;
- current/history mode and `as_of`;
- seed identifiers;
- approved relation paths and evidence hashes;
- returned and excluded candidates with reasons;
- completeness and readiness results;
- Onyx tool-call and source evidence.

Sensitive query text is stored only when approved by operational policy.
Otherwise the audit stores a query hash and technical telemetry.

FalkorDB is private to the application network. Runtime access is read-only.
Cypher is parameterized and selected from an allowlist. Traversal, result,
memory, and time limits are configured even though MVP latency is not an
acceptance gate.

## 11. Verification and acceptance

### 11.1 Unit and contract tests

- Project only verified searchable relations.
- Preserve instrument, version, and provision endpoint precision.
- Select correct current and historical versions for `as_of`.
- Produce deterministic, idempotent graph projections.
- Reject dangling identifiers, duplicate logical edges, invalid temporal
  ranges, and missing evidence.
- Map canonical graph targets to stable Onyx projection IDs.
- Preserve source, Document Set, revision, and access filters in both retrieval
  phases.

### 11.2 FalkorDB integration tests

- Exercise approved direction and relationship templates against a real test
  graph.
- Confirm structural edges do not consume legal hops.
- Confirm temporal filters exclude invalid versions and edges.
- Confirm query limit, timeout, and revision failures produce incomplete or
  blocking responses.

### 11.3 Onyx CE overlay tests

- Every VBPL Legal Agent Internal Search invokes graph expansion.
- Phase one supplies stable seeds.
- Phase two retrieves only graph-approved candidates.
- Search documents are deduplicated while citations remain valid.
- A valid zero-edge graph result may continue.
- Graph failure, stale graph, missing target, or incomplete traversal prevents
  answer generation.
- Non-VBPL agents retain stock Search Tool behavior.

### 11.4 Release tests

- A graph is ready before release promotion.
- Retrieval readiness does not advance before successful Onyx reconciliation.
- Partial sync, wrong revision, or missing documents blocks readiness.
- Failed candidates do not delete retained evidence, releases, or database
  volumes.

### 11.5 Legal-search acceptance corpus

Cases cover:

- instrument-to-instrument amendment;
- provision-to-provision amendment;
- implementation guidance;
- legal-basis chains;
- current-law questions;
- point-in-time questions;
- no verified relation;
- stale status and conflicting evidence;
- graph outage and revision mismatch.

Mandatory gates:

- graph invocation coverage: 100%;
- Internal Search evidence coverage: 100%;
- evidence-backed graph-path coverage: 100%;
- current-law safety: 100%;
- no result outside `vbpl_export` or the permitted Document Sets;
- controlling-provision recall@10 is not below baseline;
- authority-bundle completeness@10 improves on relationship cases;
- final context size is no more than 125% of baseline.

Latency is measured by phase and reported, but it does not block MVP
acceptance.

## 12. Required repository verification

The implementation plan must include:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

It must also include real FalkorDB integration tests, Schema-v2 OpenSearch
verification, release/readiness reconciliation, and live Onyx Chat acceptance
that proves both `internal_search` and graph execution evidence.
