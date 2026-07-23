# VBPL Legal-Data Policy

**Status:** Current
**Applies to:** Source acquisition, state, normalization, references, releases, connector metadata, retrieval, and evaluation changes.
**Use for:** Preserving provenance, legal-status, promotion, freshness, and recovery safety requirements.
**Do not use for:** Runtime Onyx user administration or general Docker lifecycle commands.

## Authority and provenance

The official VBPL service (`vbpl.vn` and its public gateway API) is the legal
authority. Every indexed instrument retains its official source URL, legal
status, verification time, corpus revision, provision structure, and retained
raw evidence. The Hugging Face dataset is bootstrap or coverage-comparison input
only; it never establishes current legal status.

## Legal-status evidence

Never infer legal force from editorial fields such as `status: Publish` or
`reviewStatus`. Use `effStatus` or explicitly verified official canonical-page
evidence. A record with missing, stale, failed, expired, suspended, conflicting,
or unparseable status evidence is not support for a current-law conclusion. It
may be indexed as `unknown` only after raw evidence is retained.

## Releases and relationships

Do not promote a partial, schema-invalid, or checksum-invalid source release.
Preserve the previous active export when candidate validation is blocked. Treat
unresolved legal-effect relationships as unresolved; only explicit official
evidence creates amendment, replacement, or repeal edges. A document reference
alone never establishes legal effect.

## Recovery and retention

Do not delete `data/state.sqlite3`, `data/raw`, or the project Docker volume
merely to recover a crawl. The crawler is checkpointed and resumes the same
revision, retrying missing detail snapshots. A full recrawl and data deletion
require explicit user approval.

## Change impact

Changes to `vbpl_client.py`, `vbpl_fallback.py`, `crawl.py`, `normalize.py`,
`models.py`, `references.py`, `state.py`, `publish.py`, `releases.py`, or
connector metadata must add focused coverage for the affected evidence path. The
test must demonstrate that invalid or incomplete official evidence cannot
silently become a current-law claim or a promoted release.
