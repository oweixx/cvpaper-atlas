"""Harvest main venues through DBLP's official SPARQL service (not its search API).

Preserves author order and researcher IDs from AuthorSignature. Each venue's distinct
publication count is checked against the complete paginated result before saving.
"""
import argparse
import json
import re
from urllib.parse import urlencode
import collect_cv
from collect_cv import fetch, retrieval_date, TODAY, YEAR
from cv_config import DATA, VENUES

PREFIX = 'PREFIX dblp: <https://dblp.org/rdf/schema#>\n'
ENDPOINT = 'https://sparql.dblp.org/sparql'
STREAMS = {'CVPR': 'conf/cvpr', 'ICCV': 'conf/iccv', 'ECCV': 'conf/eccv', 'WACV': 'conf/wacv', 'TPAMI': 'journals/pami', 'IJCV': 'journals/ijcv'}


def query(text):
    url = ENDPOINT + '?' + urlencode({'query': PREFIX + text, 'format': 'json'})
    return fetch(url, True)['results']['bindings'], url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    collect_cv.REFRESH = parser.parse_args().refresh
    all_records, ledger = [], []
    for venue, stream in STREAMS.items():
        condition = ''
        if VENUES[venue]['kind'] == 'conference':
            condition = f'FILTER(?label = "{venue}" || STRSTARTS(?label, "{venue} (") && REGEX(?label, "[0-9]+[)]$"))'
            if venue == 'WACV':
                condition = 'FILTER(?label = "WACV" || ?label = "WACV/MOTION")'
        base = f'''?p dblp:publishedInStream <https://dblp.org/streams/{stream}>;
                     dblp:title ?title; dblp:yearOfPublication ?year; dblp:publishedIn ?label; dblp:authoredBy ?author .
                     FILTER(STR(?year) >= "{VENUES[venue]['since']}" && STR(?year) <= "{YEAR}") {condition}'''
        counts, count_url = query('SELECT (COUNT(DISTINCT ?p) AS ?count) WHERE {' + base + '}')
        expected = int(counts[0]['count']['value'])
        rows, offset, dates = {}, 0, []
        while len(rows) < expected:
            sparql = '''SELECT ?p ?title ?year
                (GROUP_CONCAT(DISTINCT STR(?doi); separator="|") AS ?dois)
                (GROUP_CONCAT(DISTINCT CONCAT(STR(?ordinal),"~",STR(?creator),"~",?name); separator="|") AS ?authors)
                WHERE {''' + base + '''
                    ?p dblp:hasSignature ?signature .
                    ?signature a dblp:AuthorSignature; dblp:signatureCreator ?creator;
                        dblp:signatureDblpName ?name; dblp:signatureOrdinal ?ordinal .
                    OPTIONAL { ?p dblp:doi ?doi }
                } GROUP BY ?p ?title ?year ORDER BY ?p LIMIT 5000 OFFSET ''' + str(offset)
            bindings, url = query(sparql)
            dates.append(retrieval_date(url))
            if not bindings:
                break
            for b in bindings:
                parts = sorted([a.split('~', 2) for a in b['authors']['value'].split('|')], key=lambda a: int(a[0]))
                authors = [re.sub(r'\s+\d{4}$', '', a[2]) for a in parts]
                dois = sorted(set(d.lower().replace('https://doi.org/', '').replace('http://doi.org/', '') for d in b.get('dois', {}).get('value', '').split('|') if d))
                doi = dois[0] if dois else ''
                key = b['p']['value']
                rows[key] = {'venue': venue, 'year': int(b['year']['value']), 'title': b['title']['value'].rstrip('.'),
                             'authors': authors, 'author_ids': [{'name': name, 'id': a[1]} for name, a in zip(authors, parts)],
                             'doi': doi, 'doi_aliases': dois, 'dblp_key': key.removeprefix('https://dblp.org/rec/'),
                             'url': 'https://doi.org/' + doi if doi else key, 'pdf_url': '', 'abstract': '',
                             'citation_count': None, 'citation_source': None, 'citation_updated': None,
                             'sources': ['DBLP'], 'source_url': key}
            offset += len(bindings)
            print(f'DBLP {venue}: {len(rows)}/{expected}', flush=True)
        if len(rows) != expected:
            raise RuntimeError(f'Incomplete DBLP pagination: {venue} {len(rows)}/{expected}')
        ledger.append({'source': 'DBLP SPARQL', 'venue': venue, 'stream': stream, 'url': count_url,
                       'expected': expected, 'retrieved': len(rows), 'complete': True, 'retrieved_at': min(dates), 'retrieved_through': max(dates)})
        all_records.extend(rows.values())
        DATA.mkdir(exist_ok=True)
        (DATA / 'dblp.json').write_text(json.dumps(all_records, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        (DATA / 'coverage_dblp.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
