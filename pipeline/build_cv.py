"""Build a consistent CV-only snapshot, downloads and browser shards without network access."""
import csv
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

TOPICS = {
    'Detection & Segmentation': r'\b(detect\w*|segment\w*|panoptic|instance mask\w*)\b',
    '3D Vision': r'\b(3d|4d|nerf|gaussian splatting|point cloud\w*|depth|stereo|reconstruction|multi.view|slam|odometry|structure.from.motion)\b',
    'Vision & Language': r'\b(vision.language|visual.question|vlm\w*|multimodal|multi.modal|image.text|caption\w*|visual.grounding|large.language)\b',
    'Image & Video Generation': r'\b(diffusion|generati\w*|gan|gans|image.synthesis|video.synthesis|image.edit\w*|inpainting|text.to.image|text.to.video)\b',
    'Video & Motion': r'\b(video|tracking|optical.flow|action.recognition|motion|temporal)\b',
    'Recognition & Representation': r'\b(classification|recognition|representation|self.supervised|contrastive|few.shot|zero.shot|metric.learning|retrieval)\b',
    'Low-level Vision': r'\b(denois\w*|deblur\w*|super.resolution|restoration|enhancement|dehazing|compression|colorization|demosaic\w*)\b',
    'People & Faces': r'\b(human|face|facial|person|pose|body|hand|gesture|avatar|pedestrian)\b',
    'Robustness & Learning': r'\b(adversarial|robust\w*|domain.adaptation|domain.generalization|continual|federated|unlearning|out.of.distribution|uncertainty)\b',
    'Medical & Scientific Vision': r'\b(medical|biomedical|microscopy|histopath\w*|radiology|mri|tomography|remote.sensing|satellite)\b',
}
PATTERNS = {k: re.compile(v, re.I) for k, v in TOPICS.items()}
STOP = set('a an the in on of for with from to by and or is are this that we our using via based learning method methods approach towards toward new novel image images visual vision computer paper model models network networks deep neural efficient end framework'.split())


def norm(text):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower())


def merge_records(crossref, official, dblp=None):
    papers, by_doi, by_title = [], {}, defaultdict(list)
    for p in (dblp or []) + crossref + official:
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
            authors = {norm(a) for a in p['authors']}
            candidates = [q for q in by_title[title_key]
                          if (not doi or not q.get('doi') or doi == q['doi'])
                          and authors & {norm(a) for a in q['authors']}]
            if len(candidates) == 1:
                match = candidates[0]
        if match is None:
            papers.append(p)
            by_title[title_key].append(p)
            for alias in aliases:
                by_doi[alias] = p
            continue
        if match['venue'] != p['venue']:
            raise ValueError('DOI assigned to different venues: ' + doi)
        match['sources'] = sorted(set(match['sources'] + p['sources']))
        match['doi_aliases'] = sorted(set(match.get('doi_aliases', []) + aliases))
        for field in ['doi', 'abstract', 'pdf_url']:
            if p.get(field) and not match.get(field):
                match[field] = p[field]
        for alias in match['doi_aliases']:
            by_doi[alias] = match
        if 'CVF' in p['sources'] or 'ECVA' in p['sources']:
            match['url'] = p['url']
            match['authors'] = p['authors']
        if p.get('citation_count') is not None and match.get('citation_count') is None:
            for key in ('citation_count', 'citation_source', 'citation_updated'):
                match[key] = p.get(key)
    for p in papers:
        key = p.get('doi') or p['url']
        p['id'] = hashlib.sha256(key.encode()).hexdigest()[:20]
        p['topics'] = [label for label, pattern in PATTERNS.items() if pattern.search(p['title'] + ' ' + p.get('abstract', ''))]
        if not p['topics']:
            p['topics'] = ['Other / Unclassified']
    return sorted(papers, key=lambda p: (-p['year'], p['venue'], p['title'].lower()))


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')


def export(papers, summary):
    folder = ROOT / 'downloads'
    folder.mkdir(exist_ok=True)
    columns = ['id', 'venue', 'year', 'title', 'authors', 'topics', 'doi', 'url', 'pdf_url', 'abstract', 'citation_count', 'citation_source', 'citation_updated', 'sources']
    def values(p):
        return ['; '.join(p.get(c, [])) if isinstance(p.get(c), list) else p.get(c) for c in columns]
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
                p['topics'] = [label for label, pattern in PATTERNS.items() if pattern.search(p['title'] + ' ' + p.get('abstract', ''))] or ['Other / Unclassified']
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
               'venues': {}, 'topics': list(TOPICS) + ['Other / Unclassified'],
               'coverage_note': 'All main-venue records returned by DBLP SPARQL, discovered official listings, and exact Crossref containers/journal ISSNs. Indexed-source coverage is audited; this is not a guarantee that every published paper is indexed. Workshops and Findings are excluded.',
               'citation_note': 'OpenAlex citation counts where an exact DOI match exists; Crossref deposited-reference counts otherwise. Sources differ and are labeled per paper. N/A means unavailable; zero means the source returned zero. These are not Google Scholar counts.',
               'topic_note': 'Automatic keyword rules on titles and available abstracts; multi-label, not authoritative conference tracks.'}
    for venue, rows in groups.items():
        counts = Counter(p['year'] for p in rows)
        summary['venues'][venue] = {**VENUES[venue], 'count': len(rows), 'min_year': min(counts), 'max_year': max(counts),
                                   'years': dict(sorted(counts.items())), 'with_abstract': sum(bool(p.get('abstract')) for p in rows),
                                   'with_citations': sum(p.get('citation_count') is not None for p in rows)}
        write_json(DATA / (venue.lower() + '.json'), rows)
    write_json(DATA / 'summary.json', summary)
    enrichment_ledger = json.loads((DATA / 'coverage_enrichment.json').read_text(encoding='utf-8')) if (DATA / 'coverage_enrichment.json').exists() else None
    write_json(DATA / 'coverage.json', {'dblp': dblp_ledger, 'crossref': ledger, 'openalex': enrichment_ledger, 'official': json.loads((DATA / 'coverage_official.json').read_text(encoding='utf-8')), 'excluded_nonpapers': len(excluded)})
    counts = Counter(a for p in papers for a in set(p['authors']))
    top = set(a for a, n in counts.most_common(400))
    pairs = Counter()
    from itertools import combinations
    for p in papers:
        pairs.update(combinations(sorted(set(p['authors']) & top), 2))
    nodes = [{'id': a, 'count': counts[a]} for a in sorted(top, key=lambda a: -counts[a])]
    edges = [{'source': a, 'target': b, 'weight': n} for (a, b), n in pairs.items() if n >= 3]
    write_json(DATA / 'network.json', {'nodes': nodes, 'edges': edges, 'min_collaborations': 3, 'node_limit': 400,
                                      'note': 'Names are not disambiguated researcher IDs. Top 400 authors in this corpus; edges require at least 3 shared papers.'})
    export(papers, summary)
    template = (ROOT / 'pipeline' / 'site.html').read_text(encoding='utf-8')
    for name in ['index.html', 'explorer.html', 'by_year.html', 'coauthor_network.html', 'dataset_preview.html']:
        (ROOT / name).write_text(template, encoding='utf-8')
    from write_docs import write_docs
    write_docs()
    print(json.dumps({k: v for k, v in summary.items() if k not in ('venues', 'topics')}, indent=2))
    print('Venue counts:', {v: len(p) for v, p in groups.items()})


if __name__ == '__main__':
    main()
