"""Regression tests for source scope, publication identity and missing metadata."""
import unittest
from build_cv import merge_records
from collect_cv import classify_container, crossref_record, parse_listing
from enrich_openalex import reconstruct


def paper(**overrides):
    return {'venue': 'CVPR', 'year': 2024, 'title': 'A real research paper', 'authors': ['Alice Smith'],
            'doi': '', 'url': 'https://example.org/paper', 'pdf_url': '', 'abstract': '',
            'citation_count': None, 'citation_source': None, 'citation_updated': None,
            'sources': ['CVF'], **overrides}


class ScopeTests(unittest.TestCase):
    def test_exclude_related_conferences_and_tracks(self):
        for title in ['2026 7th International Conference on Computer Vision, Image and Deep Learning (CVIDL)',
                      'Advances in Computer Vision and Pattern Recognition',
                      'Energy Minimization Methods in Computer Vision and Pattern Recognition',
                      '2025 IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops (CVPRW)',
                      '2026 IEEE/CVF Conference on Computer Vision and Pattern Recognition- FINDINGS Track (CVPRF)',
                      'Computer Vision – ECCV 2024 Workshops']:
            with self.subTest(title=title):
                self.assertIsNone(classify_container(title))

    def test_historical_wacv_is_a_main_venue(self):
        self.assertEqual(classify_container('2007 IEEE Workshop on Applications of Computer Vision (WACV)'), 'WACV')
        self.assertIsNone(classify_container('2025 IEEE/CVF Winter Conference on Applications of Computer Vision Workshops (WACVW)'))

    def test_undated_proceedings_use_edition_year(self):
        work = {'DOI': '10.1109/CVPR.2005.1', 'title': ['A paper'], 'author': [{'family': 'Alice Smith'}],
                'type': 'proceedings-article', 'container-title': ["2005 IEEE Computer Society Conference on Computer Vision and Pattern Recognition (CVPR'05)"]}
        self.assertEqual(crossref_record(work, 'CVPR')['year'], 2005)

    def test_official_record_without_doi_survives(self):
        markup = '<dl><dt class="ptitle"><a href="/paper.html">Test &amp; Learn</a></dt><dd><input name="query_author" value="Alice Smith"></dd><dd><a href="/paper.pdf">pdf</a></dd></dl>'
        p = parse_listing(markup, 'https://openaccess.thecvf.com/CVPR2024', 'CVPR', 2024)[0]
        self.assertEqual(p['title'], 'Test & Learn')
        self.assertEqual(p['doi'], '')
        self.assertEqual(p['pdf_url'], 'https://openaccess.thecvf.com/paper.pdf')
        self.assertIsNone(p['citation_count'])


class IdentityTests(unittest.TestCase):
    def test_openalex_abstract_positions_and_missing_abstract(self):
        self.assertEqual(reconstruct({'vision': [1, 3], 'Computer': [0], 'and': [2]}), 'Computer vision and vision')
        self.assertEqual(reconstruct(None), '')

    def test_missing_doi_merges_with_matching_official_record(self):
        cr = paper(doi='10.1/test', sources=['Crossref'], citation_count=0, citation_source='Crossref')
        official = paper(title='A real research paper.', pdf_url='https://example.org/a.pdf')
        result = merge_records([cr], [official])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['citation_count'], 0)
        self.assertEqual(result[0]['pdf_url'], official['pdf_url'])
        self.assertEqual(result[0]['sources'], ['CVF', 'Crossref'])

    def test_journal_extension_and_different_dois_remain_distinct(self):
        result = merge_records([paper(doi='10.1/a'), paper(doi='10.1/b'), paper(doi='10.1/c', venue='TPAMI')], [])
        self.assertEqual(len(result), 3)

    def test_author_conflict_does_not_merge(self):
        result = merge_records([paper(doi='10.1/a')], [paper(authors=['Bob Jones'], url='https://example.org/b')])
        self.assertEqual(len(result), 2)

    def test_dblp_author_order_and_alternate_doi_identity(self):
        base = paper(doi='10.1/a', doi_aliases=['10.1/a', '10.1/b'], sources=['DBLP'], authors=['Bob', 'Alice'])
        result = merge_records([paper(doi='10.1/b', citation_count=17, citation_source='Crossref', sources=['Crossref'])], [], [base])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['authors'], ['Bob', 'Alice'])
        self.assertEqual(result[0]['citation_count'], 17)

    def test_unavailable_citations_are_not_zero(self):
        self.assertIsNone(merge_records([], [paper()])[0]['citation_count'])


if __name__ == '__main__':
    unittest.main()
