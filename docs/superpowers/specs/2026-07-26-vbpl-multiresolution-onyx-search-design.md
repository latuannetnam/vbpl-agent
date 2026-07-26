# VBPL Multi-Resolution Stock-Onyx Search Design

**Status:** Approved design
**Date:** 2026-07-26
**Scope:** Clean-slate VBPL data pipeline, canonical PostgreSQL store,
multi-resolution release projection, persistent custom connector overlay, and
stock Onyx Internal Search.

## Purpose

Rebuild the project around a canonical representation of Vietnamese legal
instruments that preserves both:

1. the internal text hierarchy `Part -> Chapter -> Article -> Clause -> Point`;
2. the authority, applicability, version, status, and verified legal
   relationships between instruments.

The searchable projection must support exact legal coordinates, semantic topic
search, full-article context, historical research, evidence audit, and staged
authority-bundle retrieval. All runtime retrieval must use Onyx
`internal_search`.

## Approved constraints and decisions

- Keep stock Onyx core. Do not maintain a retrieval, chunking, embedding,
  ranking, or reranking fork.
- A project overlay may add the `vbpl_export` connector, source registration,
  connector configuration, UI registration, and Compose wiring.
- All runtime legal retrieval uses `internal_search`. Web Search, MCP, code
  execution, and model background knowledge are not legal authorities.
- Docker Compose is the canonical deployment and operational path.
- Replace SQLite as the canonical store with a project-owned PostgreSQL
  database. Do not use the Onyx relational database for canonical VBPL data.
- Use a clean-slate rebuild. Do not migrate legacy SQLite rows or legacy Onyx
  projection documents into the new schema.
- Keep the existing Onyx index available while the new canonical corpus and
  release are built. Delete the scoped old VBPL connector/index only after the
  new full candidate release passes pre-index validation.
- Use multi-resolution Onyx documents: Article Context, Atomic Provision, and
  Legal Relation documents.
- Use three logical corpus views and connector configurations: Current,
  History, and Evidence.
- The three connectors share the active physical Onyx search index but are
  separated by document sets and globally unique document IDs.
- Keep legal status, applicability, authority classification, relationship
  validation, and release promotion outside Onyx.
- Do not globally boost higher-authority instruments. Retrieve and reason over
  an authority bundle after applicability gates.

## Non-goals

- Changing Onyx core or adding an external runtime search service.
- Using an LLM-generated knowledge graph as legal authority.
- Treating a citation as proof of amendment, repeal, replacement, suspension,
  or continued effect.
- Treating document type alone as an authority rank when the issuer is
  material.
- Making raw HTML or API payloads the ordinary current-law search corpus.
- Preserving backward compatibility with the legacy one-document-per-instrument
  projection.
- Migrating the legacy SQLite state or legacy Onyx document IDs.

## Verified Onyx constraints

The design relies on behavior verified in the pinned Onyx checkout
`e31b356caed3c4767a66c5f790d497b28784fd74`.

### Document and section model

Onyx `DocumentBase` supports document-level metadata whose values are strings
or lists of strings. `TextSection` carries text, link, and an optional heading;
it does not carry arbitrary section metadata.

The stock text chunker greedily accumulates consecutive text sections while
they fit inside the content token budget. It does not preserve a searchable
legal section identifier, and an ordinary heading does not create a hard chunk
boundary. Oversized sections are sentence-split.

The normal chunk budget is 512 embedding-tokenizer tokens. Title, semantic
metadata, and optional contextual-RAG reservations reduce the content budget.
Semantic metadata is omitted from the embedding input when it consumes at least
25 percent of the chunk budget.

The native context size of an embedding model does not automatically increase
the normal Onyx chunk size. The embedding tokenizer can still change how much
Vietnamese text fits in 512 tokens. Embedding dimension affects vector storage,
memory, latency, and retrieval quality; it does not participate in section
packing or chunk-boundary decisions.

Multipass indexing may add large chunks made from groups of four normal chunks
for model/provider combinations that stock Onyx explicitly supports. These are
additional chunks, not replacements for normal chunks.

### Index and document-set model

