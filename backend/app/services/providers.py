"""Bounded connection diagnostics. Never retain or return provider POI attributes.

Discovery, persistence and HERE delivery need separately established source rights.
"""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from ..config import get_settings


class ProviderError(ValueError):
    pass


def provider_status():
    settings = get_settings()
    return [
        {'id': 'google', 'name': 'Google Places', 'configured': bool(settings.google_places_api_key),
         'api': 'Places API (New) · Text Search', 'mode': 'Connection diagnostics only',
         'permission': 'Standard Places access is not permission to store or deliver attributes to HERE.',
         'documentation': 'https://developers.google.com/maps/documentation/places/web-service/policies'},
        {'id': 'grab', 'name': 'AWS GrabMaps', 'configured': bool(settings.grab_api_key),
         'api': f'Places v1 · {settings.grab_region} · {settings.grab_place_index or "index not set"}',
         'mode': 'Connection diagnostics only',
         'permission': 'Confirm the index provider and contractual storage, comparison and redistribution rights.',
         'documentation': 'https://docs.aws.amazon.com/location/latest/APIReference/API_geoplaces_SearchText.html'},
        {'id': 'apple', 'name': 'Apple Maps', 'configured': bool(settings.apple_maps_access_token),
         'api': 'Maps Server API', 'mode': 'Not enabled for this POC',
         'permission': 'No approved HERE-delivery use supplied; standard terms restrict derivative databases.',
         'documentation': 'https://developer.apple.com/support/terms/apple-developer-program-license-agreement/'},
    ]


def request_json(url, payload, headers=None):
    request = Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json', **(headers or {})}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ProviderError('Provider response exceeded the diagnostic limit.')
            return json.loads(data)
    except HTTPError as exc:
        reason = {400: 'Check API version, request support and configured index.',
                  401: 'Credentials were rejected.', 403: 'Check key permissions, billing and key restrictions.',
                  404: 'The configured provider resource was not found.',
                  429: 'Rate limit or quota reached. Retry later.'}.get(exc.code, 'Provider service is unavailable.')
        # Do not return exception URLs/bodies: AWS carries API keys in the URL.
        raise ProviderError(f'Provider returned HTTP {exc.code}. {reason}') from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError('Provider request timed out or could not connect. Retry later.') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ProviderError('Provider returned an invalid JSON response.') from None


def diagnose(provider, aoi):
    settings = get_settings()
    west, south, east, north = aoi['bbox']
    if provider == 'google':
        if not settings.google_places_api_key:
            raise ProviderError('GOOGLE_PLACES_API_KEY is not configured.')
        payload = {'textQuery': f"restaurant in {aoi['name']}", 'pageSize': 1,
                   'locationRestriction': {'rectangle': {'low': {'latitude': south, 'longitude': west},
                                                        'high': {'latitude': north, 'longitude': east}}}}
        result = request_json('https://places.googleapis.com/v1/places:searchText', payload,
                              {'X-Goog-Api-Key': settings.google_places_api_key.get_secret_value(),
                               'X-Goog-FieldMask': 'places.id,nextPageToken'})
        if not isinstance(result, dict) or not isinstance(result.get('places', []), list):
            raise ProviderError('Unexpected Google Places response shape.')
        count = len(result.get('places', []))
    elif provider == 'grab':
        result = grab_search(aoi['bbox'], f"restaurant in {aoi['name']}", max_results=1)
        count = len(result.get('ResultItems', []))
    else:
        raise ProviderError('Apple is not enabled for this POC; access and permitted use are still required.')
    return {'provider': provider, 'status': 'connected', 'sample_result_count': count, 'requests_made': 1,
            'scope': 'Single bounded diagnostic request; not a coverage measurement.',
            'retained_provider_records': 0, 'delivery_eligible': False}


def grab_search(bounds, query, language='', token=None, max_results=100, storage=False):
    """AWS Places v2, matching the existing heremaps_project integration."""
    settings = get_settings()
    if not settings.grab_api_key:
        raise ProviderError('GRAB_API_KEY is not configured.')
    if settings.grab_region not in ('ap-southeast-1', 'ap-southeast-5'):
        raise ProviderError('Use a GrabMaps-supported AWS region.')
    endpoint = f'https://places.geo.{settings.grab_region}.amazonaws.com/v2/search-text?'
    payload = {'QueryText':query, 'Filter':{'BoundingBox':list(bounds)}, 'MaxResults':max_results,
               'IntendedUse':'Storage' if storage else 'SingleUse'}
    if language: payload['Language'] = 'tl' if language == 'fil' else language
    if token: payload['NextToken'] = token
    result = request_json(endpoint + urlencode({'key':settings.grab_api_key.get_secret_value()}), payload)
    if not isinstance(result,dict) or not isinstance(result.get('ResultItems',[]),list):
        raise ProviderError('Unexpected AWS Places v2 response shape.')
    return result
