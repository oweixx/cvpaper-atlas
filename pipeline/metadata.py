"""Publication identity and conference-edition normalization."""
import re
import json
import unicodedata
from urllib.parse import unquote
from cv_config import DATA

CALENDAR_SOURCE = 'https://www.thecvf.com/?page_id=100'
ICCV_YEARS = {1987, 1988, 1990, 1993, 1995, 1998, 1999, *range(2001, 2100, 2)}


def valid_edition(venue, year):
    if venue == 'ECCV':
        return year >= 1990 and year % 2 == 0
    if venue == 'ICCV':
        return year in ICCV_YEARS
    return True


def normalize_doi(value):
    value = unquote(value or '').strip().lower()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value)
    return re.sub(r'\s+', '', value)


def parse_author_text(text, bibtex=False):
    # Older ECVA lists use BibTeX's "Family, Given and Family, Given" form.
    if bibtex or re.search(r'\s+and\s+', text):
        names = re.split(r'\s+and\s+', text)
        return [' '.join(reversed(n.split(',', 1))).strip() if ',' in n else n.strip() for n in names]
    return [n.strip().strip('* ') for n in text.split(',') if n.strip()]


def author_key(name):
    parts = re.findall(r'[a-z]+', unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower())
    return (parts[0][0], parts[-1]) if parts else ('', '')


def title_key(title):
    title = title.replace('&', 'and')
    title = re.sub(r'\^\s*(\d)\s+\1', r'\1', title)
    title = re.sub(r'\\circ\b|[°∘]', '', title)
    for char, word in {'ε': 'epsilon', 'α': 'alpha', 'β': 'beta', 'γ': 'gamma', 'δ': 'delta'}.items():
        title = title.replace(char, word)
    title = re.sub(r'\\(?:text|mathrm|mathbf|mathcal)\{([^}]+)\}', r'\1', title)
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode().lower())


def edition_evidence(p):
    venue = p['venue']
    if venue in ('TPAMI', 'IJCV'):
        return p['year'], 0, 'publication year', p.get('source_url', '')
    if set(p['sources']) & {'CVF', 'ECVA'}:
        return p['year'], 3, 'official conference listing', p.get('url', '')
    container = p.get('container_title', '')
    m = re.search(r'\b((?:19|20)\d{2})\b', container)
    if not m and venue == 'ECCV':
        short = re.search(r'eccv\s*[\u2019\x27]?\s*(9\d)\b', container, re.I)
        if short:
            return 1900 + int(short[1]), 2, 'proceedings title', p.get('source_url', '')
    if m:
        return int(m[1]), 2, 'proceedings title', p.get('source_url', '')
    return p['year'], 0, 'bibliographic year', p.get('source_url', '')


def normalize_records(records):
    path = DATA / 'identity_overrides.json'
    overrides = {r['official_url']: r for r in json.loads(path.read_text(encoding='utf-8'))} if path.exists() else {}
    authoritative = {}
    titles = {}
    for p in records:
        if not set(p['sources']) & {'DBLP', 'Crossref'}:
            continue
        if p.get('doi'):
            authoritative[normalize_doi(p['doi'])] = p
            titles.setdefault((p['venue'], title_key(p['title'])), []).append(p)
    editions = {}
    prepared = []
    for original in records:
        p = dict(original)
        p['doi'] = normalize_doi(p.get('doi'))
        override = overrides.get(p.get('url'))
        if override and not p['doi']:
            target = authoritative.get(override['doi'])
            if not target or (p['venue'], p['year']) != (override['venue'], override['year']) or {author_key(a) for a in p['authors']} != {author_key(a) for a in target['authors']}:
                raise ValueError('Reviewed identity override no longer matches its evidence')
            p['identity_correction'] = {'original_doi': '', 'corrected_doi': override['doi'], 'reason': override['reason'], 'source_url': override['evidence_url']}
            p['doi'] = override['doi']
        if set(p['sources']) & {'CVF', 'ECVA'} and p['doi'] in authoritative:
            target = authoritative[p['doi']]
            if title_key(target['title']) != title_key(p['title']):
                candidates = {normalize_doi(q['doi']) for q in titles.get((p['venue'], title_key(p['title'])), [])
                              if abs(q['year'] - p['year']) <= 1 and {author_key(a) for a in q['authors']} & {author_key(a) for a in p['authors']}}
                if len(candidates) == 1 and p['doi'] not in candidates:
                    corrected = next(iter(candidates))
                    p['identity_correction'] = {'original_doi': p['doi'], 'corrected_doi': corrected,
                                                'reason': 'Official DOI points to a different title; exact title and overlapping author match bibliographic record',
                                                'source_url': p.get('url')}
                    p['doi'] = corrected
        p['doi_aliases'] = sorted({normalize_doi(d) for d in p.get('doi_aliases', []) + [p['doi']] if d})
        p['source_years'] = {s: [original['year']] for s in p['sources']}
        if 'DBLP' in p['sources']:
            p['publication_year'] = original['year']
        evidence = edition_evidence(p)
        for doi in p['doi_aliases']:
            key = (p['venue'], doi)
            if evidence[1] > editions.get(key, (0, -1))[1]:
                editions[key] = evidence
            elif evidence[1] > 0 and evidence[1] == editions.get(key, (0, -1))[1] and evidence[0] != editions[key][0]:
                raise ValueError(f'Conflicting conference edition evidence: {key}')
        prepared.append(p)
    for p in prepared:
        choices = [edition_evidence(p)] + [editions[(p['venue'], d)] for d in p['doi_aliases'] if (p['venue'], d) in editions]
        year, rank, basis, url = max(choices, key=lambda x: x[1])
        if not valid_edition(p['venue'], year):
            raise ValueError(f'Unresolved off-calendar paper: {p["venue"]} {year} {p["title"]}')
        p.update(year=year, year_basis=basis, year_source_url=url)
    return prepared
