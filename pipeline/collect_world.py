"""Prepare a small public-domain Natural Earth basemap for offline hosting."""
import json
import base64
import requests
from cv_config import DATA

URL = 'https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson'


def main():
    r = requests.get('https://api.github.com/repos/nvkelso/natural-earth-vector/contents/geojson/ne_110m_admin_0_countries.geojson', timeout=60)
    r.raise_for_status()
    source = json.loads(base64.b64decode(r.json()['content']))
    features = []
    def rounded(value):
        return [rounded(x) for x in value] if isinstance(value, list) else round(value, 3)
    for f in source['features']:
        p = f['properties']
        code = p.get('ISO_A2_EH') or p.get('ISO_A2')
        if code == 'AQ' or not code or len(code) != 2:
            continue
        features.append({'code': code, 'name': p['NAME_EN'], 'type': f['geometry']['type'],
                         'coordinates': rounded(f['geometry']['coordinates'])})
    data = {'source': URL, 'license': 'Public domain', 'attribution': 'Natural Earth 1:110m countries', 'features': features}
    (DATA / 'world.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
    print(f'Basemap: {len(features)} country/region geometries')


if __name__ == '__main__':
    main()
