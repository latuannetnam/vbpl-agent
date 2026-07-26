# VBPL Multi-Resolution Stock-Onyx Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the VBPL pipeline on a canonical PostgreSQL legal model and publish Current, History, and Evidence multi-resolution views that stock Onyx retrieves exclusively through `internal_search`.

**Architecture:** Official VBPL evidence is retained in a content-addressed volume and normalized into immutable instrument versions plus a `Part -> Chapter -> Article -> Clause -> Point` tree in a project-owned PostgreSQL database. Projectors produce one-section Article, Atomic, Relation, and Evidence documents with disjoint global IDs. Immutable checksummed JSONL releases feed three configurations of the existing `vbpl_export` overlay into one stock Onyx index, isolated by document sets. Release, delivery, readiness, acceptance, and destructive cutover are separate state transitions.

**Tech Stack:** Python 3.12, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3, PostgreSQL 17, httpx, Typer, pytest, Ruff, mypy, Docker Compose, stock Onyx pinned at `e31b356caed3c4767a66c5f790d497b28784fd74`, and the project-owned `vbpl_export` connector/UI overlay.

## Global Constraints

- Official VBPL API and canonical-page evidence are authoritative. Preserve official URL, legal status, verification time, corpus revision, source anchors, evidence hashes, and raw evidence for every searchable record.
- Do not migrate `data/state.sqlite3`, legacy `data/raw` rows, schema-v1/schema-v2 projection documents, or legacy `vbpl:<official-id>` Onyx documents. Build the new PostgreSQL database and release from official sources.
- Do not change Onyx core retrieval, chunking, embedding, ranking, reranking, relational schema, or indexing behavior. Changes under `infra/onyx/overlay/` and the generated patch may only register/configure the connector source and UI.
- All runtime legal retrieval and all acceptance evidence must come through Onyx `internal_search`, with source type `vbpl_export` and the Agent's explicit document sets. A legally correct answer without this tool evidence fails.
- Every projected Onyx document has exactly one `TextSection`. Article documents may be sentence-split by stock Onyx, but no document crosses an Article, Atomic leaf, Relation edge, or Evidence-record boundary.
- Keep Current, History, and Evidence IDs in disjoint global namespaces. Current IDs are stable by logical path or logical edge and never include mutable text.
- A partial/failed catalog scan cannot advance the baseline, create tombstones, promote a release, or refresh current-law readiness. Two consecutive complete scans are required before removal.
- Current-law eligibility requires fresh verified official status and sufficient applicability/structure evidence. Heuristic or unparsed structure remains discoverable outside exact current-law citation.
- Do not use authority as a global Onyx boost. Authority ordering is applied only after applicability gates and bounded authority-bundle retrieval.
- Docker Compose is the canonical build, migration, crawl, test, backup, and cutover path. Native `uv` commands remain the fast developer test loop.
- Preserve the existing scoped VBPL Onyx service until the new full candidate passes pre-index validation and capacity estimation. Never delete unrelated Onyx users, Agents, connectors, document sets, models, database state, indexes, or volumes.
- Do not commit `.env`, credentials, PostgreSQL dumps, evidence objects, release artifacts, rendered Compose containing secrets, or edits under `.onyx/onyx`.
- After each production behavior change, run the focused failing test first, implement the narrow behavior, make it pass, and commit only the files owned by that task.

---

### Task 1: Establish the PostgreSQL schema and transaction boundary

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `src/vbpl_kb/config.py`
- Create: `src/vbpl_kb/db.py`
- Create: `src/vbpl_kb/db_models.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/20260726_01_canonical_vbpl.py`
- Create: `tests/test_db.py`
- Create: `tests/integration/test_postgres_migrations.py`
- Modify: `docker-compose.vbpl.yml`
- Modify: `docker/Dockerfile.pipeline`
- Modify: `.env.example`

**Interfaces:**

- Consumes `Settings.database_url: SecretStr` and `Settings.pipeline_lock_key: int`.
- Produces `create_engine(database_url: SecretStr) -> Engine`.
- Produces `create_session_factory(engine: Engine) -> sessionmaker[Session]`.
- Produces `session_scope(factory: sessionmaker[Session]) -> Iterator[Session]`.
- Produces `pipeline_advisory_lock(session: Session, lock_key: int) -> Iterator[None]`.
- Migration head creates the complete empty canonical schema without reading SQLite.

- [ ] **Step 1: Add failing database configuration and migration tests**

  In `tests/test_db.py`, assert that `Settings` requires a non-empty
  `VBPL_KB_DATABASE_URL` outside unit-test overrides, that the URL is represented
  as `SecretStr`, and that `pipeline_advisory_lock()` executes
  `pg_try_advisory_lock` and always calls `pg_advisory_unlock`.

  In `tests/integration/test_postgres_migrations.py`, mark the test
  `@pytest.mark.postgres` and assert that `alembic upgrade head` on an empty test
  database creates these tables:

  ```python
  EXPECTED_TABLES = {
      "pipeline_runs",
      "catalog_scans",
      "catalog_observations",
      "removal_candidates",
      "evidence_objects",
      "evidence_dependencies",
      "instruments",
      "instrument_versions",
      "legal_nodes",
      "authority_regimes",
      "authority_classifications",
      "status_observations",
      "applicability_envelopes",
      "legal_relations",
      "release_runs",
      "release_views",
      "connector_deliveries",
      "acceptance_runs",
  }
  ```

  Also assert that a second `alembic upgrade head` is idempotent and that the
  database contains no tables imported from the legacy SQLite store.

- [ ] **Step 2: Run the focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_db.py -q
  ```

  Expected: import/configuration failures because the PostgreSQL boundary does
  not exist.

- [ ] **Step 3: Add PostgreSQL dependencies and settings**

  Add:

  ```toml
  "alembic>=1.16,<2",
  "psycopg[binary]>=3.2,<4",
  "sqlalchemy>=2.0,<3",
  ```

  Replace `db_path`-driven configuration with:

  ```python
  database_url: SecretStr
  pipeline_lock_key: int = 868075126
  evidence_dir: Path = Path("/app/data/evidence")
  export_dir: Path = Path("/app/data/exports")
  ```

  Unit tests may instantiate `Settings(database_url=SecretStr(
  "postgresql+psycopg://vbpl:vbpl@localhost/vbpl_test"))`; production commands
  must fail before work starts when the secret is absent.

- [ ] **Step 4: Implement the transaction and advisory-lock helpers**

  Use SQLAlchemy 2 typed APIs. `pipeline_advisory_lock()` must fail fast when
  `SELECT pg_try_advisory_lock(:key)` returns false:

  ```python
  @contextmanager
  def pipeline_advisory_lock(session: Session, lock_key: int) -> Iterator[None]:
      acquired = session.scalar(
          text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
      )
      if acquired is not True:
          raise PipelineAlreadyRunning("another VBPL pipeline run holds the lock")
      try:
          yield
      finally:
          session.execute(
              text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
          )
  ```

- [ ] **Step 5: Define the complete initial migration**

  Use UUID primary keys for observations/runs and string canonical identifiers
  for instruments, versions, nodes, relations, and releases. Add database
  constraints for:

  - unique `instruments.official_source_id`;
  - unique `(instrument_id, detail_payload_hash, normalized_content_hash)`;
  - legal node type in `part/chapter/article/clause/point`;
  - unique `(version_id, materialized_path)` and
    `(version_id, parent_node_id, node_type, normalized_coordinate)`;
  - parse state in
    `verified_structured/verified_text/heuristic/unparsed`;
  - immutable evidence hash primary key;
  - applicability scope target exactly one instrument version and optional node;
  - relation source/target foreign keys and unique logical edge identity;
  - release state in
    `candidate/promoted/connector_applied/accepted/blocked`;
  - unique `(release_id, corpus_view)` and
    `(release_id, connector_name)`;
  - corpus view in `current/history/evidence`.

  Store raw metadata and validation reports in PostgreSQL `JSONB`; store raw
  payload bytes only in the evidence volume.

- [ ] **Step 6: Add the minimal migration-test Compose boundary**

  Replace the SQLite pipeline command with the initial `vbpl-db`,
  `vbpl-migrate`, and profile-gated `vbpl-test` services. At this stage it is
  sufficient for the database to be healthy, the migration to complete, and
  the test container to receive an isolated test database URL. Task 9 adds the
  complete production volumes, networks, pipeline, scheduler, and backup
  contracts.

- [ ] **Step 7: Run unit and Docker-backed migration tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_db.py -q
  docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test `
    uv run pytest tests/integration/test_postgres_migrations.py -q -m postgres
  ```

  Expected: the unit contract and empty-database migration pass twice.

- [ ] **Step 8: Commit**

  ```powershell
  git add pyproject.toml uv.lock src/vbpl_kb/config.py src/vbpl_kb/db.py `
    src/vbpl_kb/db_models.py alembic.ini migrations tests/test_db.py `
    tests/integration/test_postgres_migrations.py docker-compose.vbpl.yml `
    docker/Dockerfile.pipeline .env.example
  git commit -m "feat: establish canonical VBPL PostgreSQL schema"
  ```