Connectors do not receive independent physical search indexes. The active
index is selected from Onyx search settings. Connector documents share that
index for a tenant/search setting, except for a temporary secondary index
during a supported index or embedding-model switchover.

Each indexed chunk has a multi-valued `document_sets` keyword field.
`internal_search` filters that field by the document set names attached to the
Agent. Multiple document sets use any-of matching.

Onyx `Document.id` is globally unique. A document may be associated with more
than one connector/credential pair, but two connectors must not emit different
content under the same ID.

These constraints require document-level legal atoms, global projection
namespaces, and document-set isolation rather than reliance on section
headings, per-section metadata, or separate physical indexes.

## System architecture

```text
Official VBPL API and canonical pages
  -> content-addressed raw evidence
  -> canonical PostgreSQL store
       -> instrument versions
       -> legal-node tree
       -> authority regimes and classifications
       -> applicability envelopes and status observations
       -> verified legal relationship graph
  -> validated multi-view candidate projection
       -> Current: article + atomic + relation
       -> History: versioned article + atomic + relation
       -> Evidence: compact evidence records
  -> immutable checksummed JSONL shards
  -> atomic active-release pointer and delta manifests
  -> three configurations of the VBPL Export Connector overlay
  -> one stock Onyx search index with three document-set scopes
  -> Current, Historical, and Evidence Audit Agents
  -> forced internal_search and source-grounded answers
```

Each bounded unit has one responsibility:

- **Acquisition** obtains and retains official evidence.
- **Canonical store** represents observed legal facts and versions.
- **Structure parser** builds the internal legal-node tree.
- **Authority classifier** assigns a versioned statutory authority group.
- **Applicability engine** records status, time, geography, subject, and
  provision-level limitations.
- **Relationship resolver** promotes only evidence-backed legal-effect edges.
- **Projector** creates search documents without legal inference.
- **Release manager** validates and promotes immutable artifacts.
- **Connector overlay** streams a selected corpus view into stock Onyx.
- **Agent instruction** performs staged retrieval and conservative synthesis.

## Canonical PostgreSQL model

The project owns a PostgreSQL database separate from all Onyx databases.
Canonical tables are normalized around stable instruments, observed versions,
and an ordered legal-node tree.

### Instruments and versions

`instruments` contains the stable official identity:

- `instrument_id`, formatted as `vbpl:<official-id>`;
- official source ID and canonical URL;
- official number and title;
- normalized and raw form;
- normalized and raw issuer;
- jurisdiction identity;
- first and latest observation timestamps.

`instrument_versions` contains immutable observed content states:

- deterministic `version_id`;
- parent `instrument_id`;
- detail payload hash and normalized content hash;
- source observation and verification timestamps;
- promulgation and effective dates;
- raw and normalized legal status;
- parse and validation state;
- corpus revision.

A changed official detail payload creates a new immutable version. It does not
overwrite historical content.

### Ordered legal-node tree

`legal_nodes` represents all structural levels:

- `node_id`;
- `version_id`;
- `parent_node_id`;
- `node_type`: `part`, `chapter`, `article`, `clause`, or `point`;
- display label, normalized coordinate, and heading;
- sibling ordinal and materialized path;
- exact text and optional lead-in text;
- source offsets or source anchors;
- content hash;
- `parse_status`;
- citation structure.

Example materialized path:

```text
phan-02/chuong-03/dieu-12/khoan-02/diem-a
```

The parser first consumes official structure from retained HTML/API evidence.
Regex parsing is a marked fallback. The allowed parse states are
`verified_structured`, `verified_text`, `heuristic`, and `unparsed`.
Heuristic or unparsed content may remain discoverable but cannot support an
exact provision-level current-law conclusion.

Tree invariants prohibit cycles, orphan nodes, duplicate sibling coordinates,
unstable ordering, and text that cannot be traced to evidence.

### Authority regimes

Authority hierarchy is separate from the internal text tree.

`authority_regimes` records versioned legal regimes with effective intervals
and checked-in classification versions. `authority_classifications` records:

