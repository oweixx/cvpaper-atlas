"""Optional browser QA: pip install -r requirements-dev.txt; playwright install chromium.

Run a local server first: python -m http.server 8765 --bind 127.0.0.1
"""
import argparse
import csv
import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright, expect
from cv_config import ROOT, DATA


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8765/')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'docs')
    args = parser.parse_args()
    summary = json.loads((DATA / 'summary.json').read_text(encoding='utf-8'))
    screenshots = args.output_dir
    screenshots.mkdir(parents=True, exist_ok=True)
    errors, checks = [], []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.base_url, wait_until='domcontentloaded')
        expect(page.locator('#result-status')).to_have_text(f"{summary['total']:,} papers in this view", timeout=180000)
        expect(page.locator('#paper-body tr')).to_have_count(25)
        checks.append('Full corpus loads and paginates')
        page.screenshot(path=str(screenshots / 'preview-desktop.png'))
        page.get_by_label('Search papers', exact=True).fill('10.1109/cvpr.2016.90')
        expect(page.locator('#result-status')).to_have_text('1 papers in this view')
        expect(page.locator('#paper-body')).to_contain_text('Deep Residual Learning for Image Recognition')
        if page.locator('#paper-body details').count():
            page.locator('#paper-body summary').click()
            expect(page.locator('#paper-body details[open] p')).not_to_be_empty()
        checks.append('Known DOI resolves to ResNet; available abstract expands')
        page.get_by_label('Search papers', exact=True).fill('no-such-paper-xyz-987654321')
        expect(page.locator('#result-status')).to_have_text('0 papers in this view')
        expect(page.locator('#paper-body')).to_contain_text('No papers match')
        page.get_by_role('button', name='Reset all', exact=True).click()
        expect(page.locator('#result-status')).to_have_text(f"{summary['total']:,} papers in this view")
        checks.append('Empty results and reset')
        for venue in ['ICCV', 'ECCV', 'WACV', 'TPAMI', 'IJCV']:
            page.locator(f'#venue-filters input[value="{venue}"]').uncheck()
        expect(page.locator('#result-status')).to_have_text(f"{summary['venues']['CVPR']['count']:,} papers in this view")
        page.get_by_label('From year', exact=True).fill('2025')
        page.get_by_label('To year', exact=True).fill('2025')
        page.get_by_label('To year', exact=True).press('Tab')
        expected_year = summary['venues']['CVPR']['years']['2025']
        expect(page.locator('#result-status')).to_have_text(f'{expected_year:,} papers in this view')
        checks.append('Venue and year filters match dataset totals')
        page.get_by_label('Research topic', exact=True).select_option(label='3D Vision')
        count = int(page.locator('#result-status').inner_text().split()[0].replace(',', ''))
        assert 0 < count < expected_year
        with page.expect_download() as event:
            page.get_by_role('button', name='Export CSV', exact=False).click()
        download = event.value
        export_path = screenshots / 'filtered-qa.csv'
        download.save_as(str(export_path))
        with export_path.open(encoding='utf-8-sig', newline='') as f:
            assert len(list(csv.DictReader(f))) == count
        checks.append('Topic filter and CSV export contain matching records')
        page.get_by_role('button', name='Reset all', exact=True).click()
        page.get_by_label('Next page', exact=True).click()
        expect(page.locator('#page-info')).to_contain_text('Page 2 ')
        page.locator('#page-size').select_option('100')
        expect(page.locator('#paper-body tr')).to_have_count(100)
        checks.append('Pagination and page size')
        page.get_by_role('link', name='Research trends', exact=True).click()
        expect(page.locator('#trend-chart svg')).to_be_visible()
        expect(page.locator('#trends-body tr')).to_have_count(summary['max_year'] - summary['min_year'] + 1)
        expect(page.locator('#trends-body tr').filter(has=page.get_by_text('2025', exact=True)).locator('td').nth(3)).to_have_text('Not held')
        checks.append('Annual trend chart and calendar-aware annual counts')
        corpus = [p for venue in summary['venues'] for p in json.loads((DATA / (venue.lower()+'.json')).read_text(encoding='utf-8'))]
        geo = json.loads((DATA / 'geography.json').read_text(encoding='utf-8'))
        page.get_by_role('link', name='Research areas', exact=True).click()
        expect(page.locator('#research-chart svg')).to_be_visible()
        assert page.get_by_role('link', name='Author network', exact=True).count() == 0
        page.locator('#research-venue').select_option('ECCV')
        page.locator('#research-from').fill('2025')
        page.locator('#research-to').fill('2025')
        page.locator('#research-to').press('Tab')
        expect(page.locator('#research-kpis .stat-value').first).to_have_text('0')
        expect(page.locator('#research-chart')).to_contain_text('No data')
        page.locator('#research-from').fill('2024')
        page.locator('#research-to').fill('2024')
        page.locator('#research-to').press('Tab')
        expect(page.locator('#research-kpis .stat-value').first).to_have_text(f"{summary['venues']['ECCV']['years']['2024']:,}")
        page.locator('#research-level').select_option('subtopics')
        page.locator('#research-focus').select_option('Neural rendering')
        expected = sum(p['venue']=='ECCV' and p['year']==2024 and 'Neural rendering' in p['subtopics'] for p in corpus)
        expect(page.locator('#research-kpis .stat-value').nth(1)).to_have_text(f'{expected:,}')
        page.screenshot(path=str(screenshots / 'preview-research.png'))
        page.locator('#research-papers').click()
        expect(page.locator('#result-status')).to_have_text(f'{expected:,} papers in this view')
        expect(page.locator('#subtopic')).to_have_value('Neural rendering')
        checks.append('ECCV 2025 is empty; 2024 edition, detailed topics and paper drilldown agree')
        page.get_by_role('link', name='Research areas', exact=True).click()
        with page.expect_download() as event:
            page.locator('#research-export').click()
        event.value.save_as(str(screenshots / 'research-statistics.csv'))
        with (screenshots / 'research-statistics.csv').open(encoding='utf-8-sig', newline='') as f:
            exported = list(csv.DictReader(f))
        neural = next(r for r in exported if r['topic']=='Neural rendering')
        assert int(neural['papers']) == expected
        assert abs(float(neural['share_percent']) - 100*expected/summary['venues']['ECCV']['years']['2024']) < 1e-9
        checks.append('Research CSV percentages use the selected paper denominator')
        page.get_by_role('link', name='Global research', exact=True).click()
        expect(page.locator('#world-map svg')).to_be_visible(timeout=60000)
        page.locator('#world-venue').select_option('CVPR')
        page.locator('#world-from').fill('2025')
        page.locator('#world-to').fill('2025')
        page.locator('#world-to').press('Tab')
        page.locator('#world-topic').select_option('3D Vision')
        selected = [p for p in corpus if p['venue']=='CVPR' and p['year']==2025]
        korean = [p for p in selected if 'KR' in geo['papers'].get(p['id'],{}).get('countries',{})]
        topic_papers = [p for p in korean if '3D Vision' in p['topics']]
        author_ids = {a for p in topic_papers for a in geo['papers'][p['id']]['countries']['KR']}
        assert korean and topic_papers
        row = page.locator('#world-table tr').filter(has=page.locator('[data-country="KR"]'))
        expect(row.locator('td').nth(1)).to_have_text(f'{len(author_ids):,}')
        expect(row.locator('td').nth(2)).to_have_text(f'{len(topic_papers):,}')
        expect(row.locator('td').nth(3)).to_have_text(f'{len(korean):,}')
        expect(row.locator('td').nth(4)).to_have_text(f'{100*len(topic_papers)/len(korean):.1f}%')
        page.locator('#world-map [data-country="KR"]').click()
        expect(page.locator('#world-country')).to_have_value('KR')
        expect(page.locator('#country-heading')).to_contain_text('South Korea')
        expect(page.locator('#country-chart svg')).to_be_visible()
        page.screenshot(path=str(screenshots / 'preview-world.png'))
        with page.expect_download() as event:
            page.locator('#world-export').click()
        event.value.save_as(str(screenshots / 'country-statistics.csv'))
        with (screenshots / 'country-statistics.csv').open(encoding='utf-8-sig', newline='') as f:
            kr = next(r for r in csv.DictReader(f) if r['country_code']=='KR')
        assert int(kr['unique_authors']) == len(author_ids)
        assert int(kr['topic_papers']) == len(topic_papers)
        checks.append('Country map, unique author IDs, topic percentages and CSV match source data')
        # A researcher with two papers must count once; dual affiliations count
        # in both countries; an unlocated author is not assigned by name.
        result = page.evaluate("""() => {
            const saved = geoData;
            try {
                geoData = {papers:{a:{authors:2,known_authors:1,countries:{US:['A1'],KR:['A1']}},b:{authors:1,known_authors:1,countries:{US:['A1']}}}};
                const p = id => ({id,topics:['3D Vision'],subtopics:[]});
                const result = summarizeCountries([p('a'),p('b'),p('missing')],'3D Vision');
                return {mapped:result.mapped,countries:result.countries.map(g=>[g.code,g.authors.size,g.selected.length])};
            } finally {geoData = saved;}
        }""")
        assert result['mapped']==2
        assert sorted(result['countries'])==[['KR',1,1],['US',1,2]]
        checks.append('Repeated authors, dual affiliations and unknown countries have distinct semantics')
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(screenshots / 'preview-world-mobile.png'))
        page.get_by_role('link', name='Research areas', exact=True).click()
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.set_viewport_size({'width':1440,'height':1000})
        page.get_by_role('link', name='About the data', exact=True).click()
        expect(page.locator('#coverage-body tr')).to_have_count(6)
        checks.append('Provenance and venue coverage')
        page.get_by_role('link', name='Paper explorer', exact=True).click()
        page.get_by_role('button', name='Reset all', exact=True).click()
        page.locator('#page-size').select_option('25')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        page.screenshot(path=str(screenshots / 'preview-mobile.png'))
        checks.append('Mobile viewport has no page-level horizontal overflow')
        browser.close()
    assert not errors, errors
    report = {'base_url': args.base_url, 'passed': checks, 'browser_errors': errors, 'papers': summary['total']}
    (screenshots / 'browser-qa.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