### Task 2: Retain content-addressed official evidence and complete catalog scans

**Files:**
- Create: `src/vbpl_kb/evidence.py`
- Create: `src/vbpl_kb/repositories.py`
- Modify: `src/vbpl_kb/catalog.py`
- Modify: `src/vbpl_kb/vbpl_client.py`
- Modify: `src/vbpl_kb/crawl.py`
- Modify: `src/vbpl_kb/models.py`
- Create: `tests/test_evidence.py`
- Modify: `tests/test_catalog.py`
- Modify: `tests/test_crawl.py`
- Modify: `tests/test_vbpl_client.py`

**Interfaces:**

- Produces `EvidenceObject(hash_sha256, media_type, official_url, endpoint, acquired_at, corpus_revision, size_bytes)`.
- Produces `EvidenceStore.put(content: bytes, *, media_type: str, official_url: str, endpoint: str, corpus_revision: str) -> EvidenceObject`.
- Produces `EvidenceStore.open(hash_sha256: str) -> BinaryIO`.
- Produces `CatalogRepository.begin_scan(run_id: UUID) -> UUID`.
- Produces `CatalogRepository.complete_scan(scan_id: UUID, entries: Sequence[CatalogEntry]) -> CatalogChangeSet`.
- Produces `CatalogRepository.fail_scan(scan_id: UUID, reason: str) -> None`.
- `DailyCrawler.run(revision: str) -> CrawlSummary` writes evidence and returns deterministic upsert/removal candidates without creating projections.

- [ ] **Step 1: Write failing evidence-store tests**

  Cover identical bytes deduplicating to one
  `/app/data/evidence/sha256/<first-two>/<sha256>` object, atomic temporary-file
  replacement, checksum verification on read, immutable content, and safe
  rejection of malformed hashes/path traversal.

- [ ] **Step 2: Write failing catalog/crawl transaction tests**

  Assert:

  - all catalog-page response bytes and every detail/canonical-page response are
    retained before derived rows reference them;
  - the catalog baseline advances only after the final page and all required
    changed-detail requests succeed;
  - unchanged fingerprints skip detail acquisition;
  - the first complete absence creates a removal candidate;
  - the second consecutive complete absence creates a tombstone;
  - a partial scan does not increment absence counts;
  - reappearance clears the removal candidate;
  - a database failure after evidence storage leaves an unreferenced but valid
    object, never a dangling database reference.

- [ ] **Step 3: Run the focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_evidence.py tests/test_catalog.py `
    tests/test_crawl.py tests/test_vbpl_client.py -q
  ```

  Expected: failures because the current crawler writes run-scoped files and
  SQLite rows.

- [ ] **Step 4: Implement content-addressed evidence**

  Hash the exact received bytes with SHA-256, write under a temporary name in
  the target directory, `fsync`, atomically replace only when the final object
  does not exist, and persist the evidence metadata plus dependency record in
  one database transaction. Do not include credentials or request headers in
  evidence metadata.

- [ ] **Step 5: Port catalog fingerprinting and two-scan removal state**

  Keep deterministic fingerprints over index-relevant official metadata. Port
  the behavior from SQLite to `CatalogRepository`, but use explicit scan states
  `running/complete/failed`. `complete_scan()` must lock the previous complete
  baseline rows, compare all IDs, and update absence counters in the same
  transaction.

- [ ] **Step 6: Refactor acquisition to the repository interfaces**

  `VBPLClient` returns response bytes plus parsed payload, allowing the crawler
  to retain exact evidence before normalization. The crawler must not receive a
  filesystem database path. Construct it as:

  ```python
  DailyCrawler(
      client: VBPLClient,
      catalog: CatalogRepository,
      evidence: EvidenceStore,
      progress: ProgressReporter | None = None,
  )
  ```

  Preserve the official canonical-page fallback and its verified provenance.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_evidence.py tests/test_catalog.py `
    tests/test_crawl.py tests/test_vbpl_client.py -q
  ```

  Expected: evidence deduplication, complete-scan barrier, incremental detail
  fetching, and two-scan tombstones all pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/evidence.py src/vbpl_kb/repositories.py `
    src/vbpl_kb/catalog.py src/vbpl_kb/vbpl_client.py src/vbpl_kb/crawl.py `
    src/vbpl_kb/models.py tests/test_evidence.py tests/test_catalog.py `
    tests/test_crawl.py tests/test_vbpl_client.py
  git commit -m "feat: retain official evidence and catalog scans"
  ```

### Task 3: Build immutable instrument versions and the ordered legal tree

**Files:**
- Create: `src/vbpl_kb/legal_tree.py`
- Create: `src/vbpl_kb/canonicalize.py`
- Modify: `src/vbpl_kb/models.py`
- Modify: `src/vbpl_kb/repositories.py`
- Create: `tests/fixtures/vbpl/structured-document.json`
- Create: `tests/fixtures/vbpl/structured-document.html`
- Create: `tests/test_canonicalize.py`
- Replace: `tests/test_provisions.py`
- Modify: `tests/test_normalize.py`

**Interfaces:**

- Produces `NodeType = Literal["part", "chapter", "article", "clause", "point"]`.
- Produces `ParseStatus = Literal["verified_structured", "verified_text", "heuristic", "unparsed"]`.
- Produces `LegalNodeDraft(node_type, display_label, normalized_coordinate, heading, sibling_ordinal, materialized_path, text, lead_in_text, source_anchor, source_start, source_end, content_hash, parse_status)`.
- Produces `parse_legal_tree(detail: Mapping[str, Any], evidence: bytes) -> tuple[LegalNodeDraft, ...]`.
- Produces `canonicalize_instrument(detail: Mapping[str, Any], observation: SourceObservation) -> CanonicalInstrumentDraft`.
- Produces `CanonicalRepository.upsert_observation(draft: CanonicalInstrumentDraft, nodes: Sequence[LegalNodeDraft]) -> InstrumentVersionResult`.

- [ ] **Step 1: Write failing structured-tree tests**

  Use a fixture containing Part, Chapter, Article, Clause, and Point nodes,
  Article/Clause lead-ins, Vietnamese labels, amended quoted text, and a
  substantive Chapter heading. Assert deterministic ordered paths such as:

  ```text
  phan-02/chuong-03/dieu-12/khoan-02/diem-a
  ```

  Assert parent links, sibling ordinals, exact text, source anchors/offsets,
  content hashes, and `verified_structured` when the official payload/HTML
  exposes structure.

- [ ] **Step 2: Write failing fallback and invariant tests**

  Cover:

  - regex fallback marked `verified_text` only when every node maps exactly to
    retained source offsets;
  - ambiguous regex output marked `heuristic`;
  - unsplittable content represented by one `unparsed` Article-like discovery
    node, not falsely cited as an exact provision;
  - no cycles, orphan nodes, duplicate sibling coordinates, unstable ordering,
    or text without an evidence anchor;
  - a changed normalized content hash creates a new immutable version;
  - the same detail and normalized hashes reuse the existing version;
  - an old version and its nodes are never updated in place.

- [ ] **Step 3: Run the focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_canonicalize.py tests/test_provisions.py `
    tests/test_normalize.py -q
  ```

  Expected: current `split_provisions()` cannot represent Part/Chapter nodes,
  parents, immutable versions, or source anchors.

