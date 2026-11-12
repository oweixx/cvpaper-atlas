"""Build a consistent CV-only snapshot, downloads and browser shards without network access."""
import csv
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import re
import unicodedata

from openpyxl import Workbook
from cv_config import ROOT, DATA, VENUES
from metadata import normalize_records, author_key, title_key as canonical_title, CALENDAR_SOURCE

from taxonomy import TOPICS, TAXONOMY, SUBTOPICS, classify
from geography import build_geography


def norm(text):
    return canonical_title(text)


def merge_records(crossref, official, dblp=None):
    papers, by_doi, by_title, by_authors = [], {}, defaultdict(list), defaultdict(list)
    for p in normalize_records((dblp or []) + crossref + official):
        if p['venue'] not in VENUES:
            raise ValueError('Unexpected venue: ' + p['venue'])
        p = dict(p)
        doi = p.get('doi', '').strip().lower()
        title_key = (p['venue'], p['year'], norm(p['title']))
        aliases = sorted(set(p.get('doi_aliases', []) + ([doi] if doi else [])))
        match = next((by_doi[d] for d in aliases if d in by_doi), None)
        if match is None:
            # Same venue/year + exact normalized title + overlapping author name;
            # different DOI publications remain distinct (journal extensions included).
            authors = {author_key(a) for a in p['authors']}
            candidates = [q for q in by_title[title_key]
                          if (not doi or not q.get('doi') or doi == q['doi'])
                          and authors & {author_key(a) for a in q['authors']}]
            if len(candidates) == 1:
                match = candidates[0]
        if match is None and not doi and set(p['sources']) & {'CVF', 'ECVA'}:
            # Title variants between accepted papers and publisher metadata:
            # require the entire author set, same edition, one unique candidate,
            # and high title similarity. Never merge two distinct DOI records.
            signature = (p['venue'], p['year'], tuple(sorted({author_key(a) for a in p['authors']})))
            candidates = [q for q in by_authors[signature] if len(signature[2]) >= 2 and SequenceMatcher(None, norm(p['title']), norm(q['title'])).ratio() >= .84]
            if len(candidates) == 1:
                match = candidates[0]
                match['title_variant'] = {'official_title': p['title'], 'official_url': p['url'], 'bibliographic_title': match['title'], 'rule': 'same edition and full author signature; unique title similarity >= 0.84'}
        if match is None:
            papers.append(p)
            by_title[title_key].append(p)
            by_authors[(p['venue'], p['year'], tuple(sorted({author_key(a) for a in p['authors']})))].append(p)
            for alias in aliases:
                by_doi[alias] = p
            continue
        if match['venue'] != p['venue']:
            raise ValueError('DOI assigned to different venues: ' + doi)
        match['sources'] = sorted(set(match['sources'] + p['sources']))
        if p.get('identity_correction'):
            match['identity_correction'] = p['identity_correction']
        for source, years in p['source_years'].items():
            match['source_years'][source] = sorted(set(match['source_years'].get(source, []) + years))
        match['doi_aliases'] = sorted(set(match.get('doi_aliases', []) + aliases))
        for field in ['doi', 'abstract', 'pdf_url']:
            if p.get(field) and not match.get(field):
                match[field] = p[field]
        for alias in match['doi_aliases']:
            by_doi[alias] = match
        if 'CVF' in p['sources'] or 'ECVA' in p['sources']:
            match['url'] = p['url']
            # DBLP already supplies ordered author IDs; do not disconnect them.
            if not match.get('author_ids'):
                match['authors'] = p['authors']
        if p.get('citation_count') is not None and match.get('citation_count') is None:
            for key in ('citation_count', 'citation_source', 'citation_updated'):
                match[key] = p.get(key)
    for p in papers:
        key = p.get('doi') or p['url']
        p['id'] = hashlib.sha256(key.encode()).hexdigest()[:20]
        p['topics'], p['subtopics'] = classify(p['title'])
    return sorted(papers, key=lambda p: (-p['year'], p['venue'], p['title'].lower()))


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def export(papers, summary):
    folder = ROOT / 'downloads'
    folder.mkdir(exist_ok=True)
    columns = ['id', 'venue', 'year', 'publication_year', 'year_basis', 'source_years', 'year_source_url', 'title', 'authors', 'topics', 'subtopics', 'doi', 'url', 'pdf_url', 'abstract', 'citation_count', 'citation_source', 'citation_updated', 'sources']
    def values(p):
        return ['; '.join(p[c]) if isinstance(p.get(c), list) else json.dumps(p[c], ensure_ascii=False) if isinstance(p.get(c), dict) else p.get(c) for c in columns]
    def safe(v):
        # Prevent spreadsheet formula execution in externally sourced titles/names.
        return "'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v
    csv_path = folder / 'cvpaper_atlas.csv.gz'
    with gzip.open(csv_path, 'wt', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for p in papers:
            writer.writerow([safe(v) for v in values(p)])
    with gzip.open(folder / 'cvpaper_atlas.jsonl.gz', 'wt', encoding='utf-8') as f:
        for p in papers:
            f.write(json.dumps(p, ensure_ascii=False) + '\n')
    book = Workbook(write_only=True)
    sheet = book.create_sheet('summary')
    for row in [('Built at', summary['built_at']), ('Papers', len(papers)), ('Citation source', 'OpenAlex preferred; Crossref fallback. Source/date recorded per paper; not Google Scholar'), ('Topics', 'Rule-based labels; may be incomplete or incorrect')]:
        sheet.append(row)
    sheet.append(['Venue', 'Papers', 'First year', 'Last year', 'With abstract', 'With citations'])
    for key, v in summary['venues'].items():
        sheet.append([key, v['count'], v['min_year'], v['max_year'], v['with_abstract'], v['with_citations']])
    for name, subset in [('papers', papers)] + [(v, [p for p in papers if p['venue'] == v]) for v in VENUES]:
        sheet = book.create_sheet(name)
        sheet.append(columns)
        for p in subset:
            sheet.append([safe(v) for v in values(p)])
    book.save(folder / 'cvpaper_atlas.xlsx')


def main():
    crossref = json.loads((DATA / 'crossref.json').read_text(encoding='utf-8'))
    official = json.loads((DATA / 'official.json').read_text(encoding='utf-8'))
    dblp = json.loads((DATA / 'dblp.json').read_text(encoding='utf-8'))
    dblp_ledger = json.loads((DATA / 'coverage_dblp.json').read_text(encoding='utf-8'))
    if len(dblp_ledger) != len(VENUES) or any(not s['complete'] for s in dblp_ledger):
        raise SystemExit('Incomplete DBLP sources')
    ledger = json.loads((DATA / 'coverage_crossref.json').read_text(encoding='utf-8'))
    if ledger['errors']:
        raise SystemExit('Incomplete Crossref sources: resolve coverage_crossref.json before publishing')
    papers = merge_records(crossref, official, dblp)
    enrichment_path = DATA / 'enrichment.json'
    if enrichment_path.exists():
        enriched = json.loads(enrichment_path.read_text(encoding='utf-8'))
        for p in papers:
            e = enriched.get(p.get('doi'))
            if e:
                p['openalex_id'] = e['openalex_id']
                if not p.get('abstract') and e.get('abstract'):
                    p['abstract'] = e['abstract']
                if e.get('citation_count') is not None:
                    p['citation_count_crossref'] = p.get('citation_count')
                    for k in ['citation_count', 'citation_source', 'citation_updated']:
                        p[k] = e[k]
                p['sources'] = sorted(set(p['sources'] + ['OpenAlex']))
                p['topics'], p['subtopics'] = classify(p['title'])
    excluded = [p for p in papers if re.search(r'^(?:editorial(?: board)?$|guest editorial\b|preface\b|foreword\b|table of contents|author index|subject index|front (?:matter|cover)|back (?:matter|cover)|correction(?:s)? (?:to|:)|errat(?:a|um)\b)', p['title'], re.I)]
    excluded_ids = {p['id'] for p in excluded}
    papers = [p for p in papers if p['id'] not in excluded_ids]
    write_json(DATA / 'excluded.json', excluded)
    if len({p['id'] for p in papers}) != len(papers):
        raise ValueError('Duplicate paper identities')
    groups = {v: [p for p in papers if p['venue'] == v] for v in VENUES}
    if any(not rows for rows in groups.values()):
        raise ValueError('A configured venue has no papers')
    summary = {'built_at': datetime.now(timezone.utc).isoformat(), 'total': len(papers),
               'min_year': min(p['year'] for p in papers), 'max_year': max(p['year'] for p in papers),
               'with_abstract': sum(bool(p.get('abstract')) for p in papers),
               'with_citations': sum(p.get('citation_count') is not None for p in papers),
               'with_pdf': sum(bool(p.get('pdf_url')) for p in papers),
               'with_doi': sum(bool(p.get('doi')) for p in papers),
               'venues': {}, 'topics': list(TOPICS) + ['Other / Unclassified'], 'subtopics': SUBTOPICS + ['Other / Unclassified'], 'taxonomy': {k: list(v) for k, v in TAXONOMY.items()}, 'calendar_source': CALENDAR_SOURCE,
               'coverage_note': 'All main-venue records returned by DBLP SPARQL, discovered official listings, and exact Crossref containers/journal ISSNs. Indexed-source coverage is audited; this is not a guarantee that every published paper is indexed. Workshops and Findings are excluded.',
               'citation_note': 'OpenAlex citation counts where an exact DOI match exists; Crossref deposited-reference counts otherwise. Sources differ and are labeled per paper. N/A means unavailable; zero means the source returned zero. These are not Google Scholar counts.',
               'topic_note': 'Multi-label keyword rules on titles only, applied consistently across venues with different abstract coverage. 10 broad areas and 30 subtopics; not official tracks. Percentages use papers as the denominator, so topic shares may sum above 100%.'}
    for venue, rows in groups.items():
        counts = Counter(p['year'] for p in rows)
        summary['venues'][venue] = {**VENUES[venue], 'count': len(rows), 'min_year': min(counts), 'max_year': max(counts),
                                   'years': dict(sorted(counts.items())), 'with_abstract': sum(bool(p.get('abstract')) for p in rows),
                                   'with_citations': sum(p.get('citation_count') is not None for p in rows)}
        write_json(DATA / (venue.lower() + '.json'), rows)
    write_json(DATA / 'summary.json', summary)
    enrichment_ledger = json.loads((DATA / 'coverage_enrichment.json').read_text(encoding='utf-8')) if (DATA / 'coverage_enrichment.json').exists() else None
    write_json(DATA / 'coverage.json', {'dblp': dblp_ledger, 'crossref': ledger, 'openalex': enrichment_ledger, 'official': json.loads((DATA / 'coverage_official.json').read_text(encoding='utf-8')), 'excluded_nonpapers': len(excluded)})
    corrections = [{'id': p['id'], 'venue': p['venue'], 'title': p['title'], 'year': p['year'], 'source_years': p['source_years'], 'basis': p['year_basis'], 'evidence_url': p['year_source_url']} for p in papers if any(y != p['year'] for years in p['source_years'].values() for y in years)]
    write_json(DATA / 'year_audit.json', {'calendar_source': CALENDAR_SOURCE, 'corrections': corrections})
    write_json(DATA / 'identity_audit.json', [{'id': p['id'], 'venue': p['venue'], 'year': p['year'], 'doi': p['doi'], 'doi_correction': p.get('identity_correction'), 'title_variant': p.get('title_variant')} for p in papers if p.get('identity_correction') or p.get('title_variant')])
    write_json(DATA / 'geography.json', build_geography(papers))
    export(papers, summary)
    template = (ROOT / 'pipeline' / 'site.html').read_text(encoding='utf-8').replace('<!-- ANALYTICS -->', (ROOT / 'pipeline' / 'analytics.html').read_text(encoding='utf-8'))
    for name in ['index.html', 'explorer.html', 'by_year.html', 'coauthor_network.html', 'research_areas.html', 'global_research.html', 'dataset_preview.html']:
        (ROOT / name).write_text(template, encoding='utf-8')
    from write_docs import write_docs
    write_docs()
    print(json.dumps({k: v for k, v in summary.items() if k not in ('venues', 'topics')}, indent=2))
    print('Venue counts:', {v: len(p) for v, p in groups.items()})


if __name__ == '__main__':
    main()
