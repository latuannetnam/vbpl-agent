# VBPL Hierarchy-Aware Onyx Search Design

**Status:** Approved design
**Date:** 2026-07-24
**Scope:** Stock Onyx Community Edition, the validated VBPL release pipeline,
the persistent VBPL Export Connector, and the scoped VBPL Legal Research Agent.

## Purpose

Improve legal-search results by representing the hierarchy and applicability of
Vietnamese normative legal instruments in the indexed corpus. Search must return
an authority bundle: the controlling provision together with the applicable
implementing, amending, continuing, and local instruments needed to understand
it.

The design keeps stock Onyx CE. Hierarchy intelligence belongs to the validated
VBPL data model, release projection, connector metadata, and canonical agent
instruction. It does not require a maintained fork of Onyx retrieval or ranking
code.

## Authoritative legal basis

Law 87/2025/QH15 amended Law 64/2025/QH15 with effect from 1 July 2025.
The official instrument is:

- <https://vbpl.vn/van-ban/chi-tiet/luat-sua-doi-bo-sung-mot-so-dieu-cua-luat-ban-hanh-van-ban-quy-pham-phap-luat-so-87-2025-qh15--178717>

The current hierarchy regime is named `vn-vbqppl-2025-07-01`. It records the
15 groups in amended Article 4:

| Order | Normative forms |
| ---: | --- |
| 1 | Constitution |
| 2 | Codes, laws, and National Assembly resolutions |
| 3 | Ordinances and resolutions of the National Assembly Standing Committee; specified joint resolutions |
| 4 | Presidential orders and decisions |
| 5 | Government decrees and resolutions; specified joint resolutions |
| 6 | Prime Minister decisions |
| 7 | Resolutions of the Council of Judges of the Supreme People's Court |
| 8 | Circulars of the Chief Justice, Procurator General, ministers, heads of ministerial-level agencies, and State Auditor General |
| 9 | Joint circulars between the authorized central officeholders |
| 10 | Provincial People's Council resolutions |
| 11 | Provincial People's Committee decisions |
| 12 | Provincial People's Committee chairperson decisions |
| 13 | Normative instruments of special administrative-economic local governments |
| 14 | Commune-level People's Council resolutions |
| 15 | Commune-level People's Committee decisions |

The numbered order is statutory classification data. It is not a global Onyx
document boost.

All forms listed within the same numbered paragraph share one
`authority_group`. The classifier does not create an additional hierarchy
between forms within that group.

The application rules modeled by the system are:

1. Use an instrument only for events, subjects, and territory within its
   effective scope.
2. Where applicable instruments regulate the same issue differently, use the
   instrument with higher legal effect.
3. Where different rules were issued by the same authority, use the later
   instrument.
4. Apply treaty precedence where legally applicable, except against the
   Constitution.
5. Respect an explicit exception enacted by the National Assembly.
6. Do not treat `lex specialis` as a universal automatic override. A narrower
   provision applies because its stated scope covers the facts or authoritative
   evidence establishes a special application rule.
7. If verified evidence does not resolve the difference, preserve and report
   the conflict as unresolved.

Law 87/2025/QH15 also creates material temporal and local rules:

- Former district-level People's Council and People's Committee instruments
  may continue only within their transitional scope, no later than
  28 February 2027, and may cease earlier through an applicable replacement or
  official decision.
- Implementing or detailed instruments affected by amendment or replacement of
  their parent require explicit continuation evidence where the law requires
  it.
- Provincial, commune, and special-zone instruments require geographic as well
  as temporal applicability.

## Goals

- Make authority, status, time, jurisdiction, and provision coordinates
  available to every retrievable legal chunk.
- Retrieve the controlling provision without suppressing relevant subordinate
  implementation details.
- Make verified legal relationships searchable through stock Onyx metadata.
- Preserve stable instrument identities and the immutable release contract.
- Infer time, jurisdiction, subject, and requested legal consequence from the
  conversation when supported.
- Ask one focused follow-up only when a missing fact cannot be inferred and
  could materially change the result.
- Fail closed for current-law conclusions when official evidence is stale,
  missing, conflicting, or insufficiently granular.
- Prove the behavior with automated evaluation and direct queries against the
  current Onyx Chat/Internal Search path.

## Non-goals