- [ ] **Step 4: Implement stable canonical identities**

  Use:

  ```python
  instrument_id = f"vbpl:{official_source_id}"
  version_id = "ver:" + sha256(
      f"{instrument_id}\0{detail_payload_hash}\0{normalized_content_hash}".encode()
  ).hexdigest()
  node_id = "node:" + sha256(
      f"{version_id}\0{node_type}\0{materialized_path}".encode()
  ).hexdigest()
  ```

  Normalize coordinates without mutable heading/text. Preserve the displayed
  label separately.

- [ ] **Step 5: Implement official-structure-first parsing**

  Parse structured payload nodes or retained HTML anchors first. Use a stack
  keyed by legal level to assign parents and ordinals. Run the regex parser only
  when official structure is absent. Validate the complete tree before any node
  is persisted.

- [ ] **Step 6: Persist one immutable version transaction**

  Upsert stable instrument identity and latest-observation timestamps, insert a
  new immutable version only for a new content state, bulk-insert validated
  nodes, and record every evidence dependency. Never mutate old version/node
  content.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_canonicalize.py tests/test_provisions.py `
    tests/test_normalize.py -q
  ```

  Expected: tree, version identity, source traceability, and fallback safety
  tests pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/legal_tree.py src/vbpl_kb/canonicalize.py `
    src/vbpl_kb/models.py src/vbpl_kb/repositories.py `
    tests/fixtures/vbpl/structured-document.json `
    tests/fixtures/vbpl/structured-document.html tests/test_canonicalize.py `
    tests/test_provisions.py tests/test_normalize.py
  git commit -m "feat: build immutable VBPL legal trees"
  ```

### Task 4: Model authority, applicability, status, and verified relations

**Files:**
- Modify: `src/vbpl_kb/authority.py`
- Modify: `src/vbpl_kb/applicability.py`
- Modify: `src/vbpl_kb/references.py`
- Create: `src/vbpl_kb/legal_semantics.py`
- Modify: `src/vbpl_kb/models.py`
- Modify: `src/vbpl_kb/repositories.py`
- Create: `src/vbpl_kb/data/authority-regimes/2025-07-01.json`
- Modify: `tests/test_authority.py`
- Modify: `tests/test_applicability.py`
- Modify: `tests/test_references.py`
- Create: `tests/test_legal_semantics.py`

**Interfaces:**

- Produces `classify_authority(version: InstrumentVersion, regime: AuthorityRegime) -> AuthorityClassification`.
- Produces `build_applicability(version: InstrumentVersion, status: StatusObservation, overrides: Sequence[ProvisionApplicability]) -> tuple[ApplicabilityEnvelope, ...]`.
- Produces `resolve_relations(version: InstrumentVersion, nodes: Sequence[LegalNode], evidence: Sequence[EvidenceReference], instrument_index: InstrumentIndex) -> tuple[LegalRelation, ...]`.
- Produces `is_current_eligible(envelope: ApplicabilityEnvelope, *, now: datetime, freshness: timedelta) -> EligibilityDecision`.
- Repository writes classifications, envelopes, observations, and relations in the same corpus revision without inference by the projector.

- [ ] **Step 1: Write failing authority-regime tests**

  Check in the 2025-07-01 regime with all 15 statutory authority groups and the
  documented legacy-district transition. Test issuer-sensitive Resolution,
  Decision, and Circular classifications. Assert zero-padded order strings,
  explicit `unknown` outside covered intervals, and no retroactive use of the
  2025 regime.

- [ ] **Step 2: Write failing applicability/status tests**

  Cover fresh in-force, not-yet-effective, suspended, expired, repealed,
  conflicting, missing, and stale observations; national/province/commune/
  special-zone/legacy-district scopes; subject tokens; transitions; and partial
  effect with and without provision-level official evidence.

- [ ] **Step 3: Write failing relationship tests**

  Cover ordinary citations, legal basis, detail, implementation, delegation,
  amendment, supplementation, replacement, repeal, suspension, and continued
  effect. Assert:

  - legal-effect edges require explicit official structured/page evidence;
  - text candidates remain unresolved and not searchable as legal effect;
  - target version/provision may remain null;
  - duplicate edges collapse by logical edge identity;
  - heuristic self-references are excluded;
  - forward and reverse tokens are deterministic;
  - effective intervals create distinct historical states.

- [ ] **Step 4: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_authority.py tests/test_applicability.py `
    tests/test_references.py tests/test_legal_semantics.py -q
  ```

  Expected: current helpers lack persisted regimes, provision overrides, full
  temporal rules, and versioned relation targets.

- [ ] **Step 5: Implement checked-in authority regimes**

  Load and validate the JSON at startup; hash its canonical JSON to produce
  `classification_version`. Require form plus issuer where the regime makes the
  issuer material. Store unknown/unclassified results rather than guessing.

- [ ] **Step 6: Implement fail-closed current eligibility**

  Return a decision with `eligible: bool` and machine-readable exclusion reasons
  such as `stale_status`, `unknown_status`, `outside_time`,
  `outside_jurisdiction`, `partial_effect_without_provision_evidence`, and
  `heuristic_structure`. The Current projector consumes only this decision.

- [ ] **Step 7: Implement evidence-backed relation promotion**

  Store the source quote, payload pointer, offset, evidence hash, resolution
  state, confidence, direction, and effective interval. Ordinary citation is a
  separate relation type and must not emit amendment/repeal traversal tokens.

- [ ] **Step 8: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_authority.py tests/test_applicability.py `
    tests/test_references.py tests/test_legal_semantics.py -q
  ```

  Expected: authority, eligibility, and verified relation contracts pass.

- [ ] **Step 9: Commit**

  ```powershell
  git add src/vbpl_kb/authority.py src/vbpl_kb/applicability.py `
    src/vbpl_kb/references.py src/vbpl_kb/legal_semantics.py `
    src/vbpl_kb/models.py src/vbpl_kb/repositories.py `
    src/vbpl_kb/data/authority-regimes/2025-07-01.json `
    tests/test_authority.py tests/test_applicability.py `
    tests/test_references.py tests/test_legal_semantics.py
  git commit -m "feat: model verified VBPL legal semantics"
  ```

### Task 5: Project one-section Current, History, and Evidence documents

**Files:**
- Create: `src/vbpl_kb/projection.py`
- Create: `src/vbpl_kb/projection_ids.py`
- Modify: `src/vbpl_kb/models.py`
- Create: `tests/test_projection_ids.py`
- Create: `tests/test_projection.py`
- Modify: `tests/test_normalize.py`

**Interfaces:**

- Produces `CorpusView = Literal["current", "history", "evidence"]`.
- Produces `ProjectionKind = Literal["article", "atomic", "relation", "evidence"]`.
- Produces `project_current(bundle: CanonicalBundle, now: datetime) -> Iterator[OnyxDocument]`.
- Produces `project_history(bundle: CanonicalBundle) -> Iterator[OnyxDocument]`.
- Produces `project_evidence(bundle: CanonicalBundle) -> Iterator[OnyxDocument]`.
- Each `OnyxDocument.sections` has length one and metadata values are only `str` or `list[str]`.

- [ ] **Step 1: Write failing identity tests**

  Assert exact namespace formats:

  ```text
  vbpl:<id>:current:article:<logical-path-hash>
  vbpl:<id>:current:atomic:<logical-path-hash>
  vbpl:<id>:current:relation:<logical-edge-hash>
  vbpl:<id>:history:<version-hash>:article:<logical-path-hash>
  vbpl:<id>:history:<version-hash>:atomic:<logical-path-hash>
  vbpl:<id>:history:<version-hash>:relation:<logical-edge-hash>
  vbpl:<id>:evidence:<evidence-kind>:<evidence-hash>
  ```

  Changing text, status evidence, or headings must not change a Current logical
  path/edge ID. Renumbering/moving a provision must change it. History IDs must
  differ between immutable versions. No IDs may collide across views.

- [ ] **Step 2: Write failing Article/Atomic projection tests**

  Assert:

  - one Article Context document per Article with breadcrumbs, Article heading,
    complete ordered descendants, one compact header, and one section;
  - Atomic leaves are Point when Points exist, otherwise Clause, otherwise
    Article;
  - Atomic text includes only material ancestor lead-ins and never siblings or
    the complete Article;
  - Part/Chapter nodes become breadcrumbs unless they carry independent
    substantive text;
  - heuristic/unparsed nodes do not enter exact-current projection;
  - every applicable document includes instrument, provision, corpus view,
    revision, authority, issuer, status, verification time, effective interval,
    jurisdiction, parse status, official URL, and verified relation tokens.

