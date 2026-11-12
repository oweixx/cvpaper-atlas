"""Build an auditable country/region index from work-time OpenAlex affiliations."""
import json
from cv_config import DATA


def build_geography(papers, source=None, ledger=None):
    path = DATA / 'affiliations.json'
    if source is None:
        source = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    entries = {}
    authors, known_authors = set(), set()
    matched, authorships, known_authorships, truncated = 0, 0, 0, 0
    for p in papers:
        record = next((source[d] for d in [p.get('doi')] + p.get('doi_aliases', []) if d in source), None)
        if not record:
            continue
        matched += 1
        truncated += bool(record.get('possibly_truncated'))
        countries = {}
        for author in record['authors']:
            authorships += 1
            authors.add(author['id'])
            if author['countries']:
                known_authorships += 1
                known_authors.add(author['id'])
            for country in author['countries']:
                countries.setdefault(country, []).append(author['id'])
        entries[p['id']] = {'countries': countries, 'authors': len(record['authors']),
                            'known_authors': sum(bool(a['countries']) for a in record['authors'])}
    ledger_path = DATA / 'coverage_affiliations.json'
    if ledger is None:
        ledger = json.loads(ledger_path.read_text(encoding='utf-8')) if ledger_path.exists() else {}
    return {'source': 'OpenAlex work authorships', 'papers': entries, 'collection_complete': ledger.get('complete', False),
            'coverage': {'total_papers': len(papers), 'matched_papers': matched,
                         'papers_with_country': sum(bool(e['countries']) for e in entries.values()),
                         'returned_authorships': authorships, 'authorships_with_country': known_authorships,
                         'unique_author_ids': len(authors), 'unique_author_ids_with_country': len(known_authors),
                         'possibly_truncated_papers': truncated},
            'note': 'Country/region is an OpenAlex affiliation location on a paper, not nationality. Authors are deduplicated by OpenAlex ID within each selected country and period. A paper or author may count in multiple countries; country totals are not additive. Missing affiliations are unknown. Institutional matching can be wrong (including company headquarters); no name-based country inference is used.'}
