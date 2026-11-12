"""Validate the published corpus, coverage totals, links and export consistency."""
import csv
import gzip
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
from cv_config import ROOT, DATA, VENUES


def main():
    summary = json.loads((DATA / 'summary.json').read_text(encoding='utf-8'))
    ids, dois, papers = set(), set(), []
    for venue in VENUES:
        rows = json.loads((DATA / (venue.lower() + '.json')).read_text(encoding='utf-8'))
        assert len(rows) == summary['venues'][venue]['count'], venue
        assert {str(k): v for k, v in Counter(p['year'] for p in rows).items()} == summary['venues'][venue]['years'], venue
        for p in rows:
            assert p['venue'] == venue and p['title'] and p['authors'], p
            assert p['id'] not in ids, p['id']
            ids.add(p['id'])
            if p.get('doi'):
                assert p['doi'] not in dois, p['doi']
                dois.add(p['doi'])
            assert urlsplit(p['url']).scheme in ('http', 'https'), p['url']
            assert VENUES[venue]['since'] <= p['year'] <= summary['max_year'], p['year']
            assert set(p['sources']) <= {'DBLP', 'CVF', 'ECVA', 'Crossref', 'OpenAlex'}, p['sources']
            assert p['citation_count'] is None or isinstance(p['citation_count'], int) and p['citation_count'] >= 0
            if p['citation_count'] is not None:
                assert p['citation_source'] and p['citation_updated']
        papers.extend(rows)
    assert len(papers) == summary['total']
    assert sum(bool(p['abstract']) for p in papers) == summary['with_abstract']
    assert sum(p['citation_count'] is not None for p in papers) == summary['with_citations']
    coverage = json.loads((DATA / 'coverage.json').read_text(encoding='utf-8'))
    assert not coverage['crossref']['errors']
    if coverage.get('openalex'):
        assert not coverage['openalex']['errors'], 'Incomplete enrichment requests'
    for source in coverage['dblp'] + coverage['crossref']['sources']:
        if 'expected' in source:
            assert source['complete'] and source['retrieved'] == source['expected'], source
    with gzip.open(ROOT / 'downloads' / 'cvpaper_atlas.csv.gz', 'rt', encoding='utf-8-sig', newline='') as f:
        assert sum(1 for _ in csv.DictReader(f)) == len(papers)
    for path in ROOT.glob('*.html'):
        soup = BeautifulSoup(path.read_text(encoding='utf-8'), 'lxml')
        for node in soup.select('[src],a[href],link[href]'):
            link = node.get('src') or node.get('href', '')
            if not link or link.startswith(('http:', 'https:', 'data:', '#', '?', 'mailto:')):
                continue
            target = (ROOT / link.split('?')[0].split('#')[0]).resolve()
            assert target.is_relative_to(ROOT) and target.exists(), (path, link)
    for path in ROOT.rglob('*'):
        if path.is_file() and '.git' not in path.parts and '.cache' not in path.parts:
            assert path.stat().st_size < 100 * 1024 * 1024, f'GitHub oversized file: {path}'
    print(f'PASS: {len(papers):,} CV papers; identities, coverage, CSV and local links agree.')


if __name__ == '__main__':
    main()