- [ ] **Step 3: Write failing Relation/Evidence projection tests**

  Require one verified edge per Relation document, searchable forward/reverse
  tokens, current/history relevance, and no promotion of ordinary citations to
  legal effect. Evidence documents must contain compact proof, reason,
  timestamps, hashes, and URLs but never raw payload bodies. Current must emit
  no Evidence document.

- [ ] **Step 4: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_projection_ids.py tests/test_projection.py `
    tests/test_normalize.py -q
  ```

  Expected: the existing one-document-per-instrument normalizer emits multiple
  sections and has no view/kind namespace.

- [ ] **Step 5: Implement compact embedded context**

  Render a bounded text header, not only metadata:

  ```text
  Văn bản: <title> | Số: <number>
  Hình thức/Cơ quan: <form> | <issuer>
  Thẩm quyền: <regime> | <zero-padded-group>
  Vị trí: <full legal breadcrumb>
  Trạng thái/Xác minh: <status> | <UTC timestamp>
  Hiệu lực/Phạm vi: <from..to> | <jurisdiction>
  Quan hệ đã xác minh: <short tokens>
  ```

  Keep short scalar/list metadata. Add a unit guard that rejects metadata whose
  serialized token estimate consumes 25 percent or more of the stock 512-token
  budget.

- [ ] **Step 6: Implement duplicate-control rules**

  Atomic projection is leaf-only; Article carries only one header; no sibling
  text enters Atomic documents; both kinds share
  `logical_provision_id` for downstream grouping. Relation documents use their
  logical edge ID, not the source provision ID.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_projection_ids.py tests/test_projection.py `
    tests/test_normalize.py -q
  ```

  Expected: all view, identity, one-section, boundary, eligibility, metadata,
  and duplicate-control tests pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/projection.py src/vbpl_kb/projection_ids.py `
    src/vbpl_kb/models.py tests/test_projection_ids.py `
    tests/test_projection.py tests/test_normalize.py
  git commit -m "feat: project multi-resolution VBPL views"
  ```

### Task 6: Write immutable sharded releases and explicit readiness state

**Files:**
- Replace: `src/vbpl_kb/releases.py`
- Modify: `src/vbpl_kb/repositories.py`
- Modify: `src/vbpl_kb/models.py`
- Replace: `tests/test_releases.py`
- Replace: `tests/test_release_deployment.py`
- Create: `tests/test_release_streaming.py`

**Interfaces:**

- Produces `ReleaseBuilder.build_candidate(revision: str) -> ReleaseManifest`.
- Produces `ReleaseValidator.validate(manifest: ReleaseManifest) -> ValidationReport`.
- Produces `ReleaseManager.promote(manifest: ReleaseManifest) -> ActiveRelease`.
- Produces `ReleaseRepository.mark_connector_applied(release_id: str, corpus_view: CorpusView, connector_id: int, attempt_id: int) -> None`.
- Produces `ReleaseRepository.mark_accepted(release_id: str, agent_profile: str, report_hash: str) -> None`.
- Release layout:

  ```text
  releases/<release-id>/
    manifest.json
    current/documents-00000.jsonl
    current/active-ids.jsonl
    current/delta-00000.jsonl
    history/documents-00000.jsonl
    history/active-ids.jsonl
    history/delta-00000.jsonl
    evidence/documents-00000.jsonl
    evidence/active-ids.jsonl
    evidence/delta-00000.jsonl
    validation.json
  active-release.json
  ```

- [ ] **Step 1: Write failing shard/streaming tests**

  With a generator that raises if materialized, assert bounded-memory JSONL
  writing and configurable shard limits by record count and bytes. Validate
  stable record order, UTF-8 canonical JSON, per-shard hash/count/byte totals,
  per-view active IDs, and no millions of per-document files.

- [ ] **Step 2: Write failing release-state and delta tests**

  Cover:

  - Current, History, and Evidence full shards share one corpus revision;
  - active ID manifests and delta upsert/tombstone IDs are view-specific;
  - a Current path moving to History emits Current tombstone plus History
    upsert;
  - unsupported projection versions, duplicate global IDs, cross-view IDs,
    checksum mismatch, stale status, invalid authority/relations, or coverage
    failure block promotion;
  - failed validation leaves `active-release.json` unchanged;
  - promotion uses one atomic pointer replacement;
  - source promotion does not imply connector-applied or accepted;
  - Current readiness requires Current applied plus Current acceptance;
  - Historical readiness requires Current and History at the same revision;
  - Evidence readiness requires Evidence applied and Evidence acceptance.

- [ ] **Step 3: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_releases.py tests/test_release_deployment.py `
    tests/test_release_streaming.py -q
  ```

  Expected: the current release writes one JSON file per instrument, one
  manifest, and conflates active/delivered state.

- [ ] **Step 4: Implement sharded projection streaming**

  Query canonical bundles with server-side/yield-per iteration, project one
  instrument/version at a time, and feed independent view shard writers.
  Calculate hashes while streaming. Never call `list()` on the complete corpus
  or active-ID stream.

- [ ] **Step 5: Implement validation and atomic promotion**

  Validate schema, checksums, ID namespaces, one-section invariant, metadata
  types/budget, coverage, evidence dependencies, freshness, tree status,
  classifications, relations, and view transition deltas. Write
  `validation.json`, then atomically replace `active-release.json` only for a
  passing report.

- [ ] **Step 6: Implement four distinct lifecycle states**

  Store `candidate`, `promoted`, per-view connector-applied attempts, per-Agent
  accepted reports, and blocked reasons. A readiness query must return both
  `ready: bool` and the exact missing/failed gate list.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_releases.py tests/test_release_deployment.py `
    tests/test_release_streaming.py -q
  ```

  Expected: immutable streaming releases, view deltas, validation, promotion,
  and readiness state pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/releases.py src/vbpl_kb/repositories.py `
    src/vbpl_kb/models.py tests/test_releases.py `
    tests/test_release_deployment.py tests/test_release_streaming.py
  git commit -m "feat: publish sharded multi-view VBPL releases"
  ```

### Task 7: Make the connector stream exactly one configured corpus view

**Files:**
- Replace: `infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py`
- Modify: `infra/onyx/patches/vbpl-export-connector.patch`
- Modify: `infra/onyx/overlay/web/src/lib/connectors/credentials.ts`
- Modify: `infra/onyx/overlay/web/src/lib/sources.ts`
- Modify: `infra/onyx/overlay/web/src/lib/types.ts`
- Replace: `tests/test_vbpl_export_connector.py`
- Modify: `tests/test_onyx_deployment.py`

**Interfaces:**

- Connector constructor remains compatible with stock Onyx.
- `load_credentials(credentials: dict[str, Any]) -> dict[str, Any] | None`.
- `load_from_state() -> Generator[list[Document], None, None]`.
- `poll_source(start: float, end: float) -> Generator[list[Document], None, None]`.
- `retrieve_all_slim_documents() -> Generator[list[SlimDocument], None, None]`.
- Required connector configuration:

  ```json
  {
    "corpus_view": "current",
    "export_root": "/app/vbpl-export"
  }
  ```

- [ ] **Step 1: Write failing three-configuration tests**

  Instantiate Current, History, and Evidence connectors against one fixture
  release. Assert each streams only its configured view, returns only that
  view's active IDs, and refuses absent/unknown `corpus_view`.

- [ ] **Step 2: Write failing streaming/checksum/delta tests**

  Assert:

  - JSONL shards are read line-by-line and batches never exceed
    `INDEX_BATCH_SIZE`;
  - all manifest and shard checksums are validated before emitting a partial
    stream;
  - each raw document has exactly one section;
  - metadata values are only strings/lists of strings;
  - `poll_source()` selects all view deltas in `(start, end]`, not merely the
    latest file;
  - repeated polling is idempotent;
  - a History tombstone cannot prune a Current ID;
  - IDs are globally unique across all fixture views;
  - incompatible projection schema fails closed.

