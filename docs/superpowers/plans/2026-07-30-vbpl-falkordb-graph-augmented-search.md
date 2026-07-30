# VBPL FalkorDB Graph-Augmented Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add release-scoped FalkorDB relationship expansion to every query made through the `VBPL Legal Current` and `VBPL Legal Historical` agents, while preserving the native Onyx CE Chat UI, one visible `internal_search` action, normal Onyx citations, and fail-closed legal-data guarantees.

**Architecture:** PostgreSQL remains canonical. A release projector writes an immutable FalkorDB graph and a typed graph service exposes parameterized read-only traversal templates. The project-owned Onyx CE overlay selects `VBPLGraphAugmentedSearchTool` for the two legal agents; its one `run()` invocation performs stock Onyx retrieval, mandatory graph expansion, exact-ID or ID-restricted phase-two retrieval, merge/rerank, and a unified `SearchDocsResponse`. A release is queryable only when `active-release.json`, `retrieval-ready.json`, FalkorDB metadata, and indexed Onyx metadata agree.

**Tech Stack:** Python 3.12, SQLAlchemy 2, Alembic, Pydantic 2, FastAPI/Uvicorn, `falkordb` 1.6.1, FalkorDB Server 4.20.1, HTTPX, PostgreSQL 17, Onyx CE pinned at `e31b356caed3c4767a66c5f790d497b28784fd74`, OpenSearch, Docker Compose, pytest, Ruff, mypy.

## Global Constraints

- Work only from the repository root `D:\latuan\Programming\vbpl-agent`.
- Preserve unrelated worktree changes. Never edit or commit generated files under `.onyx/onyx`; change only `infra/onyx/overlay/`, `infra/onyx/patches/`, bootstrap scripts, source, tests, and current documentation.
- Use the official VBPL API/canonical-page evidence and PostgreSQL as authority. FalkorDB and Onyx remain derived indexes.
- Only `searchable=true` relations with an accepted resolution state and official evidence enter the serving graph. `CITES` remains a citation relationship and never becomes a legal-effect edge.
- Use parameterized FalkorDB queries selected from an enum/allowlist. Never accept Cypher from an HTTP request or an LLM.
- Every VBPL legal query must invoke graph expansion. Graph unavailability, timeout, revision mismatch, incomplete traversal, missing Onyx target, or stale readiness aborts the request before answer generation.
- A valid complete expansion with zero legal edges is not an infrastructure error; it may continue with phase-one evidence and the established verified-basis refusal contract.
- Keep phase-two retrieval inside the original `vbpl_export`, Document Set, release revision, and user ACL scope.
- Standardize the three Document Set names as `VBPL-current`, `VBPL-history`, and `VBPL-evidence`.
- Do not add an MVP latency pass/fail gate. Record phase timings and report them in acceptance output.
- Use `falkordb/falkordb-server:v4.20.1`, not an unpinned image. Use `Graph.ro_query(query, params=parameters, timeout=timeout_ms)` at runtime and the write-capable `Graph.query` only in the projector.
- Each task below starts with a failing focused test, implements the smallest coherent behavior, runs focused verification, and creates one commit.

---

## Task 1: Lock dependencies, settings, and secret boundaries

**Files:**

- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/vbpl_kb/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `scripts/bootstrap-falkordb-acl.ps1`
- Test: `tests/test_graph_config.py`
- Test: `tests/test_deployment_files.py`

- [ ] **Step 1: Write failing settings and ACL-bootstrap tests**

Add assertions equivalent to:

```python
def test_graph_settings_are_bounded_and_secrets_are_not_serialized() -> None:
    settings = Settings(
        falkordb_host="falkordb",
        falkordb_admin_password="admin-secret",
        falkordb_reader_password="reader-secret",
        graph_service_token="service-secret",
    )
    assert settings.graph_max_legal_hops == 2
    assert settings.graph_max_candidates == 30
    assert settings.graph_query_timeout_ms == 2_000
    assert "admin-secret" not in repr(settings)
    assert "reader-secret" not in repr(settings)
    assert "service-secret" not in repr(settings)


def test_acl_bootstrap_never_contains_committed_passwords() -> None:
    script = Path("scripts/bootstrap-falkordb-acl.ps1").read_text(encoding="utf-8")
    assert "VBPL_KB_FALKORDB_ADMIN_PASSWORD" in script
    assert "VBPL_KB_FALKORDB_READER_PASSWORD" in script
    assert "user vbpl_reader" in script
    assert "+graph.ro_query" in script
    assert "-graph.query" in script
```

Also assert `.gitignore` contains `data/runtime-secrets/` and `.env.example` exposes blank secret variables rather than values.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_config.py tests/test_deployment_files.py -q
```

Expected: failures for missing settings, dependency, ACL bootstrap, and ignore rules.

- [ ] **Step 3: Add pinned dependencies and settings**

Add:

```toml
"falkordb==1.6.1",
"fastapi>=0.116,<1",
"uvicorn>=0.35,<1",
```

Add these `Settings` fields with the shown defaults/types:

```python
falkordb_host: str = "vbpl-falkordb"
falkordb_port: int = 6379
falkordb_admin_username: str = "vbpl_projector"
falkordb_admin_password: SecretStr = SecretStr("")
falkordb_reader_username: str = "vbpl_reader"
falkordb_reader_password: SecretStr = SecretStr("")
graph_service_url: str = "http://vbpl-graph-service:8091"
graph_service_token: SecretStr = SecretStr("")
graph_query_timeout_ms: int = 2_000
graph_http_timeout_seconds: float = 5.0
graph_max_legal_hops: int = 2
graph_max_candidates: int = 30
graph_max_paths: int = 100
graph_max_instrument_documents: int = 64
retrieval_ready_path: Path = Path("/app/data/exports/retrieval-ready.json")
onyx_current_connector_id: int | None = None
onyx_history_connector_id: int | None = None
onyx_evidence_connector_id: int | None = None
onyx_current_document_set: str = "VBPL-current"
onyx_history_document_set: str = "VBPL-history"
onyx_evidence_document_set: str = "VBPL-evidence"
opensearch_url: str = "https://opensearch:9200"
opensearch_username: str = "admin"
opensearch_password: SecretStr = SecretStr("")
opensearch_verify_tls: bool = False
opensearch_index_pattern: str = "danswer_chunk_*"
```

Use Pydantic validators to enforce:

```python
1 <= graph_max_legal_hops <= 3
1 <= graph_max_candidates <= 100
graph_max_paths >= graph_max_candidates
100 <= graph_query_timeout_ms <= 10_000
```

- [ ] **Step 4: Add the ACL bootstrap script**

The script must:

1. fail when either password is blank;
2. create only `data/runtime-secrets/falkordb-users.acl`;
3. write a projector user with `GRAPH.QUERY` and a reader user with `GRAPH.RO_QUERY` but not `GRAPH.QUERY`;
4. never print either password;
5. atomically replace the ACL file.

The generated semantic contract is:

```text
user default off
user vbpl_projector on >ADMIN_PASSWORD ~* +@connection +graph.query +graph.ro_query +graph.list +graph.explain
user vbpl_reader on >READER_PASSWORD ~* +@connection +graph.ro_query +graph.list -graph.query
```

- [ ] **Step 5: Refresh the lock and run focused verification**

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv lock
uv run pytest tests/test_graph_config.py tests/test_deployment_files.py -q
uv run ruff check src/vbpl_kb/config.py tests/test_graph_config.py
uv run mypy src/vbpl_kb/config.py
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml uv.lock src/vbpl_kb/config.py .env.example .gitignore scripts/bootstrap-falkordb-acl.ps1 tests/test_graph_config.py tests/test_deployment_files.py
git commit -m "build: add graph runtime configuration"
```

---

## Task 2: Complete the canonical relation serving contract and query audit schema

