"""Shared scope for CV Paper Atlas. Conference workshops/findings are separate works."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache' / 'cv'
DATA = ROOT / 'data'
VENUES = {
    'CVPR': {'name': 'Computer Vision and Pattern Recognition', 'since': 1983, 'color': '#2563eb', 'kind': 'conference'},
    'ICCV': {'name': 'International Conference on Computer Vision', 'since': 1987, 'color': '#7c3aed', 'kind': 'conference'},
    'ECCV': {'name': 'European Conference on Computer Vision', 'since': 1990, 'color': '#08916d', 'kind': 'conference'},
    'WACV': {'name': 'Winter Conference on Applications of Computer Vision', 'since': 1992, 'color': '#d97706', 'kind': 'conference'},
    'TPAMI': {'name': 'IEEE Transactions on Pattern Analysis and Machine Intelligence', 'since': 1979, 'color': '#dc4b61', 'kind': 'journal', 'issn': '0162-8828'},
    'IJCV': {'name': 'International Journal of Computer Vision', 'since': 1987, 'color': '#0891b2', 'kind': 'journal', 'issn': '0920-5691'},
}