- [ ] **Step 3: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_vbpl_export_connector.py `
    tests/test_onyx_deployment.py -q
  ```

  Expected: the current connector reads one per-document manifest and has no
  `corpus_view`.

- [ ] **Step 4: Implement manifest-first validated streaming**

  Read the active pointer and manifest, select one view, verify every selected
  shard hash, then stream JSONL records in batches. Convert exactly one section
  to one `TextSection`; set source to `DocumentSource.VBPL_EXPORT`; preserve the
  document ID and sanitized metadata unchanged.

- [ ] **Step 5: Implement view-scoped polling and SlimConnector pruning**

  Filter delta entries by connector view and poll interval. Enumerate the
  selected view's `active-ids.jsonl`. Never enumerate another view as a pruning
  baseline.

- [ ] **Step 6: Register the required view in the overlay UI**

  Present a required select with `current`, `history`, and `evidence`. Preserve
  source type `vbpl_export`. Regenerate/update the checked-in patch from the
  overlay without adding retrieval/indexing changes.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_vbpl_export_connector.py `
    tests/test_onyx_deployment.py -q
  ```

  Expected: view isolation, streaming, polling, pruning, and overlay-boundary
  tests pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add infra/onyx/overlay/backend/onyx/connectors/vbpl_export/connector.py `
    infra/onyx/patches/vbpl-export-connector.patch `
    infra/onyx/overlay/web/src/lib/connectors/credentials.ts `
    infra/onyx/overlay/web/src/lib/sources.ts `
    infra/onyx/overlay/web/src/lib/types.ts `
    tests/test_vbpl_export_connector.py tests/test_onyx_deployment.py
  git commit -m "feat: isolate VBPL connector corpus views"
  ```

### Task 8: Orchestrate the clean pipeline and three Onyx connector configurations

**Files:**
- Replace: `src/vbpl_kb/connector_control.py`
- Replace: `src/vbpl_kb/cli.py`
- Create: `src/vbpl_kb/pipeline.py`
- Create: `src/vbpl_kb/readiness.py`
- Modify: `src/vbpl_kb/config.py`
- Replace: `tests/test_connector_control.py`
- Replace: `tests/test_cli.py`
- Create: `tests/test_pipeline.py`
- Create: `tests/test_readiness.py`

**Interfaces:**

- `Pipeline.run_daily(revision: str) -> PipelineResult`.
- `OnyxConnectorClient.ensure_topology(specs: Sequence[ConnectorSpec]) -> ConnectorTopology`.
- `OnyxConnectorClient.trigger(connector_id: int, *, from_beginning: bool) -> int`.
- `OnyxConnectorClient.wait_for_indexed(connector_id: int, attempt_id: int, timeout_seconds: float) -> ConnectorStatus`.
- `ReadinessService.get_agent_readiness(agent_profile: AgentProfile, release_id: str) -> ReadinessResult`.
- Three settings groups: Current, History, Evidence connector IDs, document set names, and Agent/persona IDs.

- [ ] **Step 1: Write failing pipeline transaction tests**

  Verify this exact order:

  1. acquire PostgreSQL advisory lock;
  2. retry promoted but unapplied view deltas;
  3. run complete catalog/detail acquisition;
  4. canonicalize changed versions and legal semantics;
  5. build and validate the candidate;
  6. promote source release;
  7. trigger only views with delta work;
  8. wait for the exact indexing attempt;
  9. record connector-applied per view;
  10. leave acceptance/readiness for the direct acceptance step.

  Assert fail-closed behavior at every boundary and idempotent retry after
  restart.

- [ ] **Step 2: Write failing connector topology tests**

  Mock supported Onyx administration endpoints and require:

  | Name | `corpus_view` | Document set |
  | --- | --- | --- |
  | `VBPL Current` | `current` | `VBPL-current` |
  | `VBPL History` | `history` | `VBPL-history` |
  | `VBPL Evidence` | `evidence` | `VBPL-evidence` |

  Assert three connector IDs may share one source type and physical search
  setting, document set membership is exact, and no two configurations emit the
  same document ID.

- [ ] **Step 3: Write failing readiness tests**

  Assert Current, Historical, and Evidence readiness rules from the approved
  design, including same-revision Current+History and an explicit refusal when
  current status freshness exceeds 24 hours.

- [ ] **Step 4: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_connector_control.py tests/test_cli.py `
    tests/test_pipeline.py tests/test_readiness.py -q
  ```

  Expected: current CLI uses SQLite, one connector setting, and active-release
  state as a proxy for delivery.

- [ ] **Step 5: Implement typed connector topology control**

  `ensure_topology()` may create/update only named `vbpl_export` connectors and
  named VBPL document sets. It must inspect existing objects first, reject a
  name owned by another source, attach the correct credential pair, and return
  stable IDs without deleting anything.

- [ ] **Step 6: Implement the pipeline service**

  Keep CLI commands thin:

  ```text
  vbpl-kb migrate
  vbpl-kb crawl --revision <id>
  vbpl-kb build-release --revision <id>
  vbpl-kb validate-release --revision <id>
  vbpl-kb promote-release --revision <id>
  vbpl-kb setup-onyx-topology
  vbpl-kb apply-release --revision <id> [--from-beginning]
  vbpl-kb run-daily [--revision <id>]
  vbpl-kb readiness --agent current|historical|evidence
  ```

  Remove `--db-path`. Do not invoke the diagnostic direct-ingestion client.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_connector_control.py tests/test_cli.py `
    tests/test_pipeline.py tests/test_readiness.py -q
  ```

  Expected: orchestration, idempotent delivery, exact attempt tracking,
  topology, and readiness tests pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/connector_control.py src/vbpl_kb/cli.py `
    src/vbpl_kb/pipeline.py src/vbpl_kb/readiness.py `
    src/vbpl_kb/config.py tests/test_connector_control.py tests/test_cli.py `
    tests/test_pipeline.py tests/test_readiness.py
  git commit -m "feat: orchestrate multi-view VBPL delivery"
  ```

### Task 9: Make Docker Compose the canonical runtime

**Files:**
- Replace: `docker-compose.vbpl.yml`
- Modify: `docker/Dockerfile.pipeline`
- Create: `docker/entrypoint.sh`
- Create: `docker/backup.sh`
- Modify: `infra/onyx/docker-compose.vbpl-connector.yml`
- Modify: `.env.example`
- Modify: `tests/test_deployment_files.py`
- Modify: `tests/test_onyx_deployment.py`
- Create: `tests/integration/test_compose_pipeline.py`

**Interfaces:**

- Compose services: `vbpl-db`, `vbpl-migrate`, `vbpl-pipeline`,
  `vbpl-scheduler`, `vbpl-backup`, and `vbpl-test`.
- Named volumes: `vbpl-postgres-data`, `vbpl-evidence-data`,
  `vbpl-export-data`, and `vbpl-backup-data`.
- Networks: `vbpl-data-internal` and external `vbpl-onyx-bridge`.
- Onyx background mounts `vbpl-export-data:/app/vbpl-export:ro`.

- [ ] **Step 1: Write failing Compose contract tests**

  Parse resolved Compose with secrets replaced by test values and assert:

  - PostgreSQL has a health check and no host port;
  - migrate waits for healthy PostgreSQL;
  - pipeline waits for successful migration;
  - scheduler is profile-gated and uses the same image/volumes;
  - backup is manual-profile-only and writes only to backup volume;
  - test has an isolated database/schema and exits with pytest status;
  - data-internal does not connect Onyx;
  - only pipeline/scheduler join the Onyx bridge;
  - evidence/export/database volumes persist;
  - Onyx mounts export read-only;
  - no secret value appears in resolved command or checked-in files.

- [ ] **Step 2: Run deployment tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_deployment_files.py `
    tests/test_onyx_deployment.py -q
  ```

  Expected: the minimal migration-test Compose lacks the final production
  pipeline, scheduler, backup, network isolation, and shared export-volume
  contract.

- [ ] **Step 3: Implement the data-stack Compose**

  Use `postgres:17-bookworm`; put credentials in environment interpolation or
  Docker secrets; configure `pg_isready`; mount evidence and export at
  `/app/data/evidence` and `/app/data/exports`; and use a one-shot migrate
  service that runs `alembic upgrade head`.

  The scheduler invokes `vbpl-kb run-daily` at the configured UTC schedule and
  relies on the advisory lock for overlap protection. The backup profile runs
  `pg_dump --format=custom` to the backup volume without exposing the database
  port.