**Files:**

- Modify: `src/vbpl_kb/legal_semantics.py`
- Modify: `src/vbpl_kb/db_models.py`
- Modify: `src/vbpl_kb/repositories.py`
- Modify: `src/vbpl_kb/crawl.py`
- Create: `migrations/versions/20260730_02_graph_serving.py`
- Modify: `tests/integration/test_postgres_migrations.py`
- Create: `tests/test_graph_repository.py`
- Create: `tests/test_crawl_canonical.py`
- Modify: `tests/test_legal_semantics.py`

- [ ] **Step 1: Write failing tests for accepted and rejected relations**

Cover:

```python
official = resolve_relations(
    source_version_id="ver:1",
    source_node_id="node:1",
    raw_references=[{
    "target_vbpl_id": "200",
    "relation_type": "amends",
    "evidence_kind": "official_structured",
    "evidence_reference": "official:referenceType=10",
    "resolution_state": "verified",
    "searchable": True,
    "evidence_hash": "a" * 64,
    "corpus_revision": "rev-1",
    }],
)[0]
assert official.searchable is True
assert official.resolution_state == "verified"

candidate = resolve_relations(
    source_version_id="ver:1",
    source_node_id="node:1",
    raw_references=[{
    "target_vbpl_id": "200",
    "relation_type": "amends",
    "evidence_kind": "text_candidate",
    "resolution_state": "candidate",
    "searchable": False,
    "evidence_hash": "b" * 64,
    "corpus_revision": "rev-1",
    }],
)[0]
assert candidate.searchable is False
```

Repository tests must prove that `list_graph_relations()` returns the first and excludes the second, unknown relations, self-edges, missing evidence, and unresolved endpoints.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_legal_semantics.py tests/test_graph_repository.py -q
```

- [ ] **Step 3: Extend `LegalRelationDraft` and preserve source fields**

Add:

```python
evidence_kind: str
evidence_reference: str
resolution_state: str
searchable: bool
corpus_revision: str
```

`resolve_relations()` must copy these fields and independently enforce:

```python
accepted_resolution = resolution_state in {"verified", "resolved_citation"}
official_evidence = evidence_kind in {"official_structured", "official_page"}
searchable = bool(ref.get("searchable")) and accepted_resolution and official_evidence
is_verified_effect = searchable and relation_type != "cites"
```

Do not turn `cites` into a verified legal effect.

- [ ] **Step 4: Add database fields and `GraphQueryAudit`**

Add the five serving fields plus `corpus_revision` to `LegalRelation`. Add:

```python
class GraphQueryAudit(Base):
    __tablename__ = "graph_query_audits"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    release_id: Mapped[str] = mapped_column(String(256), nullable=False)
    corpus_revision: Mapped[str] = mapped_column(String(128), nullable=False)
    graph_name: Mapped[str] = mapped_column(String(256), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    seeds_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    paths_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    returned_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    excluded_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, nullable=False)
    complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    readiness_ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    timings_json: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Create an additive Alembic migration. Its downgrade may remove only the new table/columns; it must not call `Base.metadata.drop_all`.

- [ ] **Step 5: Add canonical graph snapshot and audit repository methods**

Introduce frozen data-transfer records in `repositories.py`; do not return
session-bound ORM objects:

```python
@dataclass(frozen=True)
class GraphInstrumentRecord:
    instrument_id: str
    official_source_id: str
    document_number: str
    normative_form: str
    issuer: str
    official_url: str

@dataclass(frozen=True)
class GraphVersionRecord:
    version_id: str
    instrument_id: str
    status: str
    status_verified_at: datetime
    effective_from: date | None
    effective_to: date | None
    authority_order: str
    jurisdiction: str
    corpus_revision: str
    current_eligible: bool

@dataclass(frozen=True)
class GraphProvisionRecord:
    node_id: str
    version_id: str
    materialized_path: str
    node_type: str
    display_label: str
    content_hash: str
    parse_status: str

@dataclass(frozen=True)
class GraphRelationRecord:
    logical_edge_id: str
    source_version_id: str
    source_node_id: str | None
    target_instrument_id: str | None
    target_version_id: str | None
    target_node_id: str | None
    relation_type: str
    evidence_hash: str
    evidence_kind: str
    evidence_reference: str
    is_verified_effect: bool
    resolution_state: str
    searchable: bool
    effective_from: date | None
    effective_to: date | None
    corpus_revision: str

@dataclass(frozen=True)
class GraphSnapshot:
    instruments: tuple[GraphInstrumentRecord, ...]
    versions: tuple[GraphVersionRecord, ...]
    provisions: tuple[GraphProvisionRecord, ...]
    relations: tuple[GraphRelationRecord, ...]
```

Add:

```python
CanonicalRepository.load_graph_snapshot(corpus_revision: str) -> GraphSnapshot
CanonicalRepository.persist_relations(relations: Sequence[LegalRelationDraft]) -> None
CanonicalRepository.load_projection_bundles(corpus_revision: str) -> tuple[CanonicalBundle, ...]
GraphAuditRepository.record(audit: GraphQueryAuditDraft) -> None
```

`load_graph_snapshot()` must join the latest authority classification, applicability envelope, and status observation needed by each version. It must reject duplicate logical edges and invalid temporal ranges rather than silently dropping them.

- [ ] **Step 6: Wire canonical bundle persistence into the crawler**

After retaining the official detail evidence, the crawler must call the
existing canonical functions in this order:

```python
draft = canonicalize_instrument(
    detail.raw_data,
    detail_payload_hash=hashlib.sha256(raw_bytes).hexdigest(),
    raw_evidence_hash=ev_detail.hash_sha256,
)
nodes = parse_legal_tree(detail.raw_data, raw_bytes)
authority = classify_authority(
    detail.raw_data.get("docType"),
    detail.raw_data.get("agency"),
)
status = StatusObservation(
    vbpl_id=draft.official_source_id,
    eff_status=draft.current_status or "",
    eff_from=str(draft.effective_date or ""),
    checked_at=ev_detail.acquired_at,
    content_hash=ev_detail.hash_sha256,
    run_id=revision,
    status_source="api",
)
applicability = build_applicability(detail.raw_data, status, authority, revision)
```

Normalize official structured references through `references.py`, resolve them
to `LegalRelationDraft`, and persist the instrument, version, ordered nodes,
authority, applicability, status observation, evidence dependencies, and
relations in one PostgreSQL transaction per instrument. A text-extracted
candidate is persisted for audit but remains `searchable=false`.

The focused crawler test must prove that a database write failure marks the
instrument failed and prevents a complete crawl; the crawler may not report
success after retaining evidence but failing canonical persistence.

