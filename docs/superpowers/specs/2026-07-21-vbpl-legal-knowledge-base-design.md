# VBPL Legal Knowledge Base Design

**Status:** Approved design

## 1. Goal and scope

Build an internal Vietnamese legal knowledge base from the official VBPL service. Onyx is the staff-facing Search UI, Chat UI, and Legal Research Agent runtime. Results must be grounded in the official source text and identify the exact cited legal provision.

Release 1 includes:

- daily crawl and verification from the VBPL public API;
- Onyx Search UI for document/provision discovery;
- Onyx Chat UI with one scoped `VBPL Legal Research` agent;
- cross-reference traversal between legal instruments;
- one cloud and one on-premises LLM option.

Release 1 excludes external agent integrations, SSO/SCIM, granular document permissions, SIEM, Kubernetes, graph databases, and response-validation middleware.

Release 2 exposes Onyx's verified legal corpus to Claude Code, Codex, Antigravity, and other MCP-compatible clients. These clients use Onyx rather than crawling VBPL independently.

## 2. Authority and source-of-truth model

- **Legal authority:** the official VBPL service (`vbpl.vn` and its public gateway APIs).
- **Bootstrap input:** `tmquan/vbpl-vn`; useful for initial coverage comparison only, never used to establish current status.
- **Internal approved research interface:** Onyx's `vbpl-verified` corpus.
- **Audit authority:** immutable raw VBPL response snapshots and crawl manifests.

The crawler obtains instrument detail from `GET /api/qtdc/public/doc/{id}` and reads status fields including `effStatus` and `effFrom`. It also obtains document index/structure metadata from the official document page flow. These API interactions are treated as an observed contract: schema tests prevent silent publication after an upstream change.

## 3. Components

```text
VBPL public APIs
  -> crawl + snapshot worker
  -> normalizer, provision splitter, reference resolver
  -> validated corpus revision
  -> Onyx Standard / vbpl-verified
       -> Search UI
       -> Chat UI / VBPL Legal Research Agent

Later: MCP-compatible agents -> Onyx MCP -> vbpl-verified
```

### 3.1 Crawl and validation worker

A scheduled daily worker enumerates the official catalog, snapshots detail and status responses, detects changes, and extracts body and structure data. It is checkpointed, idempotent, rate-limited, retried with exponential backoff, and records per-ID failures.

The worker must not use a view-count-sorted catalog as an incremental cursor. It scans the full intended catalog and records coverage so status changes to old instruments are not missed.

### 3.2 Canonical records

| Record | Required contents |
|---|---|
| `vbpl_raw_snapshot` | VBPL ID, endpoint, fetch time, response body and hash |
| `legal_instrument` | number, title, type, issuer, dates, canonical URL, text hash |
| `legal_provision` | VBPL ID, article/clause/point key, text, source offsets |
| `status_observation` | VBPL ID, `effStatus`, `effFrom`, checked time, raw hash, crawl run |
| `legal_reference` | origin/target provisions, type, evidence span, resolution confidence |
| `crawl_run` | revision, coverage, failures, schema checks, timestamps |
| `onyx_projection` | VBPL ID, Onyx ID, content hash, indexed/published revision |

Use SQLite and mounted local storage for the pilot: raw snapshots, normalized revision artifacts, crawl state, relationship records, error queues, and run reports. Do not couple pipeline state to Onyx's own database.

### 3.3 Onyx projection

Index one logical Onyx document per legal instrument, with headed sections for each `Điều`, `Khoản`, and `Điểm`. The generated document begins with a provenance block containing document identity, canonical link, legal status, verification time, and corpus revision. Every provision heading is retained so retrieved chunks are citable.

Required metadata includes `legal_status`, `status_checked_at`, `effective_from`, `source_url`, `corpus_revision`, document type, legal area, issuer, and scope. Search defaults to current, fresh records but can explicitly show historical records with prominent status labels.

A revision is promoted only after validation and Onyx ingestion complete. The prior revision remains available during a failed run but becomes stale after 24 hours.

## 4. Status policy

Statuses are cached before queries through the daily crawl. A current-law claim is permitted only when the cited record has a successful verification no older than 24 hours.

- `Còn hiệu lực`: eligible for a current-law answer.
- `Hết hiệu lực một phần`: eligible only with the limitation stated first.
- `Chưa có hiệu lực`: never described as presently effective.
- fully expired, suspended, missing, conflicting, or stale: historical/discovery use only; no current-law conclusion.
- crawl or parse failure: `verification_failed`; never reuse an old status as current.