- Maintaining a custom Onyx retrieval or reranking fork.
- Applying an unconditional numeric boost based on Article 4 order.
- Adding a separate graph database.
- Using the current Onyx MCP server for acceptance testing.
- Inferring amendment, replacement, repeal, suspension, continuation, or
  implementation from an ordinary citation.
- Using the 2025 hierarchy regime to resolve conflicts for events before
  1 July 2025. Earlier regimes require separate modeled catalogs.
- Updating current operational or coding-agent documentation before the
  implementation behavior is settled.

## Current-system assessment

The current release contains one Onyx document per instrument with stable
identity `vbpl:<official-id>`. The active projection records official status,
verification time, document type, issuer, and source URL.

The current projection has four limitations relevant to hierarchy-aware search:

1. A raw `docType` may be a structured object, but normalization currently
   forwards it without deriving a stable normative-form classification.
2. Each instrument is sent to Onyx as one `TextSection`; Onyx can therefore
   retrieve a provision chunk separated from the legal context at the beginning
   or end of the document.
3. Structured VBPL references are flattened to ordinary citations, while text
   heuristics can create duplicate and self-referential apparent legal-effect
   edges.
4. The canonical agent instruction contains a simplified
   Constitution/Law/Decree/Circular ladder and a generic `lex specialis` rule
   that is too broad for safe conflict resolution.

## Chosen architecture

```text
Official VBPL API and canonical-page evidence
  -> normalized instruments and provisions
  -> versioned authority classification
  -> applicability envelopes
  -> verified relationship graph
  -> checksummed schema-v2 candidate release
  -> atomic active-release pointer
  -> backward-compatible VBPL Export Connector
  -> stock Onyx chunk indexing
  -> scoped Legal Research Agent authority-bundle workflow
```

The design introduces four bounded units.

### Authority classifier

The classifier consumes normalized official document form and issuer data. It
returns:

- `hierarchy_regime`
- `article4_order`
- `normative_form`
- `authority_group`
- `issuer_type`
- `classification_status`
- `classification_source`
- `classification_version`
- `is_normative`

`authority_group` is the stable slug for one numbered Article 4 paragraph.
`classification_version` identifies the exact checked-in mapping-table version;
`hierarchy_regime` identifies the legal period in which that mapping applies.

`classification_status` is one of:

- `known`
- `unknown`
- `not_normative`
- `legacy_transitional`

The classifier must accept the VBPL form as either a string or an object with
fields such as `name`, `code`, and `parentCode`. It normalizes the input before
matching. Form alone is insufficient for forms such as `Nghị quyết`,
`Quyết định`, or `Thông tư`; the issuer is part of the classification key.

An unknown combination remains unknown. The classifier does not guess from the
instrument title when official form or issuer evidence conflicts with the
title. Title parsing may produce diagnostic evidence only.

### Applicability envelope

Every instrument carries:

- `legal_status_raw`
- `legal_status_normalized`
- `verified_at`
- `status_source`
- `effective_from`
- `effective_to`
- `jurisdiction_level`
- `jurisdiction_code`
- `jurisdiction_name`
- `transitional_until`
- `source_url`
- `corpus_revision`
- `status_evidence_hash`

For a current-law conclusion, `verified_at` must be no more than 24 hours old.
The existing configured freshness check remains the source for calculating the
age; the hierarchy feature must not introduce a second, inconsistent clock.

`jurisdiction_level` is one of:

- `national`
- `province`
- `commune`
- `special_zone`
- `legacy_district`
- `unknown`

Every provision section additionally carries:

- `provision_key`
- `article_number`
- `clause_number`
- `point_label`
- `provision_heading`
- `citation_structure`

Empty values are explicit empty strings or nulls according to the release
schema. Their absence must not silently acquire a default legal meaning.

### Verified relationship graph

Relationships are stored independently from their searchable projection. A
relationship record includes:

- source instrument and provision
- target instrument and provision, when resolved
- relation type
- evidence kind
- source quote or official structured payload reference
- source offset when available
- confidence or resolution state
- evidence hash
- corpus revision

Supported relation types are:

- `cites`
- `legal_basis`
- `details`
- `implements`
- `delegated_by`
- `amends`
- `supplements`
- `replaces`
- `repeals`
- `suspends`
- `continues_effect`
- `unknown`