- [ ] **Step 7: Run unit and migration tests**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_legal_semantics.py tests/test_graph_repository.py tests/test_crawl_canonical.py -q
$env:VBPL_KB_DATABASE_URL="postgresql+psycopg://vbpl:vbpl@localhost:5432/vbpl_test"
uv run pytest tests/integration/test_postgres_migrations.py -q -m postgres
```

Expected: unit tests pass; migration test creates 19 tables including `graph_query_audits` and is idempotent.

- [ ] **Step 8: Commit**

```powershell
git add src/vbpl_kb/legal_semantics.py src/vbpl_kb/db_models.py src/vbpl_kb/repositories.py src/vbpl_kb/crawl.py migrations/versions/20260730_02_graph_serving.py tests/test_legal_semantics.py tests/test_graph_repository.py tests/test_crawl_canonical.py tests/integration/test_postgres_migrations.py
git commit -m "feat: persist graph-serving legal relations"
```

---

## Task 3: Make projection IDs and release manifests graph-addressable

**Files:**

- Modify: `src/vbpl_kb/projection.py`
- Modify: `src/vbpl_kb/projection_ids.py`
- Modify: `src/vbpl_kb/models.py`
- Modify: `src/vbpl_kb/releases.py`
- Create: `src/vbpl_kb/release_catalog.py`
- Modify: `tests/test_projection.py`
- Modify: `tests/test_releases.py`
- Create: `tests/test_release_catalog.py`

- [ ] **Step 1: Write failing projection-anchor tests**

For each article/atomic document, require:

```python
assert doc.metadata["legal_node_id"].startswith("node:")
assert doc.metadata["logical_provision_id"] == "vbpl:12345:dieu-12"
assert doc.metadata["effective_from"] == "2026-01-01"
assert doc.metadata["effective_to"] == ""
assert doc.metadata["current_eligible"] == "true"
```

For each release document, require:

```python
assert doc["metadata"]["release_id"] == manifest.release_id
assert doc["metadata"]["corpus_revision"] == "rev-2026-07-30"
assert doc["metadata"]["projection_schema_version"] == "2"
```

Require the manifest to contain a SHA-256 and document count for every JSONL shard and `active-ids.jsonl`.

- [ ] **Step 2: Run focused tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_projection.py tests/test_releases.py tests/test_release_catalog.py -q
```

- [ ] **Step 3: Add deterministic legal-node anchors**

Use the existing canonical function:

```python
node_id = compute_node_id(
    bundle.draft.version_id,
    node.node_type,
    node.materialized_path,
)
metadata["legal_node_id"] = node_id
```

Relation projection metadata must also expose `source_node_id`, `target_node_id`, `target_instrument_id`, and `logical_edge_id` when present.

- [ ] **Step 4: Stamp release metadata and strengthen the manifest**

`ReleaseBuilder.build_candidate()` must:

1. require explicit projected documents or a canonical snapshot provider;
2. stop rebranding/copying an older active release when input is absent;
3. stamp `release_id`, `corpus_revision`, and schema version into every document;
4. write per-shard count/SHA-256 metadata;
5. validate duplicate document IDs across all views.

Use atomic file replacement for the manifest and pointer files.

Add:

```python
ReleaseBuilder.build_from_repository(
    revision: str,
    bundles: Sequence[CanonicalBundle],
    now: datetime,
) -> ReleaseManifest
```

It must call the existing Current, History, and Evidence projectors and is the
only production release path used by `run-daily`.

- [ ] **Step 5: Implement the release document catalog**

Add:

```python
@dataclass(frozen=True)
class ReleaseDocumentRef:
    document_id: str
    corpus_view: Literal["current", "history", "evidence"]
    instrument_id: str
    version_id: str
    legal_node_id: str | None


class ReleaseDocumentCatalog:
    @classmethod
    def load(cls, release_dir: Path) -> "ReleaseDocumentCatalog":
        return cls(_read_release_refs(release_dir))

    def exact_for_node(
        self, node_id: str, mode: str, as_of: datetime | None
    ) -> tuple[str, ...]:
        return tuple(ref.document_id for ref in self._eligible(mode, as_of) if ref.legal_node_id == node_id)

    def bounded_for_instrument(
        self,
        instrument_id: str,
        mode: str,
        as_of: datetime | None,
        limit: int,
    ) -> tuple[str, ...]:
        matches = (
            ref.document_id
            for ref in self._eligible(mode, as_of)
            if ref.instrument_id == instrument_id
        )
        return tuple(islice(matches, limit))
```

Current mode may return only Current IDs. Historical mode may return History IDs valid for the selected version plus Current IDs only when their version covers `as_of`. Evidence IDs are never returned.

- [ ] **Step 6: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_projection.py tests/test_releases.py tests/test_release_catalog.py -q
uv run ruff check src/vbpl_kb/projection.py src/vbpl_kb/releases.py src/vbpl_kb/release_catalog.py
uv run mypy src/vbpl_kb/projection.py src/vbpl_kb/releases.py src/vbpl_kb/release_catalog.py
```

- [ ] **Step 7: Commit**

```powershell
git add src/vbpl_kb/projection.py src/vbpl_kb/projection_ids.py src/vbpl_kb/models.py src/vbpl_kb/releases.py src/vbpl_kb/release_catalog.py tests/test_projection.py tests/test_releases.py tests/test_release_catalog.py
git commit -m "feat: add graph anchors to releases"
```

---

## Task 4: Project immutable release-scoped FalkorDB graphs

**Files:**

- Create: `src/vbpl_kb/graph_models.py`
- Create: `src/vbpl_kb/falkordb_client.py`
- Create: `src/vbpl_kb/graph_projector.py`
- Create: `tests/test_graph_projector.py`
- Create: `tests/integration/test_falkordb_projector.py`

- [ ] **Step 1: Write failing deterministic projection tests**

Use a fake Falkor adapter to assert:

- the graph name is deterministic and safe;
- indexes are created for `Instrument.official_source_id`, `Instrument.document_number`, `InstrumentVersion.version_id`, and `Provision.node_id`;
- two projections of the same snapshot issue equivalent parameterized upserts;
- a text candidate, unknown relation, self-edge, missing-evidence edge, or unresolved target is never written;
- old release-scoped graphs are never deleted or mutated.

Expected graph-name behavior:

```python
assert graph_name_for_release("release-rev/2026:07:30") == (
    "vbpl_release_rev_2026_07_30_"
    + hashlib.sha256(b"release-rev/2026:07:30").hexdigest()[:12]
)
```

- [ ] **Step 2: Run unit tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_projector.py -q
```

- [ ] **Step 3: Define typed graph projection records**

Create frozen Pydantic models:

```python
class GraphMetadata(BaseModel):
    release_id: str
    corpus_revision: str
    manifest_sha256: str
    projected_at: datetime
    instrument_count: int
    version_count: int
    provision_count: int
    legal_edge_count: int


class GraphProjectionReport(BaseModel):
    graph_name: str
    metadata: GraphMetadata
    complete: bool
    errors: tuple[str, ...]
```

- [ ] **Step 4: Implement explicit Falkor adapters**

Define protocols:

```python
class WritableGraph(Protocol):
    def query(self, cypher: str, params: dict[str, object], timeout: int | None = None) -> Any:
        raise NotImplementedError


class ReadOnlyGraph(Protocol):
    def ro_query(self, cypher: str, params: dict[str, object], timeout: int) -> Any:
        raise NotImplementedError
```

`FalkorAdminClient` authenticates as `vbpl_projector`; `FalkorReadClient` authenticates as `vbpl_reader`. The runtime class must expose no `query()` method.

- [ ] **Step 5: Implement the projector with parameterized upserts**

Use fixed Cypher strings. Representative node upsert:

```python
UPSERT_INSTRUMENT = """
UNWIND $rows AS row
MERGE (i:Instrument {official_source_id: row.official_source_id})
SET i.document_number = row.document_number,
    i.normative_form = row.normative_form,
    i.issuer = row.issuer,
    i.official_url = row.official_url
"""
```

Create structural edges with `MERGE`. For legal edges, choose the relationship type from a Python enum before selecting one of seven constant queries; do not interpolate request data into Cypher.

Resolve edge precision exactly:

- source endpoint is `Provision(source_node_id)` when present, otherwise the
  `Instrument` owning `source_version_id`;
- target endpoint is `Provision(target_node_id)` when present, otherwise
  `Instrument(target_instrument_id)`;
- never invent a target provision from a quote or document number;
- a missing canonical endpoint blocks graph projection.

Normalize dates/timestamps to fixed-width ISO-8601 UTC strings before writing
them so template comparisons are deterministic.

Write one `GraphMetadata` node for the graph. Reject a pre-existing graph whose `release_id`, revision, or manifest checksum differs.

- [ ] **Step 6: Add real FalkorDB integration coverage**

