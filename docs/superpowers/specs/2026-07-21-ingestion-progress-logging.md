# Ingestion progress logging

## Goal

Make the one-shot VBPL ingestion visibly progress in Docker logs without
changing crawl, normalization, reference-resolution, publication, or state
semantics.

## Design

- `DailyCrawler` and `Publisher` accept an optional progress callback.
- Each component emits human-readable phase events and cumulative counts.
- The CLI supplies a callback that writes one event per line with `typer.echo`,
  which is visible through `docker compose ... logs`.
- Events contain only phase names, document counts, catalog page numbers,
  failure counts, and publish upsert/delete counts. They never contain
  credentials, request headers, or document body text.
- Progress is emitted at phase boundaries and after each configured batch of
  fetched or published documents. Completion summaries remain unchanged.

## Event examples

```text
crawl: catalog page 3 discovered; documents=300
crawl: fetched 250/1200 documents (failed=2)
crawl: normalized 250/1200 documents
publish: upserted 250/1200 documents
publish: deleted 12 stale documents
```

## Acceptance criteria

- Docker logs show work advancing during catalog discovery, fetching,
  normalization, reference resolution, upsertion, and deletion.
- Progress counts are monotonic and use the known catalog total when available.
- A caller that provides no callback has unchanged pipeline behavior.
- Unit tests cover crawler and publisher progress events; CLI tests cover their
  human-readable rendering.