- [ ] **Step 4: Update the Onyx export mount**

  Use the same external named `vbpl-export-data` volume in the Onyx overlay.
  Do not mount evidence or expose canonical PostgreSQL to Onyx.

- [ ] **Step 5: Run Docker-backed integration**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_deployment_files.py `
    tests/test_onyx_deployment.py -q
  docker compose -f docker-compose.vbpl.yml --profile test build `
    vbpl-migrate vbpl-test
  docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test `
    uv run pytest tests/integration/test_postgres_migrations.py `
    tests/integration/test_compose_pipeline.py -q -m postgres
  ```

  Expected: fresh database migration, advisory lock exclusion, restart-safe
  persistence, evidence/export volume writes, and test-service exit propagation
  pass.

- [ ] **Step 6: Commit**

  ```powershell
  git add docker-compose.vbpl.yml docker/Dockerfile.pipeline `
    docker/entrypoint.sh docker/backup.sh `
    infra/onyx/docker-compose.vbpl-connector.yml .env.example `
    tests/test_deployment_files.py tests/test_onyx_deployment.py `
    tests/integration/test_compose_pipeline.py
  git commit -m "feat: deploy VBPL data stack with Docker"
  ```

### Task 10: Enforce scoped Internal Search acceptance and legal retrieval metrics

**Files:**
- Replace: `src/vbpl_kb/acceptance.py`
- Replace: `src/vbpl_kb/evaluate.py`
- Modify: `src/vbpl_kb/onyx_chat.py`
- Modify: `src/vbpl_kb/cli.py`
- Create: `benchmarks/multiresolution-current.json`
- Create: `benchmarks/multiresolution-historical.json`
- Create: `benchmarks/multiresolution-evidence.json`
- Replace: `tests/test_acceptance.py`
- Replace: `tests/test_evaluate.py`
- Modify: `tests/test_onyx_chat.py`
- Modify: `tests/test_onyx.py`

**Interfaces:**

- `run_acceptance(cases, chat, context) -> AcceptanceReport`.
- `evaluate_acceptance(report: AcceptanceReport) -> LegalSearchMetrics`.
- Context records Agent, model, prompt hash, release/schema, connector
  deliveries, document sets, search settings, and timestamp.
- Every `RetrievedChunk` records `document_id`, rank, chunk index, metadata,
  source type, link, and document sets.

- [ ] **Step 1: Write failing source/document-set tests**

  Fail a case when:

  - there is no `internal_search` tool call;
  - `search_docs` is empty;
  - any evidence comes from Web Search, MCP, model-only knowledge, or a source
    other than `vbpl_export`;
  - Current retrieves `VBPL-history` or `VBPL-evidence`;
  - Historical retrieves Evidence;
  - a returned projection ID/view disagrees with its document set;
  - a substantive answer citation lacks instrument, provision, issuer, status,
    effective time, verification timestamp, or official URL.

- [ ] **Step 2: Write failing hard-gate metric tests**

  Implement fixtures at pass/fail boundaries for:

  ```text
  unsafe current-law conclusions = 0
  Current History/Evidence leakage = 0
  non-internal/non-vbpl evidence = 0
  exact Atomic rank <= 5
  controlling-provision recall@10 >= 0.95
  authority-bundle completeness@10 >= 0.90
  evidence-resolved conflict accuracy = 1.00
  unresolved labeling accuracy = 1.00
  duplicate logical-provision hits in top 10 <= 2
  complete citations = 1.00
  ```

  Remove the superseded 1.25-times chunk-ratio gate.

- [ ] **Step 3: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_acceptance.py tests/test_evaluate.py `
    tests/test_onyx_chat.py tests/test_onyx.py -q
  ```

  Expected: existing acceptance lacks document-set/view rules, complete
  citations, duplicate control, and readiness persistence.

- [ ] **Step 4: Implement three benchmark schemas**

  Cover exact coordinates, topic search, implementing details, authority
  conflict, same-authority later instruments, partial effect, geographic
  mismatch, district transition, historical dates, amendments, replacement,
  repeal, continuation, ordinary citations, follow-up context, and evidence
  audit. Each case must name expected projection kind, view, logical provision,
  authority bundle, and safe outcome.

- [ ] **Step 5: Implement acceptance recording and persistence**

  Record the authenticated ordinary Onyx Chat response, every tool call,
  `search_docs`, retrieved rank/chunk/metadata/document sets, answer/citations,
  and failure findings. Hash the JSON report and write its accepted/blocked
  state to `acceptance_runs`. Never mark readiness from an admin search endpoint
  or LLM-only response.

- [ ] **Step 6: Add controlled search configuration evaluation**

  Run the same release, benchmark, reranker, Agent prompt, and model at
  `HYBRID_ALPHA` 0.3, 0.5, and 0.7 with `DOC_TIME_DECAY=0`,
  `MAX_CHUNKS_FED_TO_CHAT=25`, and `MAX_LLM_CYCLES=8`. Record results without
  automatically altering Onyx core or globally boosting authority.

- [ ] **Step 7: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_acceptance.py tests/test_evaluate.py `
    tests/test_onyx_chat.py tests/test_onyx.py -q
  ```

  Expected: all source, document-set, metrics, evidence-recording, and benchmark
  contracts pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add src/vbpl_kb/acceptance.py src/vbpl_kb/evaluate.py `
    src/vbpl_kb/onyx_chat.py src/vbpl_kb/cli.py `
    benchmarks/multiresolution-current.json `
    benchmarks/multiresolution-historical.json `
    benchmarks/multiresolution-evidence.json tests/test_acceptance.py `
    tests/test_evaluate.py tests/test_onyx_chat.py tests/test_onyx.py
  git commit -m "feat: enforce scoped VBPL Internal Search acceptance"
  ```

### Task 11: Configure the three legal Agents without changing Onyx core

**Files:**
- Replace: `docs/onyx-agent-instruction.md`
- Replace: `docs/onyx-agent-setup.md`
- Create: `docs/onyx-agent-instruction-historical.md`
- Create: `docs/onyx-agent-instruction-evidence.md`
- Create: `src/vbpl_kb/agent_setup.py`
- Modify: `src/vbpl_kb/cli.py`
- Create: `tests/test_agent_setup.py`
- Modify: `tests/test_documentation.py`

**Interfaces:**

- `OnyxAgentSetup.ensure_agents(topology: ConnectorTopology) -> AgentTopology`.
- Current Agent uses only `VBPL-current`.
- Historical Agent uses only `VBPL-current` and `VBPL-history`.
- Evidence Audit Agent uses `VBPL-evidence`; Current/History are attached only
  through an explicit operator flag.

- [ ] **Step 1: Write failing Agent configuration tests**

  Mock supported Onyx management routes and assert exact document sets,
  forced/available `internal_search`, disabled Web Search/MCP/code/external
  write tools, deterministic prompt hashes, and idempotent updates of only the
  three named VBPL Agents.

- [ ] **Step 2: Write failing prompt-contract tests**

  Require the staged workflow: establish legal coordinates; exact-coordinate
  search when supplied; topic search without invented Article numbers;
  applicability/status gate; bounded relation-token follow-ups; Article plus
  Atomic evidence; authority comparison only for the same issue/scope;
  preservation of necessary subordinate implementation; unresolved conflicts;
  complete citations; and this exact insufficient-evidence response:

  ```text
  Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.
  ```

- [ ] **Step 3: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_agent_setup.py tests/test_documentation.py -q
  ```

  Expected: only one Agent instruction/setup contract exists.

- [ ] **Step 4: Implement idempotent Agent setup**

  Inspect existing Agents by exact name, reject conflicting ownership, create or
  update only the three VBPL profiles, attach exact document sets and the
  configured Internal Search tool, and return IDs plus prompt hashes. Do not
  modify Onyx source.

- [ ] **Step 5: Implement profile-specific prompts**

  Current refuses stale/unsupported current-law claims and never searches
  History/Evidence. Historical establishes a material date and compares
  versions without presenting them as current. Evidence Audit distinguishes
  provenance/decision evidence from legal authority.

