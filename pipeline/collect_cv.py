"""Collect all discovered main proceedings and two journals from official sources.

python pipeline/collect_cv.py [--refresh]
Raw responses are cached by URL; normalized snapshots and a coverage ledger are tracked.
Crossref exact-container cursor totals are audited, never inferred from a search page.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import html
import json
import re
import threading
import time
import sys
from urllib.parse import urljoin, urlencode

import requests
from bs4 import BeautifulSoup
from cv_config import CACHE, DATA, VENUES
from metadata import normalize_doi, parse_author_text

TODAY = datetime.now(timezone.utc).date().isoformat()
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
YEAR = int(TODAY[:4])
REFRESH = False
LOCK = threading.Lock()
NEXT_REQUEST = 0.0
LEDGER = []
ERRORS = []


def fetch(url, is_json=False):
    global NEXT_REQUEST
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ('.json' if is_json else '.html'))
    if path.exists() and not REFRESH:
        content = path.read_text(encoding='utf-8')
        return json.loads(content) if is_json else content
    for attempt in range(6):
        # Crossref public-pool concurrency stays at one request and <= 2 requests/s.
        lock = LOCK if 'api.crossref.org' in url else threading.Lock()
        try:
            with lock:
                if 'api.crossref.org' in url:
                    time.sleep(max(0, NEXT_REQUEST - time.monotonic()))
                response = requests.get(url, headers={'User-Agent': 'CVPaperAtlas/1.0 (public research metadata)'}, timeout=90)
                NEXT_REQUEST = time.monotonic() + 0.6
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(40, float(response.headers.get('Retry-After', 2 ** (attempt + 1)))))
                continue
            response.raise_for_status()
            response.encoding = 'utf-8'
            content = response.text
            if is_json:
                result = response.json()
            else:
                if 'Making sure you' in content[:1000]:
                    raise RuntimeError('Source returned an automated-access challenge')
                result = content
            path.write_text(content, encoding='utf-8')
            return result
        except (requests.RequestException, ValueError) as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in (400, 401, 403, 404):
                raise
            if attempt == 5:
                raise
            time.sleep(min(30, 2 ** attempt))
    raise RuntimeError('Retries exhausted: ' + url)


def clean(value):
    return re.sub(r'\s+', ' ', html.unescape(BeautifulSoup(str(value or ''), 'lxml').get_text(' '))).strip()


def retrieval_date(url, is_json=True):
    path = CACHE / (hashlib.sha256(url.encode()).hexdigest() + ('.json' if is_json else '.html'))
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()


def classify_container(title):
    t = title.lower()
    if 'findings' in t or 'demonstration' in t:
        return None
    # The original WACV editions were named "Workshop on Applications...".
    if ('applications of computer vision' in t or re.search(r'\bwacv\b', t)):
        return None if ('wacvw' in t or re.search(r'\(wacv\).*workshop|\(wacv\s+workshops?\)', t) or 'conference on applications of computer vision workshops' in t) else 'WACV'
    if 'workshop' in t or re.search(r'\b(?:cvprw|iccvw)\b', t):
        return None
    if 'conference on computer vision and pattern recognition' in t or 'computer vision and pattern recognition conference' in t or re.fullmatch(r'cvpr \d{4}', t):
        return 'CVPR'
    if re.match(r'^computer vision\s*[-–—]\s*eccv\b', t):
        return 'ECCV'
    if (re.search(r'\biccv\b', t) or 'international conference on computer vision' in t) and not any(x in t for x in ['theory', 'image and deep', 'cvidl']):
        return 'ICCV'
    return None


def crossref_url(params, issn=None):
    base = 'https://api.crossref.org/' + (f'journals/{issn}/works' if issn else 'works')
    return base + '?' + urlencode(params)


def discover_containers():
    found = {}
    # Separate decades avoid the 1000-facet cap hiding small early proceedings.
    for query in ['CVPR', 'Computer Vision and Pattern Recognition', 'ICCV', 'WACV', 'Applications of Computer Vision', 'ECCV']:
        for date_filter in ['', 'from-pub-date:1979-01-01,until-pub-date:1999-12-31', 'from-pub-date:2000-01-01,until-pub-date:2012-12-31']:
            params = {'query.container-title': query, 'rows': 0, 'facet': 'container-title:*'}
            if date_filter:
                params['filter'] = date_filter
            url = crossref_url(params)
            message = fetch(url, True)['message']
            facets = message.get('facets', {}).get('container-title', {}).get('values', {})
            for title in facets:
                venue = classify_container(title)
                if venue:
                    found[title] = venue
            LEDGER.append({'source': 'Crossref discovery', 'url': url, 'facet_count': len(facets), 'facet_limit_reached': len(facets) >= 1000, 'retrieved_at': retrieval_date(url)})
    DATA.mkdir(exist_ok=True)
    (DATA / 'containers.json').write_text(json.dumps(found, ensure_ascii=False, indent=2), encoding='utf-8')
    return found


def crossref_record(work, venue):
    title = clean((work.get('title') or [''])[0])
    authors = [clean(' '.join(filter(None, [a.get('given'), a.get('family')])) or a.get('name', '')) for a in work.get('author', [])]
    authors = [a for a in authors if a]
    if not title or not authors or work.get('type') not in ('proceedings-article', 'journal-article', 'book-chapter'):
        return None
    if re.search(r'^(?:\[?front (?:matter|cover)|back (?:matter|cover)|table of contents|author index|subject index|copyright|editorial board|message from|reviewers\b|preface\b|errat(?:a|um)\b|correction (?:to|:))', title, re.I):
        return None
    date = (work.get('published') or work.get('published-print') or work.get('published-online') or work.get('issued') or {}).get('date-parts', [[0]])[0]
    year = date[0] if date else 0
    container = (work.get('container-title') or [''])[0]
    if VENUES[venue]['kind'] == 'conference':
        match = re.search(r'\b(19\d{2}|20\d{2})\b', container)
        if match:
            year = int(match[1])
        elif re.search(r'\b(19\d{2}|20\d{2})\b', work.get('DOI', '')):
            year = int(re.search(r'\b(19\d{2}|20\d{2})\b', work['DOI'])[1])
        elif venue == 'ECCV' and re.search(r'eccv\s*[\u2019\x27]?\s*(9\d)\b', container, re.I):
            year = 1900 + int(re.search(r'eccv\s*[\u2019\x27]?\s*(9\d)\b', container, re.I)[1])
    if year < VENUES[venue]['since'] or year > YEAR:
        return None
    doi = work.get('DOI', '').lower().strip()
    return {'venue': venue, 'year': year, 'title': title, 'authors': authors, 'doi': doi,
            'url': 'https://doi.org/' + doi if doi else work.get('URL', ''), 'pdf_url': '',
            'abstract': clean(work.get('abstract')), 'citation_count': work.get('is-referenced-by-count'),
            'citation_source': 'Crossref' if work.get('is-referenced-by-count') is not None else None,
            'citation_updated': TODAY if work.get('is-referenced-by-count') is not None else None,
            'sources': ['Crossref'], 'source_url': work.get('URL', ''), 'container_title': container}


def collect_crossref(title, venue, issn=None):
    params = {'rows': 1000, 'cursor': '*', 'select': 'DOI,title,author,published,published-print,published-online,issued,type,container-title,abstract,is-referenced-by-count,URL'}
    # An upper publication-date filter silently removes undated historical records.
    search_mode = not issn and ',' in title
    if search_mode:
        # Crossref's filter grammar reserves commas. Discover the exact title count
        # with facets, then retain only exact-title hits from the ranked query.
        edition = re.search(r'\b(?:19|20)\d{2}\b', title)
        params['query.container-title'] = venue + (' ' + edition[0] if edition else '')
        params['filter'] = 'prefix:10.1109'
        params['sort'] = 'score'
        params['order'] = 'desc'
        totals_url = crossref_url({'query.container-title': venue, 'rows': 0, 'facet': 'container-title:*'})
        facet_total = fetch(totals_url, True)['message'].get('facets', {}).get('container-title', {}).get('values', {}).get(title)
        if facet_total is None:
            raise RuntimeError('Cannot verify exact container total: ' + title)
    elif not issn:
        params['filter'] = 'container-title:' + title
    records, seen, received, retrieved_dates = [], set(), 0, []
    first_url, total = '', None
    pages_read = 0
    while True:
        pages_read += 1
        if search_mode and pages_read > 10:
            raise RuntimeError(f'Exact container search incomplete after 10 pages: {received}/{total} {title}')
        url = crossref_url(params, issn)
        first_url = first_url or url
        message = fetch(url, True)['message']
        fetched_at = retrieval_date(url)
        retrieved_dates.append(fetched_at)
        if total is None:
            total = facet_total if search_mode else message['total-results']
            if total is None:
                raise RuntimeError('Cannot verify exact container total: ' + title)
        works = message.get('items', [])
        if not works:
            break
        for work in works:
            if search_mode and title not in work.get('container-title', []):
                continue
            key = work.get('DOI')
            if key in seen:
                continue
            seen.add(key)
            received += 1
            # Exact container filtering is checked again locally.
            if not issn and title not in work.get('container-title', []):
                raise ValueError('Crossref returned unexpected container')
            record = crossref_record(work, venue)
            if record:
                if record['citation_count'] is not None:
                    record['citation_updated'] = fetched_at
                records.append(record)
        if received >= total:
            break
        nxt = message.get('next-cursor')
        if not nxt or nxt == params['cursor']:
            raise RuntimeError(f'Cursor stalled at {received}/{total}: {title}')
        params['cursor'] = nxt
    ledger = {'source': 'Crossref', 'venue': venue, 'container': title, 'url': first_url,
              'expected': total, 'retrieved': received, 'retained': len(records), 'complete': received == total,
              'retrieved_at': min(retrieved_dates), 'retrieved_through': max(retrieved_dates)}
    LEDGER.append(ledger)
    if received != total:
        ERRORS.append(ledger)
    print(f'Crossref {venue}: {len(records)} papers ({received}/{total}) {title}', flush=True)
    return records


def parse_listing(content, base, venue, year):
    soup = BeautifulSoup(content, 'lxml')
    records = []
    for dt in soup.select('dt.ptitle'):
        a = dt.find('a', href=True)
        if not a:
            continue
        url = urljoin(base, a['href'])
        actual_year = year
        if venue == 'ECCV':
            match = re.search(r'eccv[_/](\d{4})', url, re.I)
            if not match:
                continue
            actual_year = int(match[1])
        dd = dt.find_next_sibling('dd')
        if dd is None:
            continue
        inputs = dd.select('input[name="query_author"]')
        authors = [clean(i.get('value')) for i in inputs] if inputs else parse_author_text(clean(dd.get_text(' ', strip=True)), bibtex=venue == 'ECCV' and actual_year == 2018)
        links = []
        for sibling in dt.find_next_siblings():
            if sibling.name == 'dt':
                break
            links += sibling.find_all('a', href=True)
        pdf, doi = '', ''
        for link in links:
            target = urljoin(base, link['href'])
            if link.get_text(strip=True).lower() == 'pdf':
                pdf = target
            if 'doi.org/' in target or '/chapter/10.' in target:
                doi = normalize_doi(re.sub(r'^.*?(10\.)', r'\1', target))
        if not authors or not clean(a.get_text()):
            continue
        source = 'ECVA' if venue == 'ECCV' else 'CVF'
        records.append({'venue': venue, 'year': actual_year, 'title': clean(a.get_text()), 'authors': authors,
                        'doi': doi, 'url': url, 'pdf_url': pdf, 'abstract': '', 'citation_count': None,
                        'citation_source': None, 'citation_updated': None, 'sources': [source], 'source_url': base})
    return records


def collect_cvf():
    base = 'https://openaccess.thecvf.com/'
    home = fetch(base)
    links = BeautifulSoup(home, 'lxml').find_all('a', href=True)
    editions = {}
    for a in links:
        match = re.fullmatch(r'/?(CVPR|ICCV|WACV)(\d{4})(?:\.py)?', a['href'])
        if match:
            editions[urljoin(base, a['href'])] = (match[1], int(match[2]))
    results = []
    def collect(item):
        url, (venue, year) = item
        page_url = url + '?day=all'
        page_urls = [page_url]
        records = parse_listing(fetch(page_url), page_url, venue, year)
        if not records:
            # Legacy .py editions expose day-specific lists, not ?day=all.
            content = fetch(url)
            records = parse_listing(content, url, venue, year)
            if not records:
                days = {urljoin(url, a['href']) for a in BeautifulSoup(content, 'lxml').find_all('a', href=True) if '?day=' in a['href']}
                for day in sorted(days):
                    records.extend(parse_listing(fetch(day), day, venue, year))
                    page_urls.append(day)
        if not records:
            raise ValueError('No papers in official listing: ' + page_url)
        LEDGER.append({'source': 'CVF', 'venue': venue, 'year': year, 'url': page_url, 'pages': page_urls, 'retained': len(records), 'retrieved_at': min(retrieval_date(u, False) for u in page_urls), 'complete': True})
        print(f'CVF {venue} {year}: {len(records)}', flush=True)
        return records
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for records in pool.map(collect, editions.items()):
            results.extend(records)
    url = 'https://www.ecva.net/papers.php'
    records = parse_listing(fetch(url), url, 'ECCV', None)
    if not records:
        raise ValueError('No ECVA papers')
    results.extend(records)
    LEDGER.append({'source': 'ECVA', 'venue': 'ECCV', 'url': url, 'retained': len(records), 'retrieved_at': retrieval_date(url, False), 'complete': True})
    print(f'ECVA: {len(records)}', flush=True)
    return results


def main():
    global REFRESH
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--only', choices=['official', 'crossref'])
    args = parser.parse_args()
    REFRESH = args.refresh
    DATA.mkdir(exist_ok=True)
    if args.only != 'crossref':
        records = collect_cvf()
        (DATA / 'official.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        (DATA / 'coverage_official.json').write_text(json.dumps(LEDGER, ensure_ascii=False, indent=2), encoding='utf-8')
        LEDGER.clear()
    if args.only != 'official':
        containers = discover_containers()
        print(f'Discovered {len(containers)} conference containers', flush=True)
        records = []
        jobs = [(title, venue, None) for title, venue in sorted(containers.items())]
        jobs += [(v['name'], k, v['issn']) for k, v in VENUES.items() if 'issn' in v]
        for title, venue, issn in jobs:
            try:
                records.extend(collect_crossref(title, venue, issn))
            except Exception as exc:
                ERRORS.append({'venue': venue, 'container': title, 'error': str(exc)})
                print('FAILED', title, str(exc), flush=True)
            (DATA / 'crossref.json').write_text(json.dumps(records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            (DATA / 'coverage_crossref.json').write_text(json.dumps({'sources': LEDGER, 'errors': ERRORS}, ensure_ascii=False, indent=2), encoding='utf-8')
    if ERRORS:
        raise SystemExit(f'{len(ERRORS)} incomplete sources; see data/coverage_crossref.json')


if __name__ == '__main__':
    main()