The integration test must run against `VBPL_KB_FALKORDB_TEST_HOST` and:

1. create a uniquely named test graph;
2. project two instruments, two versions, three provisions, and one verified amendment;
3. project the same snapshot a second time;
4. assert counts remain unchanged;
5. assert graph metadata matches;
6. delete only its uniquely named test graph in test cleanup.

Run the integration database as a test-only container bound to localhost:

```powershell
$env:VBPL_FALKORDB_TEST_PASSWORD="integration-only"
docker run -d --rm --name vbpl-falkordb-integration -p 127.0.0.1:6380:6379 -e "REDIS_ARGS=--requirepass $env:VBPL_FALKORDB_TEST_PASSWORD" falkordb/falkordb-server:v4.20.1
$env:VBPL_KB_FALKORDB_TEST_HOST="127.0.0.1"
$env:VBPL_KB_FALKORDB_TEST_PORT="6380"
$env:VBPL_KB_FALKORDB_ADMIN_USERNAME="default"
$env:VBPL_KB_FALKORDB_ADMIN_PASSWORD=$env:VBPL_FALKORDB_TEST_PASSWORD
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/integration/test_falkordb_projector.py -q
docker stop vbpl-falkordb-integration
```

- [ ] **Step 7: Run unit and integration verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_projector.py tests/integration/test_falkordb_projector.py -q
uv run ruff check src/vbpl_kb/graph_models.py src/vbpl_kb/falkordb_client.py src/vbpl_kb/graph_projector.py
uv run mypy src/vbpl_kb/graph_models.py src/vbpl_kb/falkordb_client.py src/vbpl_kb/graph_projector.py
```

- [ ] **Step 8: Commit**

```powershell
git add src/vbpl_kb/graph_models.py src/vbpl_kb/falkordb_client.py src/vbpl_kb/graph_projector.py tests/test_graph_projector.py tests/integration/test_falkordb_projector.py
git commit -m "feat: project immutable FalkorDB release graphs"
```

---

## Task 5: Validate graph integrity before release promotion

**Files:**

- Create: `src/vbpl_kb/graph_validation.py`
- Modify: `src/vbpl_kb/cli.py`
- Create: `tests/test_graph_validation.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing validation tests**

Cover failures for:

- missing `GraphMetadata`;
- release/revision/checksum mismatch;
- node/edge count mismatch;
- dangling legal edge endpoint;
- duplicate `logical_edge_id`;
- missing official evidence;
- `effective_from > effective_to`;
- `searchable=false` edge in the serving graph.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_validation.py tests/test_cli.py -q
```

- [ ] **Step 3: Implement `GraphValidator`**

Expose:

```python
class GraphValidator:
    def validate(
        self,
        graph_name: str,
        expected: GraphMetadata,
    ) -> GraphValidationReport:
        return _validate_graph(self._reader, graph_name, expected)
```

Every read must call `ro_query` with
`timeout=settings.graph_query_timeout_ms`. A query timeout is a validation
error, never a warning.

- [ ] **Step 4: Add graph CLI commands**

Add:

```text
vbpl-kb graph-build --release-id <id>
vbpl-kb graph-validate --release-id <id>
```

`graph-build` must load the validated candidate manifest and PostgreSQL snapshot, project, validate, write `graph-validation.json` inside the immutable release directory, and exit non-zero on any error.

- [ ] **Step 5: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_validation.py tests/test_cli.py -q
uv run ruff check src/vbpl_kb/graph_validation.py src/vbpl_kb/cli.py
uv run mypy src/vbpl_kb/graph_validation.py src/vbpl_kb/cli.py
```

- [ ] **Step 6: Commit**

```powershell
git add src/vbpl_kb/graph_validation.py src/vbpl_kb/cli.py tests/test_graph_validation.py tests/test_cli.py
git commit -m "feat: gate releases on graph integrity"
```

---

## Task 6: Implement allowlisted current and historical traversal

**Files:**

- Create: `src/vbpl_kb/graph_queries.py`
- Create: `src/vbpl_kb/graph_retrieval.py`
- Create: `tests/test_graph_retrieval.py`
- Create: `tests/integration/test_falkordb_retrieval.py`

- [ ] **Step 1: Write failing request/template tests**

Define requests/results matching the approved design:

```python
class GraphExpansionRequest(BaseModel):
    query_id: str
    query_hash: str
    release_id: str
    corpus_revision: str
    mode: Literal["current", "history"]
    as_of: datetime | None
    seed_document_ids: tuple[str, ...]
    seed_instrument_ids: tuple[str, ...]
    seed_provision_ids: tuple[str, ...]
    exact_citations: tuple[ExactCitationSeed, ...] = ()
    clarification_only: bool = False
    allowed_relation_types: tuple[LegalRelationType, ...]
    max_legal_hops: int = 2
    max_candidates: int = 30


class GraphExpansionResult(BaseModel):
    release_id: str
    corpus_revision: str
    graph_name: str
    complete: bool
    canonical_candidates: tuple[GraphCandidate, ...]
    exact_document_ids: tuple[str, ...]
    scoped_candidate_document_ids: tuple[str, ...]
    relation_paths: tuple[RelationPath, ...]
    evidence_references: tuple[str, ...]
    excluded_candidates: tuple[ExcludedCandidate, ...]
    timings_ms: dict[str, float]
```

Tests must reject history mode without `as_of`, current mode with `as_of`, hop counts outside 1..3, unsupported relation types, too many seeds, and any raw-Cypher field.

`ExactCitationSeed` contains only a normalized official document number and an
optional normalized materialized path. The service resolves it through indexed
graph properties; it does not infer a relationship from the citation text.
When `clarification_only=true`, the service verifies readiness and graph
metadata, records the audit, and returns a complete empty candidate set without
traversal.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_retrieval.py -q
```

- [ ] **Step 3: Add fixed traversal templates**

Create an enum:

```python
class TraversalTemplate(str, Enum):
    CURRENT_AUTHORITY_BUNDLE = "current_authority_bundle"
    HISTORICAL_AUTHORITY_BUNDLE = "historical_authority_bundle"
```

Each template must hard-code the seven legal relationship labels and use:

```cypher
type(rel) IN $allowed_relation_types
```

The variable-length legal path may contain only:

```text
LEGAL_BASIS|AMENDS|SUPPLEMENTS|REPEALS|REPLACES|GUIDES_IMPLEMENTATION|CITES
```

`HAS_VERSION` and `CONTAINS` are matched outside the variable-length path, so they consume zero legal hops. Every edge predicate requires `searchable`, accepted resolution, evidence hash/reference, corpus revision, and valid effective range.

- [ ] **Step 4: Implement complete/incomplete semantics**

Return `complete=false` when:

- FalkorDB reports timeout;
- raw rows reach `max_paths` or candidates reach the configured hard limit;
- an endpoint cannot map to the candidate release catalog;
- a returned edge lacks required evidence;
- graph metadata differs from the request.

A complete zero-row query returns `complete=true` with empty candidate/path lists.

- [ ] **Step 5: Implement stable Onyx ID mapping**

Use `ReleaseDocumentCatalog`:

- provision endpoint -> `exact_document_ids`;
- instrument endpoint -> at most `graph_max_instrument_documents` in `scoped_candidate_document_ids`;
- no Evidence-view IDs;
- current/history selection follows `mode` and `as_of`.

- [ ] **Step 6: Add real traversal integration tests**

Prove:

- one- and two-hop amendment/legal-basis paths work;
- structural edges do not increase hop count;
- current mode excludes stale/ineligible versions;
- history mode selects the version covering `as_of`;
- a `CITES` path is marked `is_verified_effect=false`;
- query timeout and limit saturation are blocking/incomplete.

Run:

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/integration/test_falkordb_retrieval.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/vbpl_kb/graph_queries.py src/vbpl_kb/graph_retrieval.py tests/test_graph_retrieval.py tests/integration/test_falkordb_retrieval.py
git commit -m "feat: add bounded legal graph traversal"
```

