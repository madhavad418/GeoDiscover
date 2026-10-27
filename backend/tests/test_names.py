"""Cross-language name matching: transliteration (and translation when enabled) bridges Thai/CJK and Latin names."""
from app.services import names
from app.services.matching import compare, name_keys

LAT, LON = 13.7512, 100.5390  # Thanon Phaya Thai


def test_thai_romanization_matches_here_style():
    assert names.transliterate('บะหมี่ เกี๊ยวปู') == 'bami kiao pu'  # HERE stores "Bami Kiao Pu"
    assert names.transliterate('Starbucks') == ''
    assert names.transliterate('窝巢服务式公寓').split()[:2] == ['Wo', 'Chao']  # CJK syllables split


def test_translations_add_an_english_key():
    keys = name_keys(['โรงแรมเบนซ์เฮ้าส์'], {'โรงแรมเบนซ์เฮ้าส์': 'Benz House Hotel'})
    assert 'benz house hotel' in keys and any('rongraem' in k for k in keys)


def test_thai_provider_name_matches_english_only_here_poi():
    here = [{'id': 1, 'place_id': 'h1', 'name': 'Bami Kiao Pu', 'category_code': None, 'category_name': None,
             'latitude': LAT, 'longitude': LON, 'address': '', 'raw': {}}]
    obs = [{'id': 1, 'batch_id': 'grab', 'source_type': 'map_provider', 'source_name': 'GrabMaps', 'source_record_id': 'g1',
            'name': 'บะหมี่ เกี๊ยวปู', 'latitude': LAT + 0.0001, 'longitude': LON, 'business_status': 'open'}]
    result = compare(here, obs, 'THA', 'd')['results']
    assert [r['outcome'] for r in result] == ['no_change']  # same business, not New + Delete


def test_translation_unavailable_is_reported_not_fatal(monkeypatch):
    def blocked(*args, **kwargs):
        from urllib.error import HTTPError
        raise HTTPError('https://translation.googleapis.com/?key=secret', 403, 'blocked', {}, None)
    monkeypatch.setattr(names, 'urlopen', blocked)
    monkeypatch.setattr(names, '_translations', {})
    monkeypatch.setattr(names, 'CACHE_FILE', names.CACHE_FILE.with_name('test-unused.json'))
    from types import SimpleNamespace
    from pydantic import SecretStr
    monkeypatch.setattr(names, 'get_settings', lambda: SimpleNamespace(google_translate_api_key=SecretStr('secret'), google_places_api_key=None))
    assert names.translate(['ร้านทดสอบ']) == {}
    assert 'HTTP 403' in names.translation_status() and 'secret' not in names.translation_status()
