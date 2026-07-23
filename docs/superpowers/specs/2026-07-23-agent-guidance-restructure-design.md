# Agent Guidance and Documentation Restructure Design

**Status:** Proposed for review
**Date:** 2026-07-23
**Scope:** Developer guidance for Codex, Claude Code, and maintainers

## Purpose

Make the repository easier and safer for coding agents to understand before
future development work. The root instructions must be short, task-oriented,
and current. Detailed guidance must have one canonical home so that agents do
not select obsolete plans, duplicate rules, or runtime operator instructions as
implementation requirements.

This design governs repository development guidance only. It does not redesign
the end-user Onyx legal-research prompt or change the legal answer contract.

## Current problems

- `AGENTS.md` combines repository navigation, legal-data invariants, detailed
  Onyx connector implementation constraints, Docker operations, and Release 1
  product scope. It is too large to serve as a reliable first-read entrypoint.
- `README.md`, `docs/operations.md`, and the connector design repeat pipeline
  and Onyx deployment descriptions with different levels of detail.
- Date-stamped plans and specifications are useful historical evidence, but
  they are poor default instructions. An agent can mistake an older design for
  the current contract when it follows a broad list of document references.
- The runtime Onyx agent setup guide sits beside development guidance without a
  clear audience boundary.

## Documentation authority model

The repository will have a single current-document layer and a separate
historical-record layer.

### Current documents

| Document | Audience | Canonical responsibility |
| --- | --- | --- |
| `AGENTS.md` | Coding agents | First-read guardrails, task routing, mandatory verification, and links to current documents. |
| `README.md` | New developers and operators | Project orientation, prerequisites, quick start, and a documentation map. |
| `docs/architecture.md` | Developers | Current component boundaries, data flow, source-of-truth hierarchy, code map, and dependency rules. |
| `docs/development-workflow.md` | Developers and coding agents | How to investigate, change, test, document, and review a task by change type. |
| `docs/legal-data-policy.md` | Developers and coding agents | Legal-data safety invariants and the consequences for crawler, normalization, reference, release, and retrieval changes. |
| `docs/operations.md` | Operators | Docker, daily execution, observability, recovery, and safe failure handling. |
| `docs/onyx-agent-setup.md` | Onyx administrators | Runtime configuration of the VBPL Legal Agent and its document-set scope. |

Every current document will begin with a compact authority block:

```markdown
**Status:** Current
**Applies to:** <scope>
**Use for:** <task types>
**Do not use for:** <out-of-scope work>
```

`Supersedes:` is added only when the document replaces a particular previous
instruction. It must name the older document precisely and must not imply that
historical records have been deleted.

### Historical records

`docs/superpowers/specs/` and `docs/superpowers/plans/` remain historical
decision and implementation records. They are not default reading for coding
agents and are never linked by `AGENTS.md` or the README quick-start flow.

When historical material still explains a current design decision, the relevant
canonical document may name it in a short `Background` section. That reference
must identify the decision it supports and state that the canonical document is
the current operational instruction.

## Root `AGENTS.md`

`AGENTS.md` will be reduced to a concise entrypoint, targeted at roughly
100–150 lines. It will contain only information that an agent must know before
opening files or executing a command:

1. Project purpose and authoritative-source boundary: official VBPL evidence
   is authoritative; Onyx is an internal retrieval interface.
2. Non-negotiable legal-data and safety rules, expressed as short directives.
3. A task-routing table that maps change categories to the current documents
   and likely source locations.
4. A safe development loop: read the applicable current document and tests,
   add focused coverage first, make the smallest coherent change, run the
   required verification, and update canonical documentation when behavior or
   operations change.
5. Secret, persisted-data, and Docker safety boundaries.
6. Required full verification commands and a note to preserve unrelated
   working-tree changes.

Detailed connector batch behavior, frontend source registration, GPU Compose
syntax, and command examples will move out of the root file. `AGENTS.md` will
route agents to `docs/architecture.md` for implementation contracts and to
`docs/operations.md` for execution details.

The root guide will not reference any date-stamped plan or specification.

### Task routing

| Change category | Read first | Primary locations |
| --- | --- | --- |
| Crawl, schema, normalization, legal status, or references | `docs/legal-data-policy.md`, `docs/architecture.md` | `src/vbpl_kb/`, `tests/` |
| Candidate exports, release promotion, or connector input | `docs/legal-data-policy.md`, `docs/architecture.md` | `releases.py`, `state.py`, connector code |
| Onyx connector, overlay, or Compose integration | `docs/architecture.md`, `docs/operations.md` | `infra/onyx/`, `scripts/`, Compose files |
| Daily run, Docker startup, incident, or recovery | `docs/operations.md` | `scripts/`, Compose files |
| Onyx Legal Agent UI configuration | `docs/onyx-agent-setup.md` | Runtime configuration only |

