"""Generate repository documentation from the published snapshot."""
import json
from cv_config import ROOT, DATA


def write_docs():
    s = json.loads((DATA/'summary.json').read_text(encoding='utf-8'))
    c = json.loads((DATA/'coverage.json').read_text(encoding='utf-8'))
    rows = '\n'.join(f"| {v} | {m['min_year']}–{m['max_year']} | {m['count']:,} | {100*m['with_abstract']/m['count']:.1f}% | {100*m['with_citations']/m['count']:.1f}% |" for v,m in s['venues'].items())
    abs_pct = 100*s['with_abstract']/s['total']
    cite_pct = 100*s['with_citations']/s['total']
    geo = json.loads((DATA/'geography.json').read_text(encoding='utf-8'))
    gc = geo['coverage']
    year_audit = json.loads((DATA/'year_audit.json').read_text(encoding='utf-8'))
    text = f'''# CV Paper Atlas

Computer Vision 논문 **{s['total']:,}편 · {s['min_year']}–{s['max_year']}**을 검색하고, 연구 분야별 추이와 국가별 저자 소속·연구 비중을 살펴보는 정적 웹 애플리케이션입니다.

웹사이트: [CV Paper Atlas](https://oweixx.github.io/cvpaper-atlas/)

대상: **CVPR · ICCV · ECCV · WACV · TPAMI · IJCV**. 수집한 실제 데이터로 검색 화면, 통계, 그래프와 다운로드 파일을 함께 생성합니다.

![Paper explorer](docs/preview-desktop.png)

## 현재 데이터

산출물 생성: **{s['built_at'][:10]}**. 원본 조회일과 인용수 조회일은 각 레코드 및 coverage ledger에 기록합니다.

| Venue | 수집 연도 | 논문 | 초록 확보율 | 인용수 확보율 |
|---|---:|---:|---:|---:|
{rows}
| **전체** | **{s['min_year']}–{s['max_year']}** | **{s['total']:,}** | **{abs_pct:.1f}%** | **{cite_pct:.1f}%** |

‘전체’는 위 여섯 venue의 수집된 corpus입니다. Computer Vision의 모든 학회·저널·arXiv를 포함한다는 뜻은 아닙니다. DBLP에 색인된 본학회 자료는 총건수와 페이지네이션 결과를 대조했습니다. 출처의 미색인·지연 반영 때문에 실제 출판물 전체와 차이가 날 수 있습니다.

## 기능

- 제목·저자·DOI·확보된 초록 검색, venue·연도·주제·최소 인용수 필터
- 최신순·인용순·제목순 정렬, 페이지네이션, 필터 결과 CSV 내보내기
- 초록 펼쳐보기, 공식 논문·DOI·공개 PDF 링크
- 연도별 누적 막대그래프와 연간 편수 표
- Research areas: 10개 분야·30개 세부 주제, 기간·학회별 논문 수/비중, 연도별 추이와 논문 검색 연결
- Global research: 세계지도·국가별 고유 저자 수·주제별 논문 비중·연간 추이·통계 CSV
- 출처·확보율 안내 및 XLSX, CSV.gz, JSONL.gz 전체 다운로드
- 모바일 화면, 키보드 검색 단축키 `/`, 검색 조건 URL 공유

## 실행

Python 3.12 이상을 권장합니다. 미리 생성한 웹 파일을 열 때는 아래 서버만 있으면 됩니다.

```sh
python -m http.server 8765 --bind 127.0.0.1
```

브라우저: http://127.0.0.1:8765 . JSON을 fetch하므로 `file://`로 직접 열지 않습니다. 별도 애플리케이션 서버·데이터베이스·프런트엔드 빌드는 필요하지 않습니다. GitHub Pages 등 정적 호스팅에도 동일한 파일을 사용할 수 있습니다.

## 재수집과 빌드

```sh
pip install -r requirements.txt
python pipeline/collect_dblp.py
python pipeline/collect_cv.py --only official
python pipeline/collect_cv.py --only crossref
python pipeline/build_cv.py
python pipeline/enrich_openalex.py
python pipeline/build_cv.py
python pipeline/validate_cv.py
```

수집기는 `.cache/cv/`의 응답을 재사용합니다. 최신 자료를 다시 조회하려면 각 수집 명령에 `--refresh`를 추가합니다. OpenAlex의 공개 할당량이 부족하면 `OPENALEX_API_KEY` 환경변수를 설정하고 재실행할 수 있습니다. API 키는 데이터·로그·브라우저에 저장하지 않습니다. 네트워크 실패는 조용히 0건으로 바꾸지 않고 명시적으로 보고합니다.

저장된 snapshot만으로 재생성:

```sh
python pipeline/build_cv.py
```

## 수집·정제 원칙

1. **DBLP SPARQL**: venue stream과 본학회 label을 명시적으로 제한합니다. 저자 순서와 DBLP 연구자 식별자를 보존합니다. CVPR/ICCV/ECCV/WACV 워크숍과 CVPR Findings는 제외합니다. 초기 WACV의 본행사는 명칭에 Workshop이 있어도 포함합니다.
2. **CVF / ECVA**: 공식 논문 목록, 저자, 논문 페이지와 PDF 링크를 수집합니다. DOI가 없는 논문도 유지합니다.
3. **Crossref**: 저널 ISSN과 정확한 proceedings 이름으로 수집합니다. 예상 등록 건수와 실제 조회 건수를 대조합니다. 쉼표가 있는 옛 proceedings는 제목을 정확히 재검증하는 검색 경로를 사용합니다.
4. **OpenAlex**: 100개 DOI씩 조회하고 반환된 DOI가 정확히 같은 경우만 초록과 인용수를 반영합니다. 다른 DOI로 연결된 결과는 제외하며 batch별 ledger에 남깁니다.
5. 같은 DOI 및 DBLP가 명시한 DOI 별칭은 병합합니다. DOI 없는 공식 논문은 동일 venue·연도·정규화 제목·겹치는 저자가 있을 때 병합합니다. 다른 DOI의 학회 원본과 저널 확장본은 구분합니다.
6. 인용수는 **OpenAlex 우선, Crossref 보완**이며 출처별 값의 의미가 다릅니다. 알 수 없는 값은 `null`/`N/A`, 출처가 반환한 0은 0으로 유지합니다. Google Scholar나 Semantic Scholar 수치로 표시하지 않습니다.
7. 주제는 **제목에 동일하게 적용하는 키워드 규칙에 의한 다중 분류**입니다. 초록 확보율이 다른 학회들을 비교하기 위해 제목만 사용합니다. 공식 세션 분류나 검증된 모델 예측이 아닙니다. 주제 비중의 분모는 선택 범위의 논문 수이므로 여러 주제의 비중 합은 100%를 넘을 수 있습니다.
8. 학회 통계의 `year`는 개최 연도입니다. 공식 목록·논문집 제목을 DBLP 출판 연도보다 우선합니다. ECCV 2024 논문의 DBLP 출판 연도 2025는 `publication_year`에 보존하고 통계는 2024로 집계합니다. ECCV 홀수 해와 ICCV 비개최 연도는 검증에서 차단하며 초기 ICCV 1988·1990·1998 등의 실제 개최는 유지합니다. [연도 수정 내역](data/year_audit.json), [식별자·제목 병합 내역](data/identity_audit.json).
9. ECVA의 BibTeX 형식 저자 목록, DOI 공백과 출처 간 제목 변형을 정규화합니다. DOI가 없는 공식 항목의 제목 변형은 동일 venue·개최 연도·전체 저자 서명, 유일 후보 및 유사도 기준을 모두 충족할 때만 병합합니다. 서로 다른 DOI의 출판물은 유지합니다.

## 국가별 통계의 범위

- 소속 국가 확보: **{gc['papers_with_country']:,} / {s['total']:,}편 ({100*gc['papers_with_country']/s['total']:.1f}%)**.
- 소속 국가가 알려진 고유 OpenAlex 저자 ID: **{gc['unique_author_ids_with_country']:,}개**. 이름이 같은 사람을 이름만으로 합산하지 않습니다.
- 국가·지역은 논문에 기록된 기관 소속이며 국적이 아닙니다. 여러 나라에 소속된 저자는 각 나라에 포함되므로 나라별 합계는 전체 고유 저자 수와 다를 수 있습니다.
- 소속 누락은 미상으로 남깁니다. 기관 연결 오류나 기업 본사 위치 때문에 실제 연구 장소와 다를 수 있습니다. 기간·학회별 확보율을 화면에 표시합니다.
- 국가별 연구 비중 = 해당 국가의 해당 주제 논문 수 / 해당 국가의 선택 기간·학회 전체 논문 수. 관측된 연구 성과의 비중이며 연구자의 주관적 관심도를 측정한 값이 아닙니다.
- OpenAlex 목록 API는 논문당 첫 100개 authorship을 반환할 수 있습니다. 100개에 도달해 잘렸을 가능성이 있는 항목: {gc['possibly_truncated_papers']:,}편.
- [소속 수집 ledger](data/coverage_affiliations.json), [브라우저 국가 집계 인덱스](data/geography.json). 재수집: `python pipeline/collect_affiliations.py` 후 `python pipeline/build_cv.py`. `OPENALEX_API_KEY` 환경변수로 인증하며 키를 소스·ledger·GitHub에 저장하지 않습니다.
- 지도: [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) public domain. 지도에 없는 작은 국가·지역도 표와 선택 목록에 데이터가 있으면 포함됩니다.

## 데이터와 검증

- [전체 XLSX](downloads/cvpaper_atlas.xlsx) — summary, papers, venue별 시트
- [전체 CSV.gz](downloads/cvpaper_atlas.csv.gz), [전체 JSONL.gz](downloads/cvpaper_atlas.jsonl.gz)
- [집계 snapshot](data/summary.json), [수집 근거 ledger](data/coverage.json)
- [수집 보고서](docs/DATA_REPORT.md), [브라우저 검증 기록](docs/browser-qa.json)

논문별 핵심 필드: `id`, `venue`, `year`(학회 개최 연도/저널 출판 연도), `publication_year`(DBLP 출판 연도), `year_basis`, `source_years`, `title`, `authors`, `author_ids`, `doi`, `url`, `pdf_url`, `abstract`, `topics`, `subtopics`, `citation_count`, `citation_source`, `citation_updated`, `sources`.

```sh
python -m unittest discover -s pipeline -p test_cv.py -v
python pipeline/validate_cv.py
```

선택적 브라우저 검증(로컬 서버를 실행한 상태):

```sh
pip install -r requirements-dev.txt
python -m playwright install chromium
python pipeline/smoke_browser.py
```

GitHub Actions는 push/PR 시 회귀 테스트, 데이터 일관성 검사와 JavaScript 문법 검사를 실행합니다. 자동 재수집 일정은 설정되어 있지 않습니다.

## GitHub Pages

Pages 배포 설정: [pages.yml](.github/workflows/pages.yml). 저장소의 Settings → Pages에서 GitHub Actions를 활성화하면 `main`에 push할 때 검증을 통과한 웹사이트를 자동 배포합니다. Actions 화면에서 수동 실행할 수도 있습니다.

배포 구성에는 HTML·CSS·JavaScript, 검색 데이터, 출처 ledger와 다운로드 파일만 포함됩니다. 수집용 Python 코드, 원본 수집 snapshot, 캐시와 Git 이력은 사이트에 포함되지 않습니다.

배포된 사이트 검증:

```sh
python pipeline/smoke_browser.py --base-url https://oweixx.github.io/cvpaper-atlas/ --output-dir .cache/pages-qa
```

GitHub Free에서는 공개 저장소의 Pages를 사용할 수 있습니다. 비공개 저장소에서 Pages를 사용하려면 이를 지원하는 요금제가 필요합니다. [GitHub 공식 안내](https://docs.github.com/en/pages/getting-started-with-github-pages).

## 출처와 프로젝트 이력

- 프로젝트 출발점: [gisbi-kim/robopaper-atlas](https://github.com/gisbi-kim/robopaper-atlas), commit `c4521736a51637d03cf728eb8a411d989faa0d7d`.
- CV 버전은 별도 수집 파이프라인과 화면을 작성하고 로봇 논문·캐시·페이지를 교체했습니다. 새 저장소의 첫 커밋은 CV 결과만 담으며 원본의 대용량 Git 이력을 포함하지 않습니다. 로컬 원본 `main` 이력은 유지됩니다.
- 데이터: [DBLP](https://sparql.dblp.org/), [CVF Open Access](https://openaccess.thecvf.com/), [ECVA](https://www.ecva.net/papers.php), [Crossref](https://www.crossref.org/), [OpenAlex](https://openalex.org/).
- 논문 PDF를 저장·재배포하지 않습니다. 논문 텍스트와 각 공급원의 자료는 해당 권리와 이용 조건을 따릅니다. 원본 저장소에 명시적인 LICENSE가 없어 원본에 새로운 이용 허락이 있다고 주장하지 않습니다.
'''
    (ROOT/'README.md').write_text(text,encoding='utf-8')
    dblp_count = sum(x['retrieved'] for x in c['dblp'])
    cr = [x for x in c['crossref']['sources'] if x['source']=='Crossref']
    oa = c.get('openalex') or {}
    report = f'''# Collection report — {s['built_at'][:10]}

## Scope and results

- Published corpus: **{s['total']:,}** records, **{s['min_year']}–{s['max_year']}**.
- Abstracts: **{s['with_abstract']:,} ({abs_pct:.1f}%)**.
- Citation counts: **{s['with_citations']:,} ({cite_pct:.1f}%)**.
- Direct public PDF links: **{s['with_pdf']:,}**; no PDFs are redistributed.
- DOI-bearing records: **{s['with_doi']:,}**. DOI-less official papers remain searchable.

| Venue | Years | Papers | Abstracts | Citations |
|---|---:|---:|---:|---:|
{rows}

## Audited sources

- DBLP SPARQL: {dblp_count:,} records from 6 streams; every expected distinct-publication total equals the downloaded total. Only main-conference labels and the two journal labels are included.
- CVF and ECVA: {sum(x['retained'] for x in c['official']):,} official-list records. Legacy CVF day lists are followed when no all-papers page exists.
- Crossref: {len(cr)} exact proceedings/ISSN collections, {sum(x['retrieved'] for x in cr):,} raw DOI records; all expected totals equal retrieved totals. Front matter, invalid dates and other non-paper records are excluded.
- OpenAlex: {oa.get('requested_dois',0):,} DOI lookups in {len(oa.get('batches',[]))} batches; {oa.get('matched_dois',0):,} exact matches. {sum(len(x.get('rejected_doi_mismatches',[])) for x in oa.get('batches',[]))} returned canonical-DOI mismatches were rejected.
- {c['excluded_nonpapers']:,} additional editorial/front-matter records were excluded at build time; see `data/excluded.json`.

## Limits

The source audit verifies collection of indexed records, not that every historically published paper has been indexed. OpenAlex and Crossref count different citation graphs; their values are labeled per paper. Current-year indexing and DOI assignment lag publication. Missing abstracts and citation counts are preserved as missing.

DBLP's ordinary search endpoint returned an automated-access challenge. Its separate official SPARQL service worked and was used for the complete indexed corpus. Semantic Scholar's unauthenticated endpoint returned HTTP 429 and is not used for this snapshot. The CVPR 2026 virtual programme's advertised pagination API returned HTTP 403; that incomplete feed was not imported. Official CVF main-conference entries are still included.

Topic labels use title-only keyword heuristics (10 areas / 30 subtopics) consistently across venues. They are multi-label, not official conference tracks. Percentages use selected papers as the denominator.

## Calendar and identity correction

The original snapshot incorrectly retained DBLP publication years after matching conference editions. ECCV 2024 papers published in 2025 are now grouped under the 2024 event. {len(year_audit['corrections']):,} merged records retain differing source-year observations in `data/year_audit.json`. Calendar validation rejects off-year ECCV and non-edition ICCV records, preserving historical ICCV even-year events.

ECVA 2018 BibTeX author lists and whitespace in ECVA DOI links are normalized before identity matching. Conservative title-variant matches and corrected erroneous official DOI links are logged in `data/identity_audit.json`. Distinct DOI publications remain distinct.

## Geographic coverage

{gc['matched_papers']:,} corpus records match the affiliation snapshot; {gc['papers_with_country']:,} ({100*gc['papers_with_country']/s['total']:.1f}%) have at least one known country/region. {gc['unique_author_ids_with_country']:,} unique OpenAlex author IDs have a known affiliation country. Request completion: {geo['collection_complete']}.

Country means work-time affiliation, not nationality. Cross-country counts overlap. Unknown affiliations remain unknown. Institutional matching, headquarters locations, author disambiguation, uneven coverage over time, and the list API's first-100-authorship limit can affect statistics. The interface reports coverage for the selected period/venue and per year. It does not infer a country from names. The public-domain basemap is Natural Earth.

## Reproduction

Normalized source snapshots, per-venue browser shards and the query ledger are committed. Raw HTTP caches are excluded. Run the commands in the repository README to collect again or rebuild offline. A rebuild timestamp does not imply that cached citations were freshly queried.
'''
    (ROOT/'docs').mkdir(exist_ok=True)
    (ROOT/'docs/DATA_REPORT.md').write_text(report,encoding='utf-8')


if __name__ == '__main__':
    write_docs()