## 5. Cross-reference graph

Treat cross-references as legal data, not plain text. `legal_reference` edges have source provision, target provision when resolved, relation type, source quote/offset, confidence, evidence hash, and revision.

Allowed relation types are `cites`, `legal_basis`, `guides_implementation`, `amends`, `supplements`, `replaces`, `repeals`, and `unknown`. Only explicit official evidence can establish a legal-effect relationship such as amendment, replacement, or repeal. Ambiguous references remain unresolved and are reviewable.

Generated documents contain a `Văn bản liên quan` section. The Chat agent can traverse resolved edges with a two-hop/ten-document cap. It must cite both originating and target provisions and must not treat a historical reference as evidence that an expired target remains current.

## 6. User experience

### Search UI

Staff search for legal terms, document number, agency, date, or status. A result exposes the instrument/provision identifier, status badge, verification time, highlighted excerpt, canonical VBPL link, and related documents. Metadata filters support document type, legal area, issuer, scope, status, and time.

### Chat UI and agent

The `VBPL Legal Research` agent is scoped exclusively to `vbpl-verified`. It has no web-search, code-execution, or unrelated connector actions. It searches before answering and returns:

1. concise Vietnamese answer;
2. status warning when applicable;
3. one source citation for every substantive conclusion, containing instrument, provision, canonical link, status, and verification time.

It refuses a current-law conclusion if it cannot retrieve fresh verified evidence. It distinguishes direct quotation from its own explanation and never invents a provision, date, or relationship.

## 7. Model providers

Enable a short model list:

- one approved cloud provider/model as the Legal Agent's default;
- one on-premises runtime through Ollama, LM Studio, or an OpenAI-compatible internal endpoint.

Provider selection changes synthesis only; retrieval, status, cross-reference, and citation policy remain identical. Record model ID, corpus revision, and citation IDs for benchmark conversations. Test all enabled models on the same Vietnamese legal benchmark before publishing them. The UI must warn users not to send sensitive case facts to a cloud provider unless approved.

## 8. Simplified pilot security

- one self-hosted Onyx Standard Docker Compose deployment on an internal network/VPN;
- Basic Auth; one Onyx admin, one crawler/indexer service credential, and authenticated pilot users;
- one shared public-to-pilot `vbpl-verified` corpus; no per-document permissions;
- local deployment environment variables for secrets, never committed or indexed;
- local run logs and revision manifests only;
- no external MCP endpoint in Release 1.

The minimum boundary is authenticated internal access, no public exposure, and no secrets in corpus content.

## 9. Deployment

Deploy Onyx Standard with Docker Compose on one internal host. Do not select Onyx Lite because it disables indexing and RAG search. Run the VBPL worker as a separately scheduled process/container on the same host for the pilot.

Start capacity planning from Onyx Standard's published preferred baseline of 8+ vCPU, 16+ GB RAM, and disk sufficient for raw snapshots plus index overhead. Before full crawl, ingest a representative corpus sample and measure index size, memory, query latency, and daily update duration. Do not enable Craft, code execution, or web search.

## 10. Quality gates and acceptance

Maintain a human-reviewed Vietnamese benchmark spanning exact provision lookup, natural-language retrieval, all effectiveness states, amendment/repeal chains, ambiguous numbers, and misleading historical references.

Promotion requires complete intended crawl coverage, valid citations and status metadata, no duplicate identities, reconciled Onyx updates, and sampled Search/Chat checks.

Release 1 targets:

| Measure | Target |
|---|---:|
| Expected provision retrieved in top 10 | >= 95% |
| Correct instrument/provision for benchmark citation | 100% |
| Citation link resolves to VBPL | 100% |
| Current-law answer from stale/failed verification | 0 |
| Incorrect legal-effect graph edge | 0 |

If daily verification fails, Search remains available with an explicit stale banner; Chat may help locate historical material but refuses current-law conclusions.

## 11. Rollout

1. Build crawler and normalizer against a small manually reviewed legal-area subset.
2. Validate daily crawl, status cache, structure parsing, references, and Onyx indexing.
3. Run a staff pilot in Search UI and Chat UI with the scoped Legal Agent.
4. Review failed searches, citation corrections, and unresolved references weekly.
5. Expand to the full catalog when quality gates hold.
6. In Release 2, enable the Onyx MCP server for external agents. Their legal-research contract allows only Onyx indexed-document search; they cite returned provision evidence and do not run separate VBPL crawlers. If technical enforcement is required, use a thin internal MCP proxy that exposes only the legal search surface.