---

## Task 7: Expose the authenticated Graph Retrieval Service

**Files:**

- Create: `src/vbpl_kb/graph_api.py`
- Modify: `src/vbpl_kb/cli.py`
- Create: `tests/test_graph_api.py`
- Modify: `docker/Dockerfile.pipeline`

- [ ] **Step 1: Write failing API contract tests**

Using `fastapi.testclient.TestClient`, require:

- `401` for absent/wrong bearer token;
- `200` for a complete result, including the exact response schema;
- `409` for release/revision/readiness mismatch;
- `503` for FalkorDB unavailable/timeout/incomplete traversal;
- no endpoint accepts Cypher;
- request logs/audits contain only `query_hash`, not raw query text.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_api.py -q
```

- [ ] **Step 3: Implement the API**

Expose only:

```text
GET  /health
GET  /v1/readiness
POST /v1/expand
```

`/health` proves process health only. `/v1/readiness` validates active/ready/graph metadata. `/v1/expand` calls `GraphRetrievalService`, records `GraphQueryAudit`, and returns the typed result.

Authenticate with:

```python
secrets.compare_digest(
    credentials.credentials,
    settings.graph_service_token.get_secret_value(),
)
```

Fail startup when the token or reader password is blank.

- [ ] **Step 4: Add `serve-graph`**

Add a CLI command that invokes:

```python
uvicorn.run("vbpl_kb.graph_api:app", host="0.0.0.0", port=8091)
```

The existing Docker image entrypoint remains `vbpl-kb`; Compose will use `command: ["serve-graph"]`.

- [ ] **Step 5: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_graph_api.py tests/test_cli.py -q
uv run ruff check src/vbpl_kb/graph_api.py src/vbpl_kb/cli.py
uv run mypy src/vbpl_kb/graph_api.py src/vbpl_kb/cli.py
```

- [ ] **Step 6: Commit**

```powershell
git add src/vbpl_kb/graph_api.py src/vbpl_kb/cli.py docker/Dockerfile.pipeline tests/test_graph_api.py tests/test_cli.py
git commit -m "feat: expose typed graph retrieval service"
```

---

## Task 8: Reconcile exact Onyx document IDs and write retrieval readiness

**Files:**

- Fix: `scripts/verify-schema-v2-index.py`
- Create: `src/vbpl_kb/onyx_reconciliation.py`
- Create: `src/vbpl_kb/readiness.py`
- Create: `tests/test_schema_v2_verifier.py`
- Create: `tests/test_onyx_reconciliation.py`
- Create: `tests/test_readiness.py`

- [ ] **Step 1: Write a regression test for the current verifier bug**

The test must prove `fetch_opensearch_docs(["vbpl:1", "vbpl:2"])` sends a `terms` query on `document_id` and does not inspect the first arbitrary 50 hits.

- [ ] **Step 2: Write failing reconciliation/readiness tests**

Cover:

- every expected Current/History document ID exists;
- no extra document with the target release/revision exists outside expected IDs;
- all matched chunks have `vbpl_export`, the expected Document Set, release ID, revision, and Schema-v2 metadata;
- missing/old/mixed metadata blocks readiness;
- `retrieval-ready.json` is written atomically only after graph and Onyx reports pass.

Expected readiness model:

```python
class RetrievalReady(BaseModel):
    release_id: str
    corpus_revision: str
    graph_name: str
    manifest_sha256: str
    view_manifest_sha256: dict[Literal["current", "history"], str]
    onyx_reconciliation: OnyxReconciliationReport
    graph_validation: GraphValidationReport
    verified_at: datetime
```

- [ ] **Step 3: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_schema_v2_verifier.py tests/test_onyx_reconciliation.py tests/test_readiness.py -q
```

- [ ] **Step 4: Fix exact-ID Schema-v2 verification**

Use a POST body equivalent to:

```json
{
  "size": 500,
  "_source": ["document_id", "source_type", "document_sets", "metadata_list"],
  "query": {"terms": {"document_id": ["vbpl:1", "vbpl:2"]}}
}
```

Deduplicate chunk hits by `document_id`. Missing requested IDs are errors. Remove the mock-success fallback from operational execution; network failure must return non-zero.

- [ ] **Step 5: Implement OpenSearch reconciliation**

Batch expected IDs from Current and History `active-ids.jsonl`, query `opensearch_index_pattern`, parse `metadata_list` entries of the form `key===value`, and compare unique document IDs and metadata. Do not include the Evidence view in the legal readiness gate.

- [ ] **Step 6: Implement atomic readiness operations**

Expose:

```python
ReadinessManager.read_active() -> ActiveRelease
ReadinessManager.read_ready() -> RetrievalReady | None
ReadinessManager.assert_queryable() -> RetrievalReady
ReadinessManager.promote_ready(candidate: RetrievalReady) -> None
```

`assert_queryable()` must compare active release, ready pointer, manifest checksum, and graph metadata every time.

- [ ] **Step 7: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_schema_v2_verifier.py tests/test_onyx_reconciliation.py tests/test_readiness.py -q
uv run ruff check scripts/verify-schema-v2-index.py src/vbpl_kb/onyx_reconciliation.py src/vbpl_kb/readiness.py
uv run mypy src/vbpl_kb/onyx_reconciliation.py src/vbpl_kb/readiness.py
```

- [ ] **Step 8: Commit**

```powershell
git add scripts/verify-schema-v2-index.py src/vbpl_kb/onyx_reconciliation.py src/vbpl_kb/readiness.py tests/test_schema_v2_verifier.py tests/test_onyx_reconciliation.py tests/test_readiness.py
git commit -m "feat: gate retrieval on exact Onyx reconciliation"
```

---

## Task 9: Enforce the approved daily publication order

**Files:**

- Modify: `src/vbpl_kb/cli.py`
- Modify: `src/vbpl_kb/connector_control.py`
- Modify: `src/vbpl_kb/repositories.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_connector_control.py`
- Create: `tests/test_daily_graph_release.py`

- [ ] **Step 1: Write a failing orchestration-order test**

Use spies and assert this exact sequence:

```text
build candidate
validate candidate
build graph
validate graph
promote active release
trigger/wait Current connector
trigger/wait History connector
reconcile Onyx
verify Schema-v2
promote retrieval readiness
```

Also assert graph failure prevents active promotion, while connector/reconciliation failure leaves readiness unchanged.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_daily_graph_release.py tests/test_connector_control.py tests/test_cli.py -q
```

- [ ] **Step 3: Replace the single-connector path**

Require `onyx_current_connector_id` and `onyx_history_connector_id` for `run-daily`. Trigger each with `from_beginning=False`, wait for the returned attempt ID to reach indexed success, and persist two `ConnectorDelivery` records. Evidence sync may run separately and must not make a legal release ready.

- [ ] **Step 4: Wire graph and readiness gates**

Refactor `run_daily()` into an orchestration service whose dependencies can be tested without network calls. Do not catch and continue after canonical DB initialization errors. Remove the broad `except Exception: pass` fallback that silently replaces PostgreSQL repositories with the placeholder `StateStore`.

- [ ] **Step 5: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_daily_graph_release.py tests/test_connector_control.py tests/test_cli.py -q
uv run ruff check src/vbpl_kb/cli.py src/vbpl_kb/connector_control.py src/vbpl_kb/repositories.py
uv run mypy src/vbpl_kb/cli.py src/vbpl_kb/connector_control.py src/vbpl_kb/repositories.py
```

- [ ] **Step 6: Commit**