Legal-effect relationships require explicit official evidence. The
implementation must first verify the semantics of VBPL structured
`referenceType` values against official evidence or retained raw examples.
Unmapped values remain `unknown`; they are not guessed from their numeric code.

Text extraction may create unresolved candidates for review or later
resolution. It cannot promote a candidate into `amends`, `supplements`,
`replaces`, `repeals`, `suspends`, or `continues_effect` without explicit
official evidence.

Before export:

- identical edges are deduplicated;
- heuristic self-references are excluded from the searchable graph;
- unresolved targets remain unresolved;
- raw evidence remains retained;
- ordinary citations remain distinct from legal-effect relationships.

Searchable metadata contains compact outgoing relation tokens containing the
relation type and target instrument number or ID. An amending or implementing
instrument therefore contains the parent instrument's identifier. A stock Onyx
search for the parent identifier can retrieve related instruments without
materializing an unbounded reverse-edge list on the parent.

### Provision-aware release projection

Release schema version 2 retains one Onyx document per instrument:

```json
{
  "projection_schema_version": 2,
  "document_id": "vbpl:<official-id>",
  "link": "https://vbpl.vn/van-ban/chi-tiet/...",
  "sections": [
    {
      "section_id": "dieu-1/khoan-2/diem-a",
      "text": "<compact legal context header>\\n\\n<provision text>",
      "link": "https://vbpl.vn/van-ban/chi-tiet/..."
    }
  ],
  "metadata": {
    "hierarchy_regime": "vn-vbqppl-2025-07-01",
    "article4_order": "2",
    "normative_form": "law",
    "issuer_type": "national_assembly",
    "jurisdiction_level": "national",
    "legal_status_normalized": "in_force",
    "relation_tokens": [
      "amends:64/2025/QH15"
    ]
  }
}
```

The exact JSON validation model belongs to implementation planning, but the
following contract is fixed:

- `projection_schema_version` is required.
- `document_id` remains `vbpl:<official-id>`.
- `sections` is ordered and non-empty for a document with usable content.
- Each section has a stable `section_id`, text, and official document link.
- The compact context header repeats the minimum authority and applicability
  information needed when that section is retrieved in isolation.
- Full raw evidence does not move into the searchable header.
- Instrument metadata is represented by short scalar values or short token
  lists so Onyx does not discard an oversized semantic metadata suffix.

The compact section header contains:

- instrument title and number;
- provision coordinate;
- normative form and issuer;
- Article 4 order or explicit unknown classification;
- legal status and verification time;
- effective period;
- jurisdiction;
- relevant verified outgoing relationship tokens.

The exporter may include a preamble or whole-document fallback section for
unparsed documents. Such a section is marked `citation_structure=unparsed` and
cannot support an exact provision-level current-law conclusion.

The connector emits one Onyx `TextSection` for every exported section, under
the stable instrument document ID. The connector supports both:

- schema-v1 documents with one `content` string; and
- schema-v2 documents with `sections`.

Because existing schema-v1 releases have no version field, an absent
`projection_schema_version` is interpreted as version 1 only. Every newly
exported document must declare its version.

Unsupported schema versions fail connector validation instead of silently
changing the indexed document.

## Search and authority-bundle workflow

The canonical runtime instruction is
`docs/onyx-agent-instruction.md`.

The agent follows these stages.

### Establish legal coordinates

Extract:

- regulated subject;
- conduct or legal issue;
- requested consequence;
- relevant event time;
- jurisdiction;
- current-law or historical-law intent.

Inference precedence is:

1. explicit facts in the current request;
2. facts established in the conversation;
3. a clearly stated assumption that does not materially alter the result.

Retrieved law may validate applicability but must not invent personal or
transactional facts about the user. If a missing fact cannot be inferred and
could change the legal result, the agent asks one focused question before
concluding.

### Retrieve the controlling provision

The first Internal Search query uses the issue terms and legal coordinates.
Candidates pass, in order:

1. official-evidence gate;
2. status and freshness gate;
3. temporal applicability;
4. geographic applicability;
5. subject and conduct scope.

Semantic and keyword relevance remain primary retrieval signals. Article 4
order is not an unconditional document boost.

### Expand the authority bundle

The agent performs bounded follow-up Internal Search queries using the retrieved
instrument number, provision coordinate, and verified relation tokens. It seeks:

- amendments, supplements, replacements, and repeals;
- suspension and continuation instruments;
- detailed and implementing instruments;
- delegated rules;
- applicable provincial, commune, or special-zone rules;
- the parent instrument of an implementing provision.

The result is a legal family, not a flat list of semantically similar
documents.

### Resolve differences conservatively

The agent applies the legal rules listed under "Authoritative legal basis."
It must:

- distinguish scope selection from hierarchy conflict resolution;
- retain necessary subordinate implementation details;
- state why an otherwise similar candidate is inapplicable;
- avoid treating a normal citation as legal-effect evidence;
- label unresolved conflicts rather than inventing a winner.

### Answer structure

The answer presents:

1. controlling provision;
2. applicable implementing detail;
3. amendments and legal-effect qualifications;
4. applicable local rule;
5. excluded candidates and exclusion reasons when material;
6. unresolved conflict, if any;
7. official citations and verification timestamps.

Each substantive conclusion cites:

- instrument number and title;
- article, clause, and point;
- issuer;
- effective date;
- status;
- `verified_at`;
- official VBPL URL.

The required refusal remains:

```text
Không tìm thấy căn cứ VBPL đã được xác minh để trả lời câu hỏi này.
```

## Failure handling

| Condition | Required behavior |
| --- | --- |
| Unknown form or issuer | Index as `authority_unknown`; do not use to resolve hierarchy |
| Missing, stale, or conflicting status | Discovery-only; exclude from current-law conclusions |
| Partial effectiveness without provision evidence | Do not claim the provision remains effective |
| Ambiguous relationship | Retain unresolved evidence; do not traverse it as legal effect |
| Duplicate or heuristic self-reference | Exclude from searchable legal-effect edges |
| Missing material time or jurisdiction | Infer only from supported context; otherwise ask one focused question |
| Same-level conflict not resolved by verified rules | Present both and label unresolved |
| Pre-1 July 2025 conflict without an earlier regime | Discovery-only; do not apply the 2025 hierarchy retroactively |
| Invalid projection schema or checksum | Block promotion and retain the prior active release |
| Connector or re-index failure | Preserve the existing source, document set, index, and prior release |

Unknown classification is a valid explicit state and does not alone make the
release schema-invalid. It cannot, however, support a hierarchy-based current-
law resolution.

## Verification strategy

### Automated tests

Unit tests cover:

- all 15 Article 4 groups;
- structured and string document-type inputs;
- issuer-sensitive classification;
- unknown, non-normative, and transitional classification;
- geographic scope;
- effective regimes and district transition;
- provision coordinates and compact context headers;
- metadata size and sanitization behavior.

Relationship tests cover:

- verified structured evidence;
- unmapped structured relation types;
- text candidates;
- explicit legal-effect promotion requirements;
- deduplication;
- self-reference exclusion;
- unresolved targets;
- evidence hashes.

Release and connector tests cover:

- schema-v1 and schema-v2 reads;
- unsupported-version refusal;
- stable document identities;
- ordered sections and per-section links;
- batching;
- checksums;
- invalid-candidate blocking;
- atomic promotion;
- prior-release preservation.

Agent-instruction contract tests cover:

- contextual inference;
- targeted clarification;
- staged Internal Search;
- current-law refusal;
- conservative conflict resolution;
- no generic `lex specialis` override;
- complete citations.

### Retrieval evaluation

The evaluation corpus includes:

- higher-level versus conflicting implementing instrument;
- query specifically seeking implementation details;
- later instrument from the same authority;
- same-level instruments from different authorities;
- treaty versus domestic instrument;
- partial effectiveness;
- stale or unknown status;
- provincial and commune mismatch;
- district transition before and after 28 February 2027;
- amendment, replacement, continuation, and ordinary-citation distinctions;
- sufficient context versus a materially ambiguous question.

Acceptance gates are:

- zero unsafe current-law conclusions;
- 100% correct conflict outcome where verified rules resolve the case;
- 100% unresolved labeling where evidence does not resolve the case;
- controlling-provision recall@10 of at least 95%;
- expected authority-bundle completeness@10 of at least 90%;
- no regression in implementation-detail cases from global authority
  suppression;