- `hierarchy_regime`;
- zero-padded `article4_order`;
- `authority_group`;
- `normative_form`;
- `issuer_type`;
- `classification_status`;
- `classification_source`;
- `classification_version`;
- `is_normative`.

For the regime effective from 2025-07-01, the 15 statutory groups and the
legacy district transition follow the approved hierarchy-aware design. Forms
such as resolution, decision, and circular require issuer-sensitive
classification.

An unmodeled historical period remains explicitly unclassified. The 2025
regime is never applied retroactively. Unknown classification is searchable but
cannot resolve an authority conflict.

### Applicability and status

`status_observations` retains every official observation and evidence hash.
`applicability_envelopes` supports both instrument-level defaults and
provision-level overrides:

- normalized and raw legal status;
- verified timestamp and evidence source;
- effective start and end;
- territorial level, code, and name;
- subject or regulated-scope tokens;
- transition end;
- partial-effect status and supporting provision evidence.

Current-law eligibility requires fresh official evidence, a qualifying status,
and provision-level evidence when an instrument is only partially effective.
Stale, missing, failed, conflicting, suspended, expired, not-yet-effective, or
unknown evidence cannot support a current-law conclusion.

### Verified relationships

`legal_relations` stores:

- source instrument, version, and provision;
- target instrument, version, and provision when resolved;
- relation type;
- direction;
- effective interval;
- evidence kind and evidence hash;
- source quote, payload pointer, and source offset;
- confidence and resolution state;
- corpus revision.

Supported types include ordinary citation, legal basis, detail, implementation,
delegation, amendment, supplementation, replacement, repeal, suspension, and
continued effect.

Only explicit official evidence promotes a legal-effect relationship.
Heuristic candidates remain unresolved. Duplicate edges are collapsed,
heuristic self-references are excluded, and unresolved targets remain
unresolved.

### Evidence storage

Raw evidence is stored outside PostgreSQL in a content-addressed Docker volume:

```text
/app/data/evidence/sha256/<prefix>/<sha256>
```

The database stores the hash, media type, official URL, acquisition timestamp,
endpoint, corpus revision, and the records that depend on the evidence.

## Stable identities

Identity is separated into three layers:

```text
Canonical instrument:
vbpl:178717

Logical provision:
vbpl:178717#dieu-12/khoan-2/diem-a

Onyx projection document:
vbpl:178717:current:article:<logical-path-hash>
vbpl:178717:current:atomic:<logical-path-hash>
vbpl:178717:current:relation:<logical-edge-hash>
vbpl:178717:history:<version-hash>:article:<logical-path-hash>
vbpl:178717:history:<version-hash>:atomic:<logical-path-hash>
vbpl:178717:history:<version-hash>:relation:<logical-edge-hash>
vbpl:178717:evidence:<evidence-kind>:<evidence-hash>
```

Current IDs are stable for an instrument and logical path so a changed current
projection updates the same Onyx document. `logical-path-hash` is derived from
the instrument identity, normalized node type, and materialized path; it never
includes mutable text. `logical-edge-hash` is derived from the relation type and
logical source/target coordinates; evidence changes update the same current
relationship document. History IDs additionally include the immutable version.
A removed or renumbered logical path receives a tombstone; content is never
silently reassigned from one legal coordinate to another.

All three connector views use disjoint namespaces. Every projection retains
`instrument_id`, `logical_provision_id` when applicable, `corpus_view`, and
`corpus_revision` as metadata.

## Multi-resolution projection

Every projection document emits exactly one `TextSection`. This makes the Onyx
Document boundary the legal retrieval boundary and prevents cross-provision or
cross-relation section merging.

### Article Context Document

An Article Context Document contains:

- one compact instrument/authority/applicability header;
- Part and Chapter breadcrumbs;
- the Article number, heading, and complete ordered Article text;
- all Clause and Point labels in their official order;
- the official document URL.

It has `projection_kind=article` and a logical path ending at the Article. Onyx
may split an oversized Article into multiple chunks, but no chunk can contain
text from another Article.

Part and Chapter headings do not receive standalone documents unless they carry
independent substantive text. They remain canonical nodes and breadcrumbs.

### Atomic Provision Document

