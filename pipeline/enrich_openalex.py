"""Enrich exact DOI matches with OpenAlex abstracts and citation counts.

Uses batches of 100 DOIs, cached responses and at most 4 requests/second. Set
OPENALEX_API_KEY for a dedicated quota; keys are never written into provenance.
Unknown values remain null. Unmatched DOIs are reported, not title-guessed.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
import threading
import time
from urllib.parse import urlencode

import requests
from cv_config import ROOT, DATA, CACHE, VENUES

RATE = threading.Lock()
NEXT = 0.0
REFRESH = False


def reconstruct(index):
    if not index:
        return ''
    pairs = [(position, word) for word, positions in index.items() for position in positions]
    return ' '.join(word for _, word in sorted(pairs))


def batch(dois):
    global NEXT
    params = {'filter': 'doi:' + '|'.join(dois), 'per-page': 100,
              'select': 'id,doi,title,cited_by_count,abstract_inverted_index'}
    public_url = 'https://api.openalex.org/works?' + urlencode(params)
    path = CACHE / ('oa-' + hashlib.sha256(public_url.encode()).hexdigest() + '.json')
    if path.exists() and not REFRESH:
        data = json.loads(path.read_text(encoding='utf-8'))
    else:
        if os.environ.get('OPENALEX_API_KEY'):
            params['api_key'] = os.environ['OPENALEX_API_KEY']
        for attempt in range(5):
            with RATE:
                time.sleep(max(0, NEXT-time.monotonic()))
                NEXT = time.monotonic() + .26
            response = requests.get('https://api.openalex.org/works', params=params, timeout=60)
            if response.status_code in (401, 402, 403):
                raise RuntimeError(f'OpenAlex access/quota unavailable (HTTP {response.status_code}); set OPENALEX_API_KEY and retry')
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(30, 2 ** (attempt+1)))
                continue
            if response.status_code != 200:
                raise RuntimeError(f'OpenAlex HTTP {response.status_code}')
            data = response.json()
            path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            break
        else:
            raise RuntimeError('OpenAlex retry budget exhausted')
    date = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()
    enriched, mismatches = {}, []
    allowed = set(dois)
    for work in data['results']:
        doi = (work.get('doi') or '').lower().removeprefix('https://doi.org/').removeprefix('http://doi.org/')
        if doi not in allowed:
            # OpenAlex sometimes resolves a requested DOI to another publication's
            # canonical DOI. Never assign that work's abstract/count by position.
            mismatches.append(doi)
            continue
        enriched[doi] = {'openalex_id': work['id'], 'abstract': reconstruct(work.get('abstract_inverted_index')),
                         'citation_count': work.get('cited_by_count'), 'citation_source': 'OpenAlex',
                         'citation_updated': date, 'title': work.get('title', '')}
    return enriched, {'url': public_url, 'requested': len(dois), 'matched': len(enriched), 'rejected_doi_mismatches': mismatches, 'retrieved_at': date, 'complete': True}


def main():
    global REFRESH
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    REFRESH = parser.parse_args().refresh
    rows = [p for v in VENUES for p in json.loads((DATA/(v.lower()+'.json')).read_text(encoding='utf-8'))]
    dois = sorted({p['doi'] for p in rows if p.get('doi')})
    groups = [dois[i:i+100] for i in range(0, len(dois), 100)]
    enriched, ledger, errors = {}, [], []
    CACHE.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(batch, group): i for i, group in enumerate(groups)}
        for future in concurrent.futures.as_completed(jobs):
            try:
                records, report = future.result()
                enriched.update(records)
                ledger.append(report)
            except Exception as exc:
                errors.append({'batch': jobs[future], 'error': str(exc)})
                print('Enrichment error:', str(exc), flush=True)
            if len(ledger) % 20 == 0 or len(ledger)+len(errors) == len(groups):
                print(f'OpenAlex {len(ledger)+len(errors)}/{len(groups)} batches; {len(enriched)} DOI matches', flush=True)
                (DATA/'enrichment.json').write_text(json.dumps(enriched, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
                (DATA/'coverage_enrichment.json').write_text(json.dumps({'requested_dois': len(dois), 'matched_dois':len(enriched), 'batches': ledger, 'errors': errors}, indent=2), encoding='utf-8')
    if errors:
        raise SystemExit(f'{len(errors)} enrichment batches unavailable; cached successes are preserved')


if __name__ == '__main__':
    main()