- [ ] **Step 6: Re-run focused tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_agent_setup.py tests/test_documentation.py -q
  ```

  Expected: Agent scope, tools, prompts, and idempotent setup pass.

- [ ] **Step 7: Commit**

  ```powershell
  git add docs/onyx-agent-instruction.md docs/onyx-agent-setup.md `
    docs/onyx-agent-instruction-historical.md `
    docs/onyx-agent-instruction-evidence.md `
    src/vbpl_kb/agent_setup.py src/vbpl_kb/cli.py `
    tests/test_agent_setup.py tests/test_documentation.py
  git commit -m "feat: configure scoped VBPL legal agents"
  ```

### Task 12: Remove legacy production paths and update canonical documentation

**Files:**
- Delete: `src/vbpl_kb/state.py`
- Delete: `src/vbpl_kb/publish.py`
- Delete: `src/vbpl_kb/onyx.py`
- Delete: `src/vbpl_kb/provisions.py`
- Delete: `scripts/reset-and-reindex-onyx.py`
- Delete or replace tests that import those legacy production paths
- Modify: `AGENTS.md`
- Modify: `README.md`
- Replace: `docs/architecture.md`
- Replace: `docs/legal-data-policy.md`
- Replace: `docs/development-workflow.md`
- Replace: `docs/operations.md`
- Modify: `TODOS.md`
- Modify: `tests/test_documentation.py`
- Modify: `tests/test_deployment_files.py`

**Interfaces:**

- Current code and docs have one production path: validated PostgreSQL-backed
  multi-view export through persistent connectors.
- Current coding-agent guidance routes by current docs and does not point to
  dated specs/plans.
- Operations distinguish build, source promotion, connector-applied,
  acceptance, readiness, backup/restore, and scoped cutover.

- [ ] **Step 1: Write failing legacy-path/documentation tests**

  Assert:

  - no production import references `StateStore`, `Publisher`,
    `OnyxIngestionClient`, `split_provisions`, SQLite, per-document release
    files, direct ingestion, one connector, or schema-v1/schema-v2 migration;
  - `AGENTS.md` requires PostgreSQL/Alembic, Docker verification, one-section
    multi-view metadata checks, and direct `internal_search` evidence;
  - README and current docs describe the real service/file/command names from
    Tasks 1-11;
  - historical design/plan files are background only;
  - operations contain exact backup, restore-to-new-database, retry, stale
    readiness, and nondestructive incident flows.

- [ ] **Step 2: Run documentation and import tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_documentation.py `
    tests/test_deployment_files.py -q
  rg -n "StateStore|publish-legacy|OnyxIngestionClient|state\.sqlite3" `
    src tests scripts docker-compose.vbpl.yml README.md AGENTS.md docs
  ```

  Expected: legacy code and current documentation references remain.

- [ ] **Step 3: Delete obsolete production paths**

  Remove only code made unreachable by the new pipeline. Move any still-required
  pure helper into its owning new module before deletion. Remove the broad reset
  script; scoped cutover tooling is introduced in Task 14.

- [ ] **Step 4: Rewrite current canonical documentation**

  Document the canonical PostgreSQL schema, evidence volume, parser states,
  authority/applicability/relation rules, projections, release layout,
  connector/document-set/Agent topology, Docker commands, daily operation,
  backups, readiness, acceptance, and failure behavior. Keep `AGENTS.md` and
  README concise and route readers to current docs.

- [ ] **Step 5: Run the full repository verification**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest -q
  uv run ruff check .
  uv run mypy src
  ```

  Expected: all tests pass and no legacy production import remains.

- [ ] **Step 6: Commit**

  ```powershell
  git add -u src/vbpl_kb/state.py src/vbpl_kb/publish.py `
    src/vbpl_kb/onyx.py src/vbpl_kb/provisions.py `
    scripts/reset-and-reindex-onyx.py tests
  git add AGENTS.md README.md docs/architecture.md `
    docs/legal-data-policy.md docs/development-workflow.md `
    docs/operations.md TODOS.md tests/test_documentation.py `
    tests/test_deployment_files.py
  git commit -m "refactor: remove legacy VBPL pipeline paths"
  ```

### Task 13: Prove the fixture pipeline, index schema, and capacity gates

**Files:**
- Create: `tests/fixtures/e2e/official-corpus/`
- Create: `tests/integration/test_multiview_e2e.py`
- Replace: `scripts/verify-schema-v2-index.py`
- Create: `scripts/estimate-onyx-capacity.py`
- Create: `scripts/benchmark-onyx-embeddings.ps1`
- Create: `scripts/run-multiview-acceptance.ps1`
- Create: `benchmarks/embedding-candidates.json`
- Modify: `tests/test_deployment_files.py`
- Modify: `tests/test_onyx_deployment.py`
- Modify: `docs/operations.md`
- Modify: `tests/test_documentation.py`

**Interfaces:**

- Fixture flow: evidence -> PostgreSQL -> legal tree/semantics -> release ->
  three connector streams -> schema/readiness assertions.
- `scripts/verify-multiview-index.py --release-id <id> --sample-size <n>`
  checks live OpenSearch metadata for random IDs from each required view.
- `scripts/estimate-onyx-capacity.py --manifest <path> --dimension <n>`
  prints machine-readable document/chunk/vector/disk estimates.
- `scripts/benchmark-onyx-embeddings.ps1` creates a disposable, isolated Onyx
  Compose project per checked-in candidate and writes comparable retrieval and
  resource reports without changing the serving Onyx project.

- [ ] **Step 1: Write failing fixture E2E tests**

  Include a small official-evidence corpus with:

  - current hierarchical instrument with Article/Clause/Point;
  - current implementing instrument;
  - historical predecessor;
  - verified amendment/replacement edge;
  - ordinary citation;
  - partial-effect provision;
  - province-scoped instrument;
  - unresolved relation;
  - Evidence audit records.

  Run the real repositories, parser, semantics, projector, release builder, and
  connector class. Assert view namespaces, one-section documents, active IDs,
  deltas, tombstones, and readiness state.

