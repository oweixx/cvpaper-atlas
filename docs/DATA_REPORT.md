# Collection report — 2026-11-12

## Scope and results

- Published corpus: **74,784** records, **1979–2026**.
- Abstracts: **53,251 (71.2%)**.
- Citation counts: **69,392 (92.8%)**.
- Direct public PDF links: **42,238**; no PDFs are redistributed.
- DOI-bearing records: **69,480**. DOI-less official papers remain searchable.

| Venue | Years | Papers | Abstracts | Citations |
|---|---:|---:|---:|---:|
| CVPR | 1988–2026 | 28,713 | 85.0% | 85.1% |
| ICCV | 1988–2025 | 11,824 | 93.6% | 98.6% |
| ECCV | 1990–2026 | 12,877 | 0.3% | 93.3% |
| WACV | 1992–2026 | 6,368 | 98.7% | 99.4% |
| TPAMI | 1979–2026 | 11,068 | 98.8% | 99.6% |
| IJCV | 1987–2026 | 3,934 | 13.3% | 100.0% |

## Audited sources

- DBLP SPARQL: 72,680 records from 6 streams; every expected distinct-publication total equals the downloaded total. Only main-conference labels and the two journal labels are included.
- CVF and ECVA: 42,240 official-list records. Legacy CVF day lists are followed when no all-papers page exists.
- Crossref: 99 exact proceedings/ISSN collections, 69,513 raw DOI records; all expected totals equal retrieved totals. Front matter, invalid dates and other non-paper records are excluded.
- OpenAlex: 69,480 DOI lookups in 695 batches; 69,272 exact matches. 35 returned canonical-DOI mismatches were rejected.
- 161 additional editorial/front-matter records were excluded at build time; see `data/excluded.json`.

## Limits

The source audit verifies collection of indexed records, not that every historically published paper has been indexed. OpenAlex and Crossref count different citation graphs; their values are labeled per paper. Current-year indexing and DOI assignment lag publication. Missing abstracts and citation counts are preserved as missing.

DBLP's ordinary search endpoint returned an automated-access challenge. Its separate official SPARQL service worked and was used for the complete indexed corpus. Semantic Scholar's unauthenticated endpoint returned HTTP 429 and is not used for this snapshot. The CVPR 2026 virtual programme's advertised pagination API returned HTTP 403; that incomplete feed was not imported. Official CVF main-conference entries are still included.

Topic labels are keyword heuristics. The graph aggregates author names, so namesakes can be conflated; DBLP author IDs are retained in the underlying records where available.

## Reproduction

Normalized source snapshots, per-venue browser shards and the query ledger are committed. Raw HTTP caches are excluded. Run the commands in the repository README to collect again or rebuild offline. A rebuild timestamp does not imply that cached citations were freshly queried.
