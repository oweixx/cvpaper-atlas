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
        checks.append('Annual trend chart and annual counts')
        page.get_by_role('link', name='Author network', exact=True).click()
        expect(page.locator('#network-authors button')).to_have_count(100, timeout=15000)
        page.locator('#network-authors button').first.click()
        expect(page.locator('#selected-author')).not_to_have_text('Select an author')
        page.locator('#network-threshold').select_option('10')
        expect(page.locator('#network-note')).to_contain_text('100 author names')
        page.get_by_role('button', name='View papers', exact=False).click()
        expect(page.locator('#view-explore')).to_be_visible()
        checks.append('Co-author network, threshold and author navigation')
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