- [ ] **Step 2: Run fixture E2E and confirm failure**

  ```powershell
  docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test `
    uv run pytest tests/integration/test_multiview_e2e.py -q -m postgres
  ```

  Expected: fixture and verification tooling do not exist.

- [ ] **Step 3: Implement live index verification**

  Replace the schema-v2 script with a multi-view verifier that checks
  `projection_kind`, `corpus_view`, `instrument_id`,
  `logical_provision_id`/logical edge, `corpus_revision`, status,
  verification time, official URL, and exact `document_sets` on random Current,
  History, and Evidence samples. Fail on missing fields or cross-view leakage.

- [ ] **Step 4: Implement embedding/dimension benchmark isolation**

  Check in these stock-supported local candidates from the pinned Onyx
  `SUPPORTED_EMBEDDING_MODELS` list:

  ```json
  [
    {
      "model": "intfloat/multilingual-e5-base",
      "dimension": 768,
      "multipass": false
    },
    {
      "model": "intfloat/multilingual-e5-small",
      "dimension": 384,
      "multipass": false
    },
    {
      "model": "nomic-ai/nomic-embed-text-v1",
      "dimension": 768,
      "multipass": true
    }
  ]
  ```

  Add a test that these model/dimension pairs still match the pinned checkout.
  The benchmark script must create a unique Compose project and unique Onyx
  volumes for each candidate, index the same candidate release, run the same
  retrieval cases/reranker/search settings, record quality/latency/index
  time/memory/disk, and then stop without touching the serving project. Do not
  enable multipass for the E5 candidates.

- [ ] **Step 5: Implement capacity estimation**

  Derive projected document counts from manifest records, estimate normal
  chunks using the stock 512-token budget and selected tokenizer, account for
  optional stock-supported multipass large chunks, and calculate raw vector
  bytes from measured chunk count and configured dimension. The report must
  record assumptions rather than treating native model context as chunk size.

- [ ] **Step 6: Run embedding, alpha, and capacity gates on the target Docker host**

  ```powershell
  $candidateRelease = "vbpl-" + (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
  docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline `
    build-release --revision $candidateRelease
  docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline `
    validate-release --revision $candidateRelease
  .\scripts\benchmark-onyx-embeddings.ps1 `
    -ReleaseId $candidateRelease `
    -CandidatesPath benchmarks\embedding-candidates.json `
    -HybridAlpha 0.3,0.5,0.7
  $selection = Get-Content `
    "data\evaluations\$candidateRelease\embedding-selection.json" `
    -Raw | ConvertFrom-Json
  if (-not $selection.passed) {
      throw "No stock-supported embedding/search configuration passed the legal gates"
  }
  $embeddingDimension = [int]$selection.dimension
  docker compose -f docker-compose.vbpl.yml run --rm vbpl-pipeline `
    python scripts/estimate-onyx-capacity.py `
    --manifest "/app/data/exports/releases/$candidateRelease/manifest.json" `
    --dimension $embeddingDimension
  ```

  Record:

  - the selected stock-supported model, dimension, precision, multipass mode,
    and hybrid alpha, with every rejected candidate's gate failures;
  - estimated documents, normal chunks, optional large chunks, and vector bytes;
  - at least 30 percent projected free OpenSearch disk after indexing;
  - measured index time and peak host/container memory on the fixture;
  - no OOM or unbounded retry loop.

  The full official corpus is not cut over in this task; this task proves the
  tooling and produces a validated candidate.

- [ ] **Step 7: Re-run repository and Docker verification**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest -q
  uv run ruff check .
  uv run mypy src
  docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test `
    uv run pytest tests/integration -q -m postgres
  ```

  Expected: unit, documentation, fixture E2E, migrations, and Docker integration
  all pass.

- [ ] **Step 8: Commit**

  ```powershell
  git add tests/fixtures/e2e tests/integration/test_multiview_e2e.py `
    scripts/verify-multiview-index.py scripts/estimate-onyx-capacity.py `
    scripts/benchmark-onyx-embeddings.ps1 `
    scripts/run-multiview-acceptance.ps1 `
    benchmarks/embedding-candidates.json tests/test_deployment_files.py `
    tests/test_onyx_deployment.py docs/operations.md `
    tests/test_documentation.py
  git commit -m "test: prove multi-view VBPL pipeline gates"
  ```

### Task 14: Execute the scoped clean-slate Onyx cutover

**Files:**
- Create: `scripts/inventory-vbpl-onyx.py`
- Create: `scripts/cutover-vbpl-onyx.py`
- Create: `tests/test_cutover.py`
- Modify: `docs/operations.md`
- Modify: `tests/test_documentation.py`
- Runtime artifacts: write untracked inventory, acceptance, and capacity reports under `data/cutover/<timestamp>/`

**Interfaces:**

- `inventory-vbpl-onyx.py` is read-only and emits exact connector, credential
  pair, document set, Agent, indexed document, release, search-setting, and
  Docker volume identities.
- `cutover-vbpl-onyx.py --inventory <path> --candidate-release <id>
  --confirm-scope-hash <sha256>` refuses any target not present in the signed
  inventory and refuses unrelated source types/document sets.
- Destructive execution is impossible without a passing preflight, exact scope
  hash, validated candidate, capacity pass, and an announced downtime flag.

- [ ] **Step 1: Write failing cutover safety tests**

  Assert dry-run by default, exact allowlisting of old `vbpl_export` connector
  IDs/document set IDs/document IDs, rejection of unrelated Onyx objects and
  broad volumes, stable scope hash, resumable step journal, and refusal when
  candidate validation/capacity gates are absent.

- [ ] **Step 2: Run focused tests and confirm failure**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_cutover.py tests/test_documentation.py -q
  ```

  Expected: scoped inventory/cutover tooling does not exist.

- [ ] **Step 3: Implement read-only inventory and dry-run**

  Capture the old connectors, credential pairs, document sets, Agents/prompts,
  search/embedding configuration, scoped `vbpl_export` document counts, current
  release, acceptance baseline, Compose projects, and exact Docker volumes.
  Redact secrets. The dry-run prints every supported Onyx administration
  operation without executing it.

- [ ] **Step 4: Re-run cutover safety tests**

  ```powershell
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest tests/test_cutover.py tests/test_documentation.py -q
  ```

  Expected: dry-run, exact scope allowlist, scope-hash verification, journal
  resume, and unrelated-object refusal tests pass.

- [ ] **Step 5: Complete the new full official build before downtime**

  Using Docker:

  1. create empty PostgreSQL/evidence/export volumes;
  2. run `vbpl-migrate`;
  3. full-crawl official sources;
  4. build the canonical tree, classifications, applicability, and relations;
  5. build and validate all three release views;
  6. estimate full-corpus document/chunk/vector resources;
  7. confirm at least 30 percent projected OpenSearch free disk.

  Keep the old VBPL Agent/index serving throughout this step.

- [ ] **Step 6: Verify exact destructive scope**

  Compare fresh inventory with the reviewed inventory. Stop if any target ID,
  source type, document set, Agent ownership, physical index setting, Compose
  project, or Docker volume differs. Never target Onyx relational volumes,
  users, models, unrelated connectors/document sets, or a workspace root.

- [ ] **Step 7: Run the announced downtime cutover**

  With the exact scope hash:

  1. disable only the old VBPL Agents;
  2. delete only old scoped VBPL connector/credential-pair associations,
     document sets, and their indexed `vbpl_export` documents through supported
     Onyx administration paths;
  3. create `VBPL Current`, `VBPL History`, and `VBPL Evidence`;
  4. attach `VBPL-current`, `VBPL-history`, and `VBPL-evidence`;
  5. full-index all three views;
  6. configure the three Agent profiles;
  7. record connector-applied states.

  Do not delete legacy pipeline data or volumes until acceptance and an
  operator-selected retention period have completed.

- [ ] **Step 8: Run direct Internal Search acceptance and capacity gates**

  Run Current, Historical, and Evidence benchmark suites through ordinary
  authenticated Onyx Chat. Require every hard gate in Task 10. Run 100 warmed
  `internal_search` queries and require p95 at or below 10 seconds. Record total
  full-index time, peak host/container memory, OpenSearch disk headroom, and
  schema samples from every view.

- [ ] **Step 9: Enable Agents only by readiness**

  Enable Current only after Current connector-applied and Current acceptance.
  Enable Historical only after same-revision Current+History application and
  historical acceptance. Enable Evidence Audit only after Evidence application
  and evidence acceptance. If a gate fails, keep the affected Agent disabled
  and preserve all reports for diagnosis.

- [ ] **Step 10: Update operations evidence and commit tooling**

  Do not commit the runtime inventory/report artifacts. Update operations with
  the verified commands, recovery checkpoints, actual non-secret resource
  assumptions, and post-cutover daily procedure.

  ```powershell
  git add scripts/inventory-vbpl-onyx.py scripts/cutover-vbpl-onyx.py `
    tests/test_cutover.py docs/operations.md tests/test_documentation.py
  git commit -m "ops: add scoped VBPL Onyx cutover workflow"
  ```

### Task 15: Review and integrate the completed refactor

**Files:**
- Review: all commits and changed production/tests/docs/Compose/overlay files

**Interfaces:**

- Consumes the approved design, this implementation plan, the complete commit
  range, and fresh unit/integration/live acceptance evidence.
- Produces a reviewed integration decision without changing recorded Agent
  readiness or discarding unresolved findings.

- [ ] **Step 1: Run final evidence-backed verification**

  ```powershell
  git status --short
  git diff --check
  $env:UV_CACHE_DIR="$PWD\.uv-cache"
  uv run pytest -q
  uv run ruff check .
  uv run mypy src
  docker compose -f docker-compose.vbpl.yml --profile test run --rm vbpl-test `
    uv run pytest tests/integration -q -m postgres
  ```

  Also verify the live multi-view index sample, all three acceptance reports,
  readiness states, 30-percent disk headroom, and 100-query warm p95 result.

- [ ] **Step 2: Request focused code review**

  Use `superpowers:requesting-code-review`. Give the reviewer the approved
  design, this plan, commit range, migration/schema, connector overlay diff,
  Compose topology, destructive scope report, and all verification evidence.
  Fix findings with focused failing tests and rerun affected gates.

- [ ] **Step 3: Integrate**

  Use `superpowers:finishing-a-development-branch` to choose the user-approved
  merge, pull-request, or branch-cleanup path. Do not claim Current,
  Historical, or Evidence Agent readiness beyond the readiness state recorded
  for each profile.
