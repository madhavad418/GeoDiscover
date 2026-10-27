"""Cross-language name keys: names in Thai, Chinese, Japanese, Arabic... are compared as written, transliterated to
Latin script, and (when the Cloud Translation API is enabled) translated to English.

Thai uses PyThaiNLP word segmentation + Royal Institute (RTGS) romanization, the style HERE uses for Thai places'
English names ("บะหมี่ เกี๊ยวปู" -> "bami kiao pu"). Other scripts use anyascii.
"""
import json
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from anyascii import anyascii

from ..config import get_settings

log = logging.getLogger(__name__)
THAI = re.compile(r'[฀-๿]')
NON_LATIN = re.compile(r'(?![\u0000-ɏḀ-ỿ])[^\W\d_]')  # a letter outside Latin
CAMEL = re.compile(r'(?<=[a-z])(?=[A-Z])')
CACHE_FILE = Path(__file__).resolve().parents[2] / '.cache' / 'translations.json'
_lock = threading.Lock()
_translations = None
_status = {'translation': 'not used'}


def needs_variants(name):
    return bool(name and NON_LATIN.search(name))


@lru_cache(maxsize=200_000)
def transliterate(name):
    """Latin-script rendering of a non-Latin name ('' when the name is already Latin)."""
    if not needs_variants(name):
        return ''
    if THAI.search(name):
        from pythainlp.tokenize import word_tokenize  # imported lazily: loads a dictionary on first use
        from pythainlp.transliterate import romanize
        parts = []
        for word in word_tokenize(name, engine='newmm'):
            if THAI.search(word):
                parts.append(romanize(word, engine='royin'))
            elif word.strip():
                parts.append(anyascii(word))
        return re.sub(r'\s+', ' ', ' '.join(parts)).strip()
    # anyascii joins CJK syllables in CamelCase (WoChaoFuWu): split them so token matching sees each syllable.
    return re.sub(r'\s+', ' ', CAMEL.sub(' ', anyascii(name))).strip()


def _load_cache():
    global _translations
    if _translations is None:
        try:
            _translations = json.loads(CACHE_FILE.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _translations = {}
    return _translations


def translate(names, target='en'):
    """{name: English translation} for non-Latin names via Cloud Translation v2; {} when it is unavailable.

    Uses GOOGLE_TRANSLATE_API_KEY, else GOOGLE_PLACES_API_KEY (the Cloud Translation API must be enabled for the key).
    Results are cached on disk so a name is translated once.
    """
    settings = get_settings()
    key = settings.google_translate_api_key or settings.google_places_api_key
    wanted = sorted({n for n in names if needs_variants(n)})
    with _lock:
        cache = _load_cache()
        missing = [n for n in wanted if n not in cache]
        if missing and key:
            try:
                for start in range(0, len(missing), 100):
                    batch = missing[start:start + 100]
                    body = json.dumps({'q': batch, 'target': target, 'format': 'text'}).encode()
                    request = Request('https://translation.googleapis.com/language/translate/v2?key=' + key.get_secret_value(),
                                      data=body, headers={'Content-Type': 'application/json'})
                    with urlopen(request, timeout=30) as response:
                        out = json.loads(response.read())['data']['translations']
                    cache.update({n: t['translatedText'] for n, t in zip(batch, out)})
                CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
                CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
                _status['translation'] = 'enabled'
            except HTTPError as exc:  # never log the URL: it carries the key
                _status['translation'] = f'unavailable (Cloud Translation API returned HTTP {exc.code}; enable it for the API key)'
                log.warning('Name translation skipped: %s', _status['translation'])
            except (URLError, TimeoutError, OSError, ValueError, KeyError):
                _status['translation'] = 'unavailable (Cloud Translation API could not be reached)'
                log.warning('Name translation skipped: %s', _status['translation'])
        elif missing:
            _status['translation'] = 'unavailable (no API key configured)'
        elif wanted:
            _status['translation'] = 'enabled (cached)'
        return {n: cache[n] for n in wanted if n in cache}


def translation_status():
    return _status['translation']


def variants(name, translations=None):
    """The name plus its transliteration and English translation, for matching."""
    out = [name] if name else []
    if needs_variants(name):
        latin = transliterate(name)
        if latin:
            out.append(latin)
        english = (translations or {}).get(name)
        if english and english != name:
            out.append(english)
    return out
