"""Fetch work-time author affiliations by exact OpenAlex ID and DOI.

Country codes describe affiliation locations, not nationality. Never infer a
country from a person's name. Responses are cached; missing records stay missing.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
import time
from urllib.parse import urlencode

import requests
from cv_config import CACHE, DATA


def normalize_authorships(work):
    authors = {}
    for a in work.get('authorships', []):
        key = (a.get('author') or {}).get('id', '')
        if not key:
            continue
        countries = set(a.get('countries') or [])
        countries.update(i.get('country_code') for i in a.get('institutions', []) if i.get('country_code'))
        authors.setdefault(key.rsplit('/', 1)[-1], set()).update(c for c in countries if isinstance(c, str) and len(c) == 2 and c.isalpha())
    return [{'id': key, 'countries': sorted(codes)} for key, codes in sorted(authors.items())]


def fetch_batch(items, refresh=False):
    params = {'filter': 'openalex:' + '|'.join(key.rsplit('/', 1)[-1] for key, _ in items),
              'per-page': 100, 'select': 'id,doi,authorships'}
    url = 'https://api.openalex.org/works?' + urlencode(params)
    path = CACHE / ('aff-' + hashlib.sha256(url.encode()).hexdigest() + '.json')
    if path.exists() and not refresh:
        result = json.loads(path.read_text(encoding='utf-8'))
    else:
        headers = {'Authorization': 'Bearer ' + os.environ['OPENALEX_API_KEY']} if os.environ.get('OPENALEX_API_KEY') else {}
        for attempt in range(5):
            response = requests.get(url, headers=headers, timeout=60)
            if response.status_code == 429:
                detail = response.text.lower()
                if any(t in detail for t in ('daily', 'budget', 'credits')):
                    raise RuntimeError('OpenAlex daily budget exhausted; resume with a verified key or after reset')
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(20, 2 ** (attempt + 1)))
                continue
            if not response.ok:
                raise RuntimeError(f'OpenAlex HTTP {response.status_code}: {response.text[:150]}')
            result = response.json()
            path.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            break
        else:
            raise RuntimeError('OpenAlex retries exhausted')
    date = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()
    expected = dict(items)
    records, rejected = {}, []
    for w in result['results']:
        doi = (w.get('doi') or '').lower().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
        if w['id'] not in expected or doi != expected[w['id']]:
            rejected.append(w['id'])
            continue
        records[doi] = {'openalex_id': w['id'], 'authors': normalize_authorships(w),
                        'returned_authorships': len(w.get('authorships', [])),
                        'possibly_truncated': len(w.get('authorships', [])) >= 100,
                        'retrieved_at': date}
    return records, {'url': url, 'requested': len(items), 'matched': len(records),
                     'rejected': rejected, 'retrieved_at': date}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    enriched = json.loads((DATA / 'enrichment.json').read_text(encoding='utf-8'))
    items = sorted({e['openalex_id']: doi for doi, e in enriched.items()}.items())
    groups = [items[i:i + 100] for i in range(0, len(items), 100)]
    CACHE.mkdir(parents=True, exist_ok=True)
    records, reports, errors = {}, [], []
    # Bounded batches stop promptly at a daily quota error instead of flooding retries.
    with ThreadPoolExecutor(max_workers=3) as pool:
        for start in range(0, len(groups), 3):
            tasks = [pool.submit(fetch_batch, g, args.refresh) for g in groups[start:start+3]]
            for i, task in enumerate(tasks):
                try:
                    data, report = task.result()
                    records.update(data)
                    reports.append(report)
                except Exception as exc:
                    errors.append({'batch': start+i, 'error': str(exc)})
            if start % 30 == 0 or errors or start+3 >= len(groups):
                ledger = {'requested_works': len(items), 'matched_works': len(records),
                          'processed_batches': len(reports), 'total_batches': len(groups),
                          'complete': len(reports) == len(groups) and not errors, 'batches': reports, 'errors': errors,
                          'source': 'OpenAlex work authorships', 'identity': 'Exact work ID and DOI',
                          'country_definition': 'Affiliation country/region on the paper; not nationality. Multi-country authors count in each country. Missing countries remain unknown.'}
                (DATA / 'affiliations.json').write_text(json.dumps(records, separators=(',', ':')), encoding='utf-8')
                (DATA / 'coverage_affiliations.json').write_text(json.dumps(ledger, indent=2), encoding='utf-8')
                print(f'Affiliations: {len(reports)}/{len(groups)} batches; {len(records)} works; errors={len(errors)}', flush=True)
            if errors:
                break
            time.sleep(.8)
    if errors:
        print('Partial coverage retained:', errors, flush=True)


if __name__ == '__main__':
    main()