Atomic documents are leaf-only:

- Point when a Clause contains Points;
- Clause when it contains no Points;
- Article when it contains no Clauses.

An atomic document includes:

- compact instrument, authority, status, and applicability context;
- the full legal breadcrumb;
- Article heading and a material Article lead-in;
- Clause lead-in for a Point;
- the exact leaf text;
- relevant verified relation tokens;
- the official document URL.

It does not repeat sibling provisions or the entire Article.
`projection_kind=atomic` and document-level metadata therefore identify one
exact legal coordinate.

### Legal Relation Document

A Legal Relation Document represents one verified relationship edge. It
contains:

- normalized relation type;
- source and target instrument IDs and numbers;
- source and target provision coordinates;
- effective interval and current/history relevance;
- compact evidence kind;
- searchable forward and reverse relation tokens.

Current includes only relationships relevant to a current-law authority bundle.
History retains versioned relationships. Evidence retains the proof and
resolution record. Ordinary citation documents never masquerade as
legal-effect documents.

### Evidence Document

Evidence projection is compact and audit-oriented. It contains status
observations, relationship proof, classification source, exclusion reasons,
official URLs, timestamps, and hashes. Full raw payloads remain in the evidence
volume.

Evidence documents are not ordinary legal authority and are not attached to
the Current Agent.

### Compact searchable context

The minimum legal context is placed inside section text, not only in Onyx
metadata, because oversized semantic metadata may be omitted from the embedding
input.

The compact header contains:

- instrument title and number;
- normative form and issuer;
- authority regime and group;
- legal coordinate;
- status and verification time;
- effective interval;
- jurisdiction;
- relevant verified relation tokens.

Metadata uses short scalar strings and short lists. Dates use UTC ISO 8601.
Authority order is zero-padded for stable lexical representation, but it is not
a global search boost.

### Duplicate control

Article and Atomic projections intentionally overlap. The following rules limit
retrieval crowding:

- create Atomic documents only for leaves;
- place one compact header on an Article, not one per descendant;
- inherit only material ancestor lead-ins into Atomic documents;
- never copy sibling provisions into an Atomic document;
- group answer evidence by `instrument_id` and `logical_provision_id`;
- prefer Atomic for exact citation and Article for surrounding context;
- allow at most two top-10 hits with the same logical provision ID.

## Connector, document-set, and Agent topology

One overlay implementation supports a required `corpus_view` connector
configuration. Three connector/credential-pair configurations use the same
source type `vbpl_export`.

| Connector configuration | Document set | Projection |
| --- | --- | --- |
| `VBPL Current` | `VBPL-current` | current Article, Atomic, Relation |
| `VBPL History` | `VBPL-history` | versioned Article, Atomic, Relation |
| `VBPL Evidence` | `VBPL-evidence` | compact evidence records |

All three feed the same active physical search index. Document-set membership
is the logical isolation and search filter. Source-type filtering alone cannot
separate the views because all use `vbpl_export`.

### Agent profiles

| Agent | Knowledge scope | Use |
| --- | --- | --- |
| `VBPL Legal Current` | `VBPL-current` | present-law research |
| `VBPL Legal Historical` | `VBPL-current`, `VBPL-history` | point-in-time and version comparison |
| `VBPL Evidence Audit` | `VBPL-evidence`, with current/history only when explicitly configured | provenance and data-decision audit |

Every Agent:

- forces `internal_search`;
- disables Web Search, MCP, code execution, and external write actions;
- is scoped to explicit VBPL document sets;
- treats retrieved official evidence as the only legal authority;
- records source documents and tool-call evidence for acceptance.

The ordinary Current Agent never includes History or Evidence. This hard
document-set boundary is preferred over prompt-only exclusion.

## Search and authority-bundle workflow

The Agent:

1. establishes subject, conduct, requested consequence, material time,
   jurisdiction, and current-versus-historical intent;
2. asks one focused question only if a missing coordinate could materially
   alter the result;
3. uses exact number and provision coordinates when supplied;
4. otherwise searches by issue terms without guessing an Article number;
5. retrieves the controlling provision after evidence, status, temporal,
   geographic, and subject-scope gates;