```powershell
git add src/vbpl_kb/cli.py src/vbpl_kb/connector_control.py src/vbpl_kb/repositories.py tests/test_daily_graph_release.py tests/test_connector_control.py tests/test_cli.py
git commit -m "feat: publish graph-ready legal releases"
```

---

## Task 10: Add the Onyx overlay graph client and phase-two retrieval strategy

**Files:**

- Create: `infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_models.py`
- Create: `infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_client.py`
- Create: `infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_query_context.py`
- Create: `infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_search.py`
- Create: `infra/onyx/overlay/backend/tests/unit/onyx/tools/test_vbpl_graph_search.py`
- Create: `tests/test_onyx_graph_overlay.py`

- [ ] **Step 1: Write failing overlay contract tests**

The repository-level test must assert the overlay contains:

- class `VBPLGraphAugmentedSearchTool`;
- tool name inherited as `internal_search`;
- `id_based_retrieval`;
- `attached_document_ids`;
- `SearchDocsResponse`;
- release/readiness validation;
- no raw Cypher.

The Onyx unit test must fake `DocumentIndex`, graph HTTP, and emitter.

Add pure parser tests for:

- full ISO and `dd/mm/yyyy` point-in-time dates;
- official VBPL URLs ending in `--<official_source_id>`;
- Vietnamese instrument numbers such as `87/2025/QH15`;
- `Điều`, `Khoản`, and `Điểm` coordinates paired with the named instrument;
- no relationship inference from words such as “sửa đổi” or “bãi bỏ”.

- [ ] **Step 2: Run repository-level test and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_onyx_graph_overlay.py -q
```

- [ ] **Step 3: Implement deterministic query context parsing**

Expose:

```python
@dataclass(frozen=True)
class VBPLQueryContext:
    mode: Literal["current", "history"]
    as_of: datetime | None
    official_source_ids: tuple[str, ...]
    exact_citations: tuple[ExactCitationSeed, ...]
    temporal_clarification_required: bool = False
```

Only a fully specified date selects history mode in the MVP. Month-only,
year-only, or conflicting dates set `temporal_clarification_required=true`;
the graph call still occurs with `clarification_only=true`, phase-one documents
are withheld from the LLM, and the tool response requests a precise date. Do
not silently choose the last day of a month or year.

- [ ] **Step 4: Implement the strict HTTP client**

`VBPLGraphClient.expand()` must:

- send one authenticated POST to `/v1/expand`;
- use connect/read timeout below the Onyx tool timeout;
- reject non-200, schema-invalid, incomplete, release-mismatched, or revision-mismatched responses by raising `VBPLGraphFatalError`;
- treat a complete empty result as valid.

- [ ] **Step 5: Implement `VBPLGraphAugmentedSearchTool` as a SearchTool strategy**

The subclass overrides a protected phase-one augmentation hook added in Task 11. Its method receives phase-one `InferenceSection` values plus the original filters, ACLs, embedding model, query, and override kwargs.

Also define:

```python
class VBPLSearchDocsResponse(SearchDocsResponse):
    graph_evidence: GraphExecutionEvidence
```

The subclass overrides a response-construction hook so successful graph
evidence is present even when phase one and phase two return zero documents.
Because this is a `SearchDocsResponse` subclass, existing citation merging and
Chat UI handling continue to use the stock code path.

Algorithm:

1. read and compare `active-release.json` and `retrieval-ready.json` from the read-only export mount;
2. derive stable seed IDs from section `document_id` and metadata;
3. call Graph Retrieval Service exactly once;
4. call `id_based_retrieval()` for `exact_document_ids`;
5. call `search_pipeline()` for instrument candidates with a copied `PersonaSearchInfo(attached_document_ids=list(scoped_candidate_document_ids))`, preserving Document Sets and ACLs;
6. reject any returned ID outside the graph-approved sets;
7. reject missing expected exact IDs;
8. validate every returned document's release/revision/source/view;
9. merge and rerank before stock Onyx document selection/citation conversion.

The existing OpenSearch implementation maps `attached_document_ids` to a `document_id` filter, so no new public Search filter is added.

Add compact graph provenance to each returned `SearchDoc.metadata`:

```text
vbpl_graph_query_id
vbpl_graph_release_id
vbpl_graph_corpus_revision
vbpl_graph_complete
vbpl_graph_path_ids
vbpl_graph_evidence_hashes
```

Detailed path/candidate audit remains in PostgreSQL; do not place raw query text
or unbounded path JSON into document metadata.

- [ ] **Step 6: Implement deterministic reranking**

Use a pure function covered by tests:

```python
score = base_rrf
score += 1.0 if exact_provision else 0.0
score += relation_weight / max(hop_count, 1)
score += 0.25 if current_or_as_of_applicable else 0.0
```

Where `relation_weight` is:

```python
{
    "AMENDS": 1.0,
    "SUPPLEMENTS": 1.0,
    "REPEALS": 1.0,
    "REPLACES": 1.0,
    "LEGAL_BASIS": 0.8,
    "GUIDES_IMPLEMENTATION": 0.7,
    "CITES": 0.2,
}
```

Do not add a standalone numeric authority-order boost. Deduplicate by `(document_id, chunk_id)` and cap merged candidates so final context can remain within 125% of the baseline.

- [ ] **Step 7: Run overlay tests**

After bootstrapping the pinned checkout:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/bootstrap-onyx.ps1
Push-Location .onyx/onyx/backend
$env:PYTHONPATH="$PWD"
uv run pytest tests/unit/onyx/tools/test_vbpl_graph_search.py -q
Pop-Location
```

- [ ] **Step 8: Commit**

```powershell
git add infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_models.py infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_client.py infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_query_context.py infra/onyx/overlay/backend/onyx/tools/tool_implementations/search/vbpl_graph_search.py infra/onyx/overlay/backend/tests/unit/onyx/tools/test_vbpl_graph_search.py tests/test_onyx_graph_overlay.py
git commit -m "feat: add graph-augmented Onyx search strategy"
```

---

## Task 11: Patch pinned Onyx CE for mandatory selection and fatal fail-closed behavior

**Files:**

- Create: `infra/onyx/patches/vbpl-graph-search.patch`
- Modify: `scripts/bootstrap-onyx.ps1`
- Create: `infra/onyx/overlay/backend/tests/unit/onyx/tools/test_vbpl_graph_fail_closed.py`
- Modify: `tests/test_bootstrap_onyx.py`
- Modify: `tests/test_onyx_graph_overlay.py`

- [ ] **Step 1: Write failing patch-content tests**

Require the patch to touch only these pinned upstream files:

```text
backend/onyx/tools/tool_implementations/search/search_tool.py
backend/onyx/tools/tool_constructor.py
backend/onyx/chat/process_message.py
backend/onyx/tools/tool_runner.py
```

Require symbols:

```text
_augment_top_sections
_build_search_docs_response
VBPLGraphAugmentedSearchTool
is_vbpl_graph_persona
VBPLGraphFatalError
allow_failures=not has_vbpl_graph_call
```

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_bootstrap_onyx.py tests/test_onyx_graph_overlay.py -q
```

- [ ] **Step 3: Add the minimal `SearchTool` hook**

Move construction of `secondary_flows_user_query` above the augmentation hook.
At the pinned source point immediately after:

```python
top_sections = merge_individual_chunks(top_chunks)[: override_kwargs.num_hits]
```

call:

```python
top_sections = self._augment_top_sections(
    top_sections=top_sections,
    original_query=secondary_flows_user_query,
    effective_filters=effective_filters,
    acl_filters=acl_filters,
    embedding_model=embedding_model,
    override_kwargs=override_kwargs,
)
```

The stock `SearchTool._augment_top_sections()` returns its input unchanged. Non-VBPL behavior therefore remains byte-for-byte equivalent after the hook.

Add stock `_build_search_docs_response` with the same `search_docs`,
`citation_mapping`, and `displayed_docs` arguments used by
`SearchDocsResponse`, and use it for both empty and non-empty returns. The VBPL subclass returns
`VBPLSearchDocsResponse` with its recorded graph evidence.

- [ ] **Step 4: Select the VBPL tool server-side**

`is_vbpl_graph_persona(persona)` returns true only when the persona Document Sets are exactly:

```text
VBPL-current
VBPL-current + VBPL-history
```

It returns false for `VBPL-evidence` and every non-VBPL agent.

For a VBPL legal persona:

- `_build_search_tool()` constructs `VBPLGraphAugmentedSearchTool`;
- Search Tool is added even if client `allowed_tool_ids` omits it;
- `SearchToolUsage.DISABLED` is overridden;
- `forced_tool_id` is set to the built-in Search Tool ID;
- absence of a registered Search Tool raises before the LLM loop.

- [ ] **Step 5: Propagate fatal graph failures out of the tool loop**

In `_safe_run_single_tool`, re-raise `VBPLGraphFatalError` before ordinary `ToolCallException`/`Exception` handling.

In `run_tool_calls`, detect a VBPL graph call and use:

```python
allow_failures=not has_vbpl_graph_call
```

All other ordinary tool exceptions retain current behavior. A fatal graph error therefore escapes `run_tool_calls`, fails the worker, and prevents the next LLM cycle.

- [ ] **Step 6: Test mandatory and fatal behavior in pinned Onyx**

Cover:

- a client request with actions disabled still constructs/forces graph search;
- non-VBPL persona still gets stock Search Tool;
- complete empty expansion continues;
- graph timeout, stale revision, incomplete response, and missing target raise through `run_llm_loop`;
- no normal `ToolResponse` containing an error is sent back to the LLM.

Run:

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/bootstrap-onyx.ps1
Push-Location .onyx/onyx/backend
$env:PYTHONPATH="$PWD"
uv run pytest tests/unit/onyx/tools/test_vbpl_graph_search.py tests/unit/onyx/tools/test_vbpl_graph_fail_closed.py -q
Pop-Location
```

- [ ] **Step 7: Commit**

```powershell
git add infra/onyx/patches/vbpl-graph-search.patch scripts/bootstrap-onyx.ps1 infra/onyx/overlay/backend/tests/unit/onyx/tools/test_vbpl_graph_fail_closed.py tests/test_bootstrap_onyx.py tests/test_onyx_graph_overlay.py
git commit -m "feat: force fail-closed graph search in Onyx CE"
```

---

## Task 12: Deploy FalkorDB, Graph Service, and Onyx overlay on private networks

**Files:**

- Modify: `docker-compose.vbpl.yml`
- Modify: `infra/onyx/docker-compose.vbpl-connector.yml`
- Modify: `scripts/start-onyx.ps1`
- Modify: `tests/test_deployment_files.py`
- Modify: `tests/test_onyx_deployment.py`
- Modify: `tests/test_release_deployment.py`

- [ ] **Step 1: Write failing deployment assertions**

Require:

- `vbpl-falkordb` uses `falkordb/falkordb-server:v4.20.1`;
- port 6379 is exposed only to internal Compose networks, not the host;
- ACL file and persistent data volume are mounted;
- `TIMEOUT_MAX`, `TIMEOUT_DEFAULT`, `RESULTSET_SIZE`, and `QUERY_MEM_CAPACITY` are bounded;
- `vbpl-graph-service` depends on healthy FalkorDB and migrated PostgreSQL;
- Graph Service has the export mount read-only;
- Onyx `api_server` has the export mount read-only plus graph URL/token;
- Onyx background remains the only connector consumer;
- no Compose file contains a password/token literal.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_deployment_files.py tests/test_onyx_deployment.py tests/test_release_deployment.py -q
```

- [ ] **Step 3: Add FalkorDB and Graph Service**

Use:

```yaml
vbpl-falkordb:
  image: falkordb/falkordb-server:v4.20.1
  expose: ["6379"]
  environment:
    - REDIS_ARGS=--aclfile /run/secrets/users.acl --appendonly yes --appendfsync everysec
    - FALKORDB_ARGS=TIMEOUT_MAX 5000 TIMEOUT_DEFAULT 2000 RESULTSET_SIZE 500 QUERY_MEM_CAPACITY 134217728
  volumes:
    - vbpl-falkordb-data:/data
    - ${VBPL_FALKORDB_ACL_PATH:-./data/runtime-secrets/falkordb-users.acl}:/run/secrets/users.acl:ro

vbpl-graph-service:
  image: vbpl-kb-pipeline:latest
  command: ["serve-graph"]
  restart: unless-stopped
  expose: ["8091"]
```

Attach both services to the project default network; attach Graph Service to the external Onyx network. Do not attach Onyx directly to FalkorDB.

- [ ] **Step 4: Wire the integration-test container**

Make `vbpl-test` depend on healthy `vbpl-falkordb` when the `test` profile is
selected and pass only environment references for the projector/reader
credentials. Integration tests run inside the Compose default network against
`vbpl-falkordb:6379`; the production service still has no host port.

- [ ] **Step 5: Wire Onyx read-only readiness access**

Mount `${VBPL_EXPORT_HOST_PATH}:/app/vbpl-export:ro` into `api_server`. Add:

```text
VBPL_GRAPH_SERVICE_URL=http://vbpl-graph-service:8091
VBPL_GRAPH_SERVICE_TOKEN
VBPL_GRAPH_ACTIVE_RELEASE_PATH=/app/vbpl-export/active-release.json
VBPL_GRAPH_READY_PATH=/app/vbpl-export/retrieval-ready.json
VBPL_GRAPH_CURRENT_DOCUMENT_SET=VBPL-current
VBPL_GRAPH_HISTORY_DOCUMENT_SET=VBPL-history
```

- [ ] **Step 6: Update startup sequencing**

`scripts/start-onyx.ps1` must:

1. validate/generate the ACL file;
2. start `vbpl-db`, migrate, FalkorDB, and Graph Service;
3. bootstrap/build the pinned Onyx overlay;
4. start Onyx;
5. check process health without claiming retrieval readiness.

- [ ] **Step 7: Validate Compose and tests**

```powershell
docker compose -f docker-compose.vbpl.yml config
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_deployment_files.py tests/test_onyx_deployment.py tests/test_release_deployment.py -q
```

- [ ] **Step 8: Commit**

```powershell
git add docker-compose.vbpl.yml infra/onyx/docker-compose.vbpl-connector.yml scripts/start-onyx.ps1 tests/test_deployment_files.py tests/test_onyx_deployment.py tests/test_release_deployment.py
git commit -m "ops: deploy private FalkorDB graph retrieval"
```

---

## Task 13: Extend live Chat acceptance with graph and legal-safety evidence

**Files:**

- Modify: `src/vbpl_kb/onyx_chat.py`
- Modify: `src/vbpl_kb/acceptance.py`
- Modify: `src/vbpl_kb/evaluate.py`
- Create: `data/benchmarks/vbpl-graph-acceptance.json`
- Modify: `tests/test_acceptance.py`
- Modify: `tests/test_evaluate.py`
- Create: `tests/test_graph_acceptance.py`

- [ ] **Step 1: Write failing acceptance tests**

Extend tool evidence:

```python
class GraphExecutionEvidence(BaseModel):
    query_id: str
    release_id: str
    corpus_revision: str
    graph_name: str
    complete: bool
    relation_paths: tuple[RelationPathEvidence, ...]
    evidence_hashes: tuple[str, ...]
    phase_timings_ms: dict[str, float]
```

Each substantive Chat turn must contain exactly one `internal_search` call and one successful graph execution record.

- [ ] **Step 2: Run tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_acceptance.py tests/test_evaluate.py tests/test_graph_acceptance.py -q
```

