import os
import requests

from .config import load_api_key, WEB_LOGO_DIR
from .card_renderer import SYSTEM_ICON_RESULT_LIMIT

TMDB_IMG_BASE = 'https://image.tmdb.org/t/p/original'
ICON_EXTS = ('.png', '.jpg', '.jpeg', '.webp')


def steam_headers():
    key = load_api_key('steamgriddb')
    return {'Authorization': f'Bearer {key}'}


def search_games(name):
    r = requests.get(f'https://www.steamgriddb.com/api/v2/search/autocomplete/{name}', headers=steam_headers(), timeout=15)
    r.raise_for_status()
    return r.json().get('data', [])


def get_grids(game_id):
    r = requests.get(f'https://www.steamgriddb.com/api/v2/grids/game/{game_id}', headers=steam_headers(), timeout=15)
    r.raise_for_status()
    return r.json().get('data', [])


def get_steam_logos(game_id):
    r = requests.get(
        f'https://www.steamgriddb.com/api/v2/logos/game/{game_id}',
        headers=steam_headers(), timeout=15,
    )
    r.raise_for_status()
    return r.json().get('data', [])


def tmdb_search_multi(query):
    r = requests.get('https://api.themoviedb.org/3/search/multi', params={'api_key': load_api_key('tmdb'), 'query': query, 'include_adult': False}, timeout=15)
    r.raise_for_status()
    results = []
    for item in r.json().get('results', []):
        if item.get('media_type') not in ('movie', 'tv'):
            continue
        title = item.get('title') or item.get('name')
        year = None
        if item.get('release_date'):
            year = item['release_date'][:4]
        elif item.get('first_air_date'):
            year = item['first_air_date'][:4]
        results.append({'id': item['id'], 'title': title, 'year': year, 'media_type': item['media_type']})
    return results


def tmdb_get_posters(item):
    r = requests.get(f"https://api.themoviedb.org/3/{item['media_type']}/{item['id']}/images", params={'api_key': load_api_key('tmdb'), 'include_image_language': 'en,null'}, timeout=15)
    r.raise_for_status()
    return r.json().get('posters', [])


def tmdb_get_logos(item):
    r = requests.get(
        f"https://api.themoviedb.org/3/{item['media_type']}/{item['id']}/images",
        params={'api_key': load_api_key('tmdb'), 'include_image_language': 'en,null'},
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get('logos', [])


def build_system_icon_index(root):
    index = []
    for base, _, files in os.walk(root):
        for f in files:
            if not f.lower().endswith(ICON_EXTS):
                continue
            abs_path = os.path.join(base, f)
            rel_path = os.path.relpath(abs_path, root).lower()
            index.append((abs_path, rel_path))
    return index


def filter_system_icons(index, query):
    q = query.lower()
    return [abs_path for abs_path, rel_lower in index if q in rel_lower]


def search_system_logos(query, icon_pack_dir=None, search_cached=False, indices=None):
    indices = indices if indices is not None else {}
    results = []
    if icon_pack_dir and os.path.isdir(icon_pack_dir):
        if icon_pack_dir not in indices:
            indices[icon_pack_dir] = build_system_icon_index(icon_pack_dir)
        results.extend(filter_system_icons(indices[icon_pack_dir], query))
    if search_cached and os.path.isdir(WEB_LOGO_DIR):
        if WEB_LOGO_DIR not in indices:
            indices[WEB_LOGO_DIR] = build_system_icon_index(WEB_LOGO_DIR)
        results.extend(filter_system_icons(indices[WEB_LOGO_DIR], query))
    total = len(results)
    return results[:SYSTEM_ICON_RESULT_LIMIT], total