## `README.md`

The README becomes a concise onboarding page and documentation map. It owns:

1. A one-paragraph project overview and Release 1 boundary.
2. Prerequisites and safe `.env` setup without exposing secrets.
3. Current quick-start commands for starting Onyx, running the daily pipeline,
   checking status, and running the test suite.
4. A documentation map linking to every current document and `AGENTS.md`.
5. A short explanation that dated plans and specifications are historical
   records, not the operational source of truth.

The README will not restate pipeline stages, release validation rules,
connector contracts, recovery procedures, GPU configuration, or Onyx agent
prompt content. It will link to the canonical document that owns each topic.

## Canonical-document content

### `docs/architecture.md`

This new document consolidates the current implementation model from approved
decisions without reproducing their dated-spec format. It will define:

- the official VBPL API/canonical-page, pipeline, release, connector, Onyx,
  and chat boundaries;
- ownership of acquisition, validation, export, indexing, and synthesis;
- current release and connector contracts, including batch behavior and
  read-only export-volume boundaries;
- code and infrastructure map, with a short description of each module;
- allowed dependencies and prohibited production paths, including no new
  direct-ingestion dependency for the daily path.

### `docs/development-workflow.md`

This new document will define a repeatable coding-agent workflow:

- classify the requested change with the routing table;
- identify the canonical contract and focused tests before editing;
- preserve legal-data invariants while making the smallest coherent change;
- update code, tests, and the document that owns changed behavior together;
- run the full required verification set before committing;
- report commands run, results, and any unverified boundary.

It will also state when to consult a historical decision record: only when the
current canonical document identifies an unresolved design question or an
implementation detail that has not been migrated.

### `docs/legal-data-policy.md`

This new document becomes the sole detailed policy reference for the existing
legal-data invariants. It will preserve the strict requirements for official
provenance, legal-status evidence, fail-closed promotion, unresolved
relationships, freshness, raw evidence retention, and checkpointed recovery.
It will include change-impact guidance for the crawler, normalizer, state
store, release exporter, connector metadata, and retrieval behavior.

### Existing runbooks

`docs/operations.md` will retain operational commands and recovery procedures,
but replace implementation explanations with links to the architecture and
legal-data policy. `docs/onyx-agent-setup.md` will receive a prominent
audience/scope block stating that it configures the running product and is not
the primary guide for repository code changes.

## Link and duplication rules

- Each substantive topic has exactly one canonical owner in the table above.
- A non-owner document may have a one-sentence summary and a relative link;
  it must not restate commands, rules, or contracts in detail.
- Links from `AGENTS.md` and `README.md` target only current documents.
- A current document may link to a historical record only in a labeled
  `Background` section, never as an imperative task instruction.
- User-facing legal-agent instructions remain separate from coding-agent
  guidance and are not loaded by default for development work.

## Validation and maintenance

Add a focused documentation contract test or check that verifies:

1. `AGENTS.md` links to the required current documents.
2. `README.md` links to the same canonical documentation map.
3. Neither entrypoint links into `docs/superpowers/specs/` or
   `docs/superpowers/plans/`.
4. Every canonical document has the required authority block.
5. The root guide contains the required full verification commands.

The check must be deterministic, run offline, and avoid asserting prose that
does not form part of the documentation contract.

## Migration sequence

1. Create the three canonical development documents.
2. Rewrite `AGENTS.md` as the concise entrypoint and task router.
3. Rewrite `README.md` as onboarding and documentation map.
4. Remove duplicate architecture and policy prose from the existing runbooks;
   replace it with canonical links.
5. Add status/scope blocks to all current documents.
6. Add the documentation contract test and include it in the normal test suite.
7. Run documentation-link checks, the full Python verification suite, lint,
   and type checking.

## Acceptance criteria

1. A coding agent can identify the relevant current document for each listed
   change category without reading a historical plan or specification.
2. `AGENTS.md` contains no links to dated plans or specifications and remains
   a concise, first-read guide.
3. The README provides current onboarding commands without duplicating detailed
   architecture or operations content.
4. Legal-data safety directives remain immediately discoverable from the root
   guide and fully specified in `docs/legal-data-policy.md`.
5. Onyx runtime setup is clearly separated from repository-development
   instructions.
6. An automated check detects future drift in entrypoint links and required
   authority blocks.