6. performs bounded follow-up `internal_search` calls using instrument IDs,
   legal coordinates, and verified relation tokens;
7. collects implementing, amending, replacing, suspending, continuing, and
   applicable local instruments;
8. retrieves Article context and Atomic citation evidence;
9. applies hierarchy only after confirming that candidates regulate the same
   issue within the same applicable scope;
10. retains necessary subordinate implementation details;
11. applies later-in-time priority only under verified same-authority
    conditions;
12. preserves unresolved conflicts instead of inventing a winner.

The answer identifies the controlling provision, implementing detail,
legal-effect qualifications, applicable local rules, material exclusions, and
unresolved conflicts. Each substantive conclusion cites the instrument,
provision, issuer, effective date, status, verification timestamp, and official
VBPL URL.

When verified evidence is insufficient, the required refusal remains:

```text
Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.
```

## Embedding, chunking, and search configuration

The design preserves the stock 512-token normal chunk budget. One-section
projection documents make legal boundaries independent of how a future
embedding tokenizer counts Vietnamese text.

Initial runtime configuration:

```text
HYBRID_ALPHA=0.5
DOC_TIME_DECAY=0
MAX_CHUNKS_FED_TO_CHAT=25
MAX_LLM_CYCLES=8
```

Recency decay is disabled because an older instrument may remain controlling
law. Currentness is enforced through official status and applicability, not
document age.

Hybrid alpha is evaluated at `0.3`, `0.5`, and `0.7` against the same corpus,
query set, reranker, and model configuration. The passing configuration with
the best legal retrieval metrics is selected. Embedding candidates must:

- be supported by stock Onyx;
- support at least the 512-token normal chunk input;
- provide strong Vietnamese multilingual retrieval;
- fit the target Docker host with required capacity headroom.

Dimension is selected by measured retrieval quality and resource cost; a
larger dimension is not assumed to be better. Changing embedding model or final
dimension requires a full Onyx re-index.

Multipass large chunks may be enabled only when stock Onyx declares the selected
model/provider compatible. They primarily benefit oversized Article Context
documents. Atomic and Relation documents ordinarily remain one normal chunk.

No authority-based Onyx `Document.boost` is used.

## Docker-first deployment

Two Compose projects preserve the boundary between canonical data and stock
Onyx.

### VBPL data stack

`docker-compose.vbpl.yml` owns:

- `vbpl-db`: PostgreSQL with no public port by default;
- `vbpl-migrate`: one-shot schema bootstrap and upgrade;
- `vbpl-pipeline`: one-shot crawl/build/release/index-trigger worker;
- `vbpl-scheduler`: optional always-on daily scheduler;
- `vbpl-backup`: manual backup profile;
- `vbpl-test`: isolated integration-test profile.

The pipeline and scheduler use a PostgreSQL advisory lock to prevent overlapping
runs.

Named volumes:

- `vbpl-postgres-data`;
- `vbpl-evidence-data`;
- `vbpl-export-data`;
- `vbpl-backup-data`.

### Onyx stack

The pinned project-owned Onyx Compose stack remains upstream-owned. Overlay
Compose mounts `vbpl-export-data` read-only into the background worker and adds
the connector/UI integration. It does not expose PostgreSQL or canonical
evidence to Onyx.

Networks:

- `vbpl-data-internal` connects only the pipeline services and PostgreSQL;
- `vbpl-onyx-bridge` connects the pipeline to the Onyx API and the export
  consumer;
- the Onyx UI remains bound to loopback by default.

Secrets stay in untracked environment or Docker-secret inputs and are never
rendered into resolved Compose output, logs, releases, or commits.

## Release and incremental synchronization

Daily operation retains a complete official catalog scan because the official
catalog does not provide a dependable change/deletion cursor. Deterministic
catalog fingerprints identify new and changed instruments. Unchanged
instruments skip detail acquisition, normalization, projection, embedding, and
index updates.

A missing instrument becomes a tombstone only after two consecutive complete
scans. Partial or failed scans do not advance the complete-scan baseline and
never emit removals.

Each immutable release contains:

- release metadata and projection schema version;
- checksummed JSONL document shards per corpus view;
- active ID manifests per view for SlimConnector pruning;
- delta shards with upsert and tombstone IDs;
- evidence and canonical-source revision references;
- validation results.

Sharding avoids millions of small files. The connector streams records and does
not load the full release into memory.

Promotion atomically changes `active-release.json` only after schema, checksum,
coverage, freshness, authority, relationship, and ID-namespace validation.
Connector delivery is tracked separately from source promotion.

## Release readiness

Four release states are distinct:

```text
candidate_release
promoted_release
connector_applied_release
accepted_release
```

An Agent is ready only when the required connector views have applied the same
release and their direct Onyx acceptance suite passes.

| Agent | Readiness |
| --- | --- |
| Current | Current connector applied and Current acceptance passed |
| Historical | Current and History applied the same revision and historical acceptance passed |
| Evidence Audit | Evidence applied and evidence acceptance passed |

Changing the active source pointer does not claim that Onyx has finished
indexing.

## Clean-slate cutover

No legacy data migration is performed.

1. Capture the old connector, Agent, prompt, index, release, and query baseline.
2. Create new PostgreSQL and evidence/export volumes.
3. Run `vbpl-migrate` against the empty project database.
4. Full-crawl official VBPL sources.
5. Build the canonical tree, classifications, applicability, and verified
   relationships.
6. Generate and validate the full multi-view candidate release.
7. Estimate final documents, chunks, vector storage, and capacity headroom.
8. Keep the old index serving through steps 1-7.
9. Begin an announced downtime window.
10. Delete only the old scoped VBPL connector, document set, and indexed
    documents using supported Onyx administration paths.
11. Do not delete unrelated Onyx users, Agents, models, relational state, or
    volumes.
12. Create the three connector configurations and document sets.
13. Full-index all required views.
14. Configure the three Agent profiles.
15. Run direct `internal_search` acceptance.
16. Enable each Agent only after its readiness gate passes.

The initial build may delete legacy project pipeline data and the scoped VBPL
index under the user's explicit clean-slate authorization. Destructive commands
must still resolve and verify exact Docker volumes, connectors, document sets,
and paths before execution.

## Failure handling

| Condition | Required behavior |
| --- | --- |
| Incomplete catalog scan | No baseline advance and no tombstone |
| Detail fetch failure | Preserve retained evidence; block completeness |
| Heuristic or unparsed structure | Discovery/history only; no exact current-law citation |
| Unknown authority classification | Searchable as unknown; no hierarchy resolution |
| Missing, stale, failed, suspended, expired, or conflicting status | Exclude from Current |
| Partial effect without provision evidence | Exclude the unsupported provision from Current |
| Ambiguous relationship | Preserve unresolved evidence; do not create legal-effect traversal |
| Invalid tree, namespace, schema, checksum, or coverage | Block promotion |
| PostgreSQL or evidence-volume failure | Stop before projection promotion |
| Connector failure | Do not advance connector-applied state; retry pending delta |
| Acceptance failure | Do not advance accepted state or enable the affected Agent |

During ordinary daily operation, the last indexed corpus may remain available
while a delta retries. If its official status evidence exceeds the 24-hour
freshness window, the Current Agent must refuse current-law conclusions.

## Verification strategy

### Canonical model tests

- migrations bootstrap an empty database and are idempotent;
- instrument versions are immutable;
- trees contain no cycles, orphans, duplicate coordinates, or unstable order;
- source anchors and evidence hashes are valid;
- logical IDs remain deterministic;
- parser fallback cannot acquire verified status silently;
- authority classification covers checked-in regimes and issuer-sensitive
  forms;
- applicability handles partial effect, geography, and transitions.

### Relationship tests

- verified official edges;
- ordinary citations;
- unresolved and unmapped references;
- evidence hashes and offsets;
- duplicate and self-reference handling;
- forward and reverse relation tokens;
- effective intervals and history transitions.

### Projection and release tests