- stable `vbpl:<official-id>` identities;
- indexed chunk count no more than 1.25 times the measured current baseline
  without explicit approval;
- focused tests, full pytest, Ruff, mypy, and documentation-contract tests
  passing.

### Direct test against the current Onyx instance

Automated tests are not sufficient for completion. The implementation must make
direct queries through the current Onyx Chat/Internal Search path.

The test may use:

- the ordinary authenticated Onyx Chat API; or
- the Onyx web UI.

It must not use the current Onyx MCP server or MCP endpoint.

Before implementation changes alter the current instance, capture a baseline
where feasible. Run the same evidence-backed query set after deployment with the
same model, agent identity, document set, and model parameters. The indexed
release and canonical prompt are the intended variables; record both prompt
hashes and both release IDs, plus any unavoidable differences.

Select live cases only after confirming that the required instruments and
official evidence exist in the active release. The set covers hierarchy,
implementation detail, legal-effect relationships, partial effectiveness,
jurisdiction, contextual inference, and required clarification.

For every live response, record:

- query;
- model and agent;
- prompt hash;
- active release ID;
- connector/indexing status;
- answer;
- retrieved source documents and chunks;
- official links;
- pass/fail findings;
- test timestamp.

Inspect:

- controlling and supporting instruments;
- authority ordering;
- legal status and `verified_at`;
- provision-level citations;
- inclusion of necessary implementing instruments;
- exclusion or explicit labeling of stale, inapplicable, and unresolved
  material;
- whether context was inferred when available;
- whether clarification occurred only for a materially missing fact.

Direct Onyx verification is a completion gate.

## Migration and rollout

1. Capture the current release, connector, prompt, query, chunk-count, and live
   search baselines.
2. Implement the classifier, applicability envelope, provision sections,
   relationship evidence model, schema-v2 exporter, connector compatibility,
   and automated tests.
3. Complete focused and full code verification.
4. After implementation behavior is settled, update current documentation:
   - `AGENTS.md` as a thin routing and guardrail entrypoint;
   - `README.md` where onboarding or behavior changes;
   - `docs/architecture.md`;
   - `docs/legal-data-policy.md`;
   - `docs/operations.md`;
   - `docs/onyx-agent-setup.md`;
   - `docs/onyx-agent-instruction.md`;
   - `tests/test_documentation.py`.
5. Do not route current documents to this historical design specification.
6. Run the full verification gate again after documentation updates.
7. Generate schema-v2 candidate output without promotion.
8. Compare candidate evaluation with the captured baseline.
9. Deploy the backward-compatible connector before promoting schema v2.
10. Promote the validated candidate atomically.
11. Trigger one full re-index of the persistent VBPL Export Connector.
12. Apply the canonical agent instruction to the current Onyx instance.
13. Run direct Onyx Chat/Internal Search acceptance tests without MCP.
14. Retain the prior release and prior prompt for rollback.

A failed candidate, connector run, or re-index does not authorize deleting the
SQLite state, raw snapshots, export releases, Onyx source, document set, index,
or Docker volumes.

Rollback atomically restores the prior validated `active-release.json` target,
restores the prior prompt when the prompt caused the regression, and triggers
the existing connector again. It does not recreate or delete the connector.

## Documentation boundary

`AGENTS.md` remains concise. It routes hierarchy, applicability, projection, and
relationship changes to the current legal-data policy, architecture, and
development workflow. It does not duplicate the 15-level table or runtime
prompt.

The canonical runtime prompt is `docs/onyx-agent-instruction.md`. The existing
`docs/vbpl-legal-agent-instruction.md` is not treated as the active prompt for
this feature.

Current documentation is updated only after implementation behavior and
operations are known. Historical specifications and plans remain records of
decisions, not current coding instructions.

## Approved decisions

- Use stock Onyx CE.
- Build authority bundles rather than globally boosting higher-level
  instruments.
- Keep stable instrument document identities.
- Use provision-aware sections and compact searchable metadata.
- Infer legal coordinates from conversation context and ask only when a
  material fact cannot be inferred.
- Treat `docs/onyx-agent-instruction.md` as the canonical runtime instruction.
- Update `AGENTS.md` and related current documents after implementation is
  complete.
- Prove the result through direct queries against the current Onyx instance.
- Do not use the current MCP server for acceptance testing.
