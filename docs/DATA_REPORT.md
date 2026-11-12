# Collection report — 2026-11-12

## Scope and results

- Published corpus: **73,522** records, **1979–2026**.
- Abstracts: **53,251 (72.4%)**.
- Citation counts: **69,392 (94.4%)**.
- Direct public PDF links: **42,239**; no PDFs are redistributed.
- DOI-bearing records: **69,397**. DOI-less official papers remain searchable.

| Venue | Years | Papers | Abstracts | Citations |
|---|---:|---:|---:|---:|
| CVPR | 1988–2026 | 28,493 | 85.6% | 85.7% |
| ICCV | 1988–2025 | 11,679 | 94.8% | 99.8% |
| ECCV | 1990–2026 | 12,018 | 0.3% | 100.0% |
| WACV | 1992–2026 | 6,338 | 99.1% | 99.8% |
| TPAMI | 1979–2026 | 11,060 | 98.9% | 99.7% |
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

Topic labels use title-only keyword heuristics (10 areas / 30 subtopics) consistently across venues. They are multi-label, not official conference tracks. Percentages use selected papers as the denominator.

## Calendar and identity correction

The original snapshot incorrectly retained DBLP publication years after matching conference editions. ECCV 2024 papers published in 2025 are now grouped under the 2024 event. 4,025 merged records retain differing source-year observations in `data/year_audit.json`. Calendar validation rejects off-year ECCV and non-edition ICCV records, preserving historical ICCV even-year events.

ECVA 2018 BibTeX author lists and whitespace in ECVA DOI links are normalized before identity matching. Conservative title-variant matches and corrected erroneous official DOI links are logged in `data/identity_audit.json`. Distinct DOI publications remain distinct.

## Geographic coverage

69,272 corpus records match the affiliation snapshot; 67,913 (92.4%) have at least one known country/region. 90,759 unique OpenAlex author IDs have a known affiliation country. Request completion: True.

Country means work-time affiliation, not nationality. Cross-country counts overlap. Unknown affiliations remain unknown. Institutional matching, headquarters locations, author disambiguation, uneven coverage over time, and the list API's first-100-authorship limit can affect statistics. The interface reports coverage for the selected period/venue and per year. It does not infer a country from names. The public-domain basemap is Natural Earth.

## Reproduction

Normalized source snapshots, per-venue browser shards and the query ledger are committed. Raw HTTP caches are excluded. Run the commands in the repository README to collect again or rebuild offline. A rebuild timestamp does not imply that cached citations were freshly queried.
