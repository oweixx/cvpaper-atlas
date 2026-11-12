"""Regression tests for source scope, publication identity and missing metadata."""
import unittest
from build_cv import merge_records
from collect_cv import classify_container, crossref_record, parse_listing
from enrich_openalex import reconstruct
from metadata import valid_edition, normalize_doi, parse_author_text
from collect_affiliations import normalize_authorships
from geography import build_geography
from taxonomy import classify


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


class CorrectedStatisticsTests(unittest.TestCase):
    def test_eccv_publication_year_is_not_event_year(self):
        base = paper(venue='ECCV', year=2025, doi='10.1/eccv', sources=['DBLP'])
        cr = paper(venue='ECCV', year=2024, doi='10.1/eccv', sources=['Crossref'], container_title='Computer Vision - ECCV 2024')
        official = paper(venue='ECCV', year=2024, sources=['ECVA'])
        result = merge_records([cr], [official], [base])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['year'], 2024)
        self.assertEqual(result[0]['publication_year'], 2025)
        self.assertEqual(result[0]['source_years']['DBLP'], [2025])

    def test_reject_off_calendar_and_preserve_historical_iccv(self):
        self.assertFalse(valid_edition('ECCV', 2025))
        self.assertFalse(valid_edition('ICCV', 2024))
        for y in [1988, 1990, 1998, 1999, 2025]:
            self.assertTrue(valid_edition('ICCV', y))
        with self.assertRaises(ValueError):
            merge_records([], [paper(venue='ECCV', year=2025)])

    def test_ecva_bibtex_names_and_doi_whitespace_do_not_duplicate(self):
        names = parse_author_text('Yuan, Ye and Kitani, Kris M.')
        self.assertEqual(names, ['Ye Yuan', 'Kris M. Kitani'])
        base = paper(venue='ECCV', year=2018, authors=names, doi='10.1007/abc_1', sources=['DBLP'])
        official = paper(venue='ECCV', year=2018, authors=['Ye Yuan', 'Kris Kitani'], doi='https://doi.org/10.1007/abc%20_1', sources=['ECVA'])
        self.assertEqual(len(merge_records([], [official], [base])), 1)
        self.assertEqual(normalize_doi(official['doi']), base['doi'])
        self.assertEqual(parse_author_text('Ikehata, Satoshi', bibtex=True), ['Satoshi Ikehata'])

    def test_title_variant_requires_full_author_signature(self):
        base = paper(doi='10.1/a', title='Scaling Egocentric Vision: The Dataset', authors=['Dima Damen','Sanja Fidler'], sources=['DBLP'])
        official = paper(title='Scaling Egocentric Vision: The EPIC-KITCHENS Dataset', authors=['Dima Damen','Sanja Fidler'])
        merged = merge_records([], [official], [base])
        self.assertEqual(len(merged), 1)
        self.assertIn('title_variant', merged[0])
        distinct = {**official, 'authors':['Dima Damen','Other Person']}
        self.assertEqual(len(merge_records([], [distinct], [base])), 2)

    def test_official_wrong_doi_cannot_attach_to_another_title(self):
        base = paper(venue='ECCV', year=2025, doi='10.1/right', sources=['DBLP'])
        different = paper(venue='ECCV', year=2024, doi='10.1/wrong', title='A different paper', authors=['Bob Jones'], sources=['DBLP'])
        official = paper(venue='ECCV', year=2024, doi='10.1/wrong', sources=['ECVA'])
        result = merge_records([], [official], [base, different])
        matched = next(p for p in result if p['doi'] == '10.1/right')
        self.assertEqual(matched['year'], 2024)
        self.assertEqual(matched['identity_correction']['original_doi'], '10.1/wrong')
        self.assertNotIn('ECVA', next(p for p in result if p['doi']=='10.1/wrong')['sources'])

    def test_country_identity_multiple_affiliations_and_missing(self):
        work = {'authorships': [
            {'author': {'id':'https://openalex.org/A1'}, 'countries':['US'], 'institutions':[{'country_code':'KR'}]},
            {'author': {'id':'https://openalex.org/A1'}, 'countries':['US']},
            {'author': {'id':'https://openalex.org/A2'}, 'countries':[]}]}
        authors = normalize_authorships(work)
        self.assertEqual(authors, [{'id':'A1','countries':['KR','US']},{'id':'A2','countries':[]}])
        records = {'10.1/a': {'authors':authors}, '10.1/b': {'authors':authors}}
        data = build_geography([{'id':'a','doi':'10.1/a'},{'id':'b','doi':'10.1/b'},{'id':'c','doi':''}],records,{'complete':True})
        self.assertEqual(data['coverage']['papers_with_country'], 2)
        self.assertEqual(data['coverage']['unique_author_ids_with_country'], 1)
        self.assertEqual(data['coverage']['returned_authorships'], 4)
        self.assertEqual(data['papers']['a']['countries'], {'KR':['A1'],'US':['A1']})
        self.assertNotIn('c', data['papers'])

    def test_multilabel_taxonomy_uses_consistent_title_evidence(self):
        areas, details = classify('Diffusion Models for Medical Image Segmentation')
        self.assertIn('Medical & Scientific Vision', areas)
        self.assertIn('Diffusion models', details)
        self.assertIn('Segmentation', details)
        self.assertEqual(classify('A New Approach')[0], ['Other / Unclassified'])


if __name__ == '__main__':
    unittest.main()