- disjoint Current, History, and Evidence ID namespaces;
- one logical provision per Atomic document;
- one Article per Article document;
- one verified edge per Relation document;
- compact header and metadata budgets;
- sharded streaming and bounded memory;
- full manifests, deltas, active IDs, and tombstones;
- checksum, schema, coverage, and atomic promotion;
- current-to-history transition;
- unsupported projection-version refusal.

### Connector and document-set tests

- the three `corpus_view` configurations read only their view;
- SlimConnector returns the correct active IDs per view;
- polling emits only unacknowledged deltas;
- a History tombstone cannot delete a Current document;
- all emitted IDs are globally unique;
- Current Agent cannot retrieve History or Evidence;
- Historical Agent retrieves only Current or History;
- Evidence Agent does not leak into the ordinary Current Agent.

### Docker integration tests

- PostgreSQL health and migration ordering;
- advisory-lock exclusion;
- restart and retry behavior;
- persistence of database, evidence, and export volumes;
- read-only export mount in the Onyx background worker;
- a small official-evidence fixture flows from acquisition through connector
  indexing;
- Compose test profile exits with the test service result.

### Direct Onyx acceptance

Completion requires the ordinary authenticated Onyx Chat/Internal Search path.
For every case, record:

- query and conversation;
- Agent and model;
- prompt hash;
- release and projection schema;
- connector and readiness states;
- tool calls and `search_docs`;
- retrieved document IDs, chunks, metadata, and document sets;
- answer, citations, timestamp, and findings.

Hard gates:

- zero unsafe current-law conclusions;
- zero History/Evidence leakage into Current;
- zero Web Search, MCP, or non-`vbpl_export` evidence;
- expected Atomic document in top 5 for exact-coordinate cases;
- controlling-provision recall@10 of at least 95 percent;
- authority-bundle completeness@10 of at least 90 percent;
- 100 percent correct outcomes for evidence-resolved conflicts;
- 100 percent unresolved labeling where evidence is insufficient;
- no more than two top-10 hits for one logical provision ID;
- complete provision, issuer, status, time, verification, and official-link
  citations.

The evaluation corpus covers exact coordinates, topic search, implementing
details, authority conflict, same-authority later instruments, partial effect,
geographic mismatch, district transition, historical dates, amendments,
replacement, repeal, continuation, ordinary citations, follow-up context, and
evidence audit.

### Capacity gates

The previous 1.25-times chunk-count ceiling is removed because
multi-resolution projection intentionally increases documents and chunks.

Before cutover:

- estimate document, chunk, and raw-vector counts from the full candidate;
- leave at least 30 percent free OpenSearch disk after indexing;
- complete indexing without OOM or an unbounded retry loop;
- achieve warm `internal_search` p95 at or below 10 seconds over 100 acceptance
  queries on the target Docker host;
- compare embedding candidates with the same release, queries, reranker, and
  search settings;
- record total index time and peak host/container memory.

Repository verification remains:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Documentation-contract tests and direct Onyx acceptance are separate mandatory
gates.

## Documentation impact

Implementation must update the current documentation that owns changed
behavior:

- `AGENTS.md`;
- `README.md`;
- `docs/architecture.md`;
- `docs/legal-data-policy.md`;
- `docs/development-workflow.md`;
- `docs/operations.md`;
- `docs/onyx-agent-setup.md`;
- `docs/onyx-agent-instruction.md`;
- `tests/test_documentation.py`.

Current documents must not route coding agents to this historical design as an
implementation instruction after implementation is complete.

## Superseded design decisions

This design preserves the legal safety and authority-bundle rules of
`2026-07-24-vbpl-hierarchy-aware-onyx-search-design.md`, but supersedes these
projection and rollout decisions:

- one Onyx document per instrument;
- reliance on multiple legal `TextSection` boundaries inside one document;
- `vbpl:<official-id>` as the only Onyx document identity;
- schema-v1/schema-v2 compatibility as a clean-slate requirement;
- the 1.25-times chunk-count ceiling;
- blue/green migration of legacy pipeline data;
- one connector/document set/Agent for all legal research modes.

The canonical `vbpl:<official-id>` instrument identity remains mandatory as
metadata and as the parent of all derived projection identities.