- [ ] **Step 3: Parse and enforce graph evidence**

Update `OnyxChatClient` for the pinned non-streaming response shape. Acceptance fails when:

- graph evidence is absent/incomplete;
- release/revision differs from the acceptance context;
- a path has no official evidence hash;
- a result leaks outside `vbpl_export` or permitted Document Sets;
- current-law status is stale/unknown;
- historical evidence does not cover `as_of`;
- an answer exists after a simulated fatal graph response.

- [ ] **Step 4: Add the benchmark corpus**

Include at least:

- instrument-to-instrument amendment;
- provision-to-provision amendment;
- implementation guidance;
- two-hop legal-basis chain;
- Current query;
- historical `as_of` query;
- verified citation-only relationship;
- no verified relation;
- stale status;
- conflicting evidence;
- graph outage;
- revision mismatch;
- missing Onyx target.

Every relationship case names expected stable document IDs, expected relation types, and expected evidence hashes.

- [ ] **Step 5: Enforce approved gates without a latency threshold**

Report:

```text
graph_invocation_coverage
internal_search_coverage
evidence_backed_path_coverage
current_law_safety
controlling_provision_recall_at_10
authority_bundle_completeness_at_10
context_size_ratio
phase_1_latency_ms
graph_latency_ms
phase_2_latency_ms
total_search_latency_ms
```

Pass only when:

- first four coverage/safety metrics are 1.0;
- no source/Document Set leakage occurs;
- controlling recall@10 is not below the recorded baseline;
- authority-bundle completeness improves on relationship cases;
- context size ratio is at most 1.25.

Latency values are report-only.

- [ ] **Step 6: Run focused verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_acceptance.py tests/test_evaluate.py tests/test_graph_acceptance.py -q
uv run ruff check src/vbpl_kb/onyx_chat.py src/vbpl_kb/acceptance.py src/vbpl_kb/evaluate.py
uv run mypy src/vbpl_kb/onyx_chat.py src/vbpl_kb/acceptance.py src/vbpl_kb/evaluate.py
```

- [ ] **Step 7: Commit**

```powershell
git add src/vbpl_kb/onyx_chat.py src/vbpl_kb/acceptance.py src/vbpl_kb/evaluate.py data/benchmarks/vbpl-graph-acceptance.json tests/test_acceptance.py tests/test_evaluate.py tests/test_graph_acceptance.py
git commit -m "test: require graph-grounded legal chat evidence"
```

---

## Task 14: Update canonical documentation and run end-to-end verification

**Files:**

- Modify: `AGENTS.md`
- Modify: `docs/architecture.md`
- Modify: `docs/legal-data-policy.md`
- Modify: `docs/operations.md`
- Modify: `docs/onyx-agent-setup.md`
- Modify: `docs/development-workflow.md`
- Modify: `README.md`
- Test: `tests/test_docs_current_guidance.py`

- [ ] **Step 1: Write failing documentation-routing assertions**

Require current documents to name:

- FalkorDB as derived/rebuildable;
- Graph Retrieval Service as the only runtime graph reader;
- mandatory graph-augmented `internal_search`;
- release readiness pointer and publication order;
- fail-closed query behavior;
- Current/History Document Set names;
- safe graph rebuild/recovery that never deletes PostgreSQL/evidence/releases.

- [ ] **Step 2: Run docs tests and confirm failure**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest tests/test_docs_current_guidance.py -q
```

- [ ] **Step 3: Update current documentation**

Keep `AGENTS.md` and README thin. Put ownership/data flow in architecture, legal acceptance rules in legal-data policy, commands/recovery in operations, and UI/admin requirements in Onyx agent setup.

Document these recovery rules:

- rebuilding a release graph creates/reuses only the matching release-scoped graph;
- never delete `vbpl-postgres-data`, evidence, release exports, or older graphs to recover;
- readiness stays unchanged until exact reconciliation succeeds;
- connector sync windows and mixed revisions intentionally fail closed;
- blue/green indexing remains deferred.

- [ ] **Step 4: Run the complete repository verification**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run pytest -q
uv run ruff check .
uv run mypy src
```

Expected: all tests pass, with only explicitly environment-gated integration tests skipped when their services are absent.

- [ ] **Step 5: Run real FalkorDB and PostgreSQL integration verification**

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/bootstrap-falkordb-acl.ps1
docker compose -f docker-compose.vbpl.yml up -d vbpl-db vbpl-falkordb
docker compose -f docker-compose.vbpl.yml run --rm vbpl-migrate
docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test tests/integration/test_postgres_migrations.py tests/integration/test_falkordb_projector.py tests/integration/test_falkordb_retrieval.py -q
```

- [ ] **Step 6: Build and validate a real candidate graph**

```powershell
$releaseId = (Get-Content data/exports/active-release.json -Raw | ConvertFrom-Json).release_id
uv run vbpl-kb graph-build --release-id $releaseId
uv run vbpl-kb graph-validate --release-id $releaseId
```

Expected: graph metadata/revision/checksum and all integrity counts pass.

- [ ] **Step 7: Rebuild/start Onyx and run exact Schema-v2 verification**

```powershell
pwsh -ExecutionPolicy Bypass -File scripts/start-onyx.ps1
$active = Get-Content data/exports/active-release.json -Raw | ConvertFrom-Json
$currentShard = Join-Path "data/exports/releases" "$($active.release_id)/current/documents-00000.jsonl"
$exactIds = Get-Content $currentShard | Select-Object -First 10 | ForEach-Object { ($_ | ConvertFrom-Json).document_id }
uv run python scripts/verify-schema-v2-index.py @exactIds
```

When explicit IDs are supplied, the verifier must check those exact IDs. It must not report success by falling back to mock metadata.

- [ ] **Step 8: Run live native Chat acceptance**

```powershell
$env:UV_CACHE_DIR="$PWD\.uv-cache"
uv run vbpl-kb onyx-acceptance data/benchmarks/vbpl-graph-acceptance.json --label graph-mvp
```

Inspect the generated report and require:

- actual native Chat response;
- exactly one visible `internal_search` per substantive turn;
- graph evidence on every query;
- Current/History Document Set confinement;
- expected graph-expanded IDs and citations;
- zero safety failures;
- no answer on graph outage/revision mismatch;
- reported, non-gating phase latency.

- [ ] **Step 9: Verify the worktree and commit documentation**

```powershell
git status --short
git diff --check
git add AGENTS.md README.md docs/architecture.md docs/legal-data-policy.md docs/operations.md docs/onyx-agent-setup.md docs/development-workflow.md tests/test_docs_current_guidance.py
git commit -m "docs: operate graph-augmented VBPL retrieval"
```

---

## Final Review Checklist

- [ ] Search the implementation for placeholder markers, raw Cypher request fields, unpinned FalkorDB tags, hard-coded tokens/passwords, and direct `.onyx/onyx` edits; none may remain.
- [ ] Confirm every production graph read uses `ro_query` with a timeout and every Cypher value is passed through `params`.
- [ ] Confirm only official, accepted, searchable relations are projected and `CITES` is never marked as verified legal effect.
- [ ] Confirm every VBPL Current/Historical Chat turn is server-forced through graph search even when client actions are disabled.
- [ ] Confirm fatal graph failures escape the Onyx tool runner and no LLM answer cycle follows.
- [ ] Confirm phase two uses exact IDs or `attached_document_ids` while preserving source, Document Set, revision, and ACL filters.
- [ ] Confirm Current/History readiness is exact-ID reconciled before `retrieval-ready.json` advances.
- [ ] Confirm non-VBPL and Evidence agents retain stock Search Tool behavior.
- [ ] Confirm the full test/Ruff/mypy gate and live FalkorDB/Onyx acceptance evidence are recorded in the implementation handoff.
