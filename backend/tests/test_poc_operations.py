from types import SimpleNamespace
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.auth import current_user
from app.main import app
from app.services import providers

AOI = {'name': 'Divisoria', 'country': 'PHL', 'bbox': [120.96, 14.59, 120.98, 14.61]}


@pytest.fixture
def credentials(monkeypatch):
    monkeypatch.setattr(providers, 'get_settings', lambda: SimpleNamespace(
        google_places_api_key=SecretStr('private-google'), grab_api_key=SecretStr('private-grab'),
        grab_place_index='explore.place.Grab', grab_region='ap-southeast-1', apple_maps_access_token=None))


def test_google_probe_is_bounded_and_does_not_return_attributes(credentials, monkeypatch):
    def request(url, payload, headers):
        assert payload['pageSize'] == 1
        assert payload['locationRestriction']['rectangle']['low']['longitude'] == 120.96
        assert headers['X-Goog-FieldMask'] == 'places.id,nextPageToken'
        return {'places': [{'id': 'provider-id'}]}
    monkeypatch.setattr(providers, 'request_json', request)
    result = providers.diagnose('google', AOI)
    assert result['sample_result_count'] == 1
    assert result['retained_provider_records'] == 0
    assert 'provider-id' not in str(result)


def test_grab_v2_bbox_and_response(credentials, monkeypatch):
    def request(url, payload):
        assert '/v2/search-text?' in url
        assert '/indexes/' not in url
        assert payload['Filter']['BoundingBox'] == AOI['bbox']
        assert payload['MaxResults'] == 1
        assert payload['IntendedUse'] == 'SingleUse'
        return {'ResultItems': [{'PlaceId':'test'}]}
    monkeypatch.setattr(providers, 'request_json', request)
    assert providers.diagnose('grab', AOI)['sample_result_count'] == 1


def test_http_errors_never_expose_url_credentials(monkeypatch):
    def fail(*args, **kwargs):
        raise HTTPError('https://example.com?key=secret', 403, 'secret', {}, None)
    monkeypatch.setattr(providers, 'urlopen', fail)
    with pytest.raises(providers.ProviderError) as error:
        providers.request_json('https://example.com?key=secret', {})
    assert 'secret' not in str(error.value)
    assert '403' in str(error.value)


def test_assessment_download_and_paid_probe_boundary(credentials):
    client = TestClient(app)
    assert client.get('/api/poc/assessment').status_code != 200  # sign-in required
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id='u', roles=['ops_manager'], aois=[], active=True)
    try:
        _assessment_checks(client)
    finally:
        app.dependency_overrides.pop(current_user, None)


def _assessment_checks(client):
    response = client.get('/api/poc/assessment')
    assert response.status_code == 200
    assert sum(a['rows'] for a in response.json()['audit']['aois']) == 18161
    assert 'private-google' not in response.text
    assert 'private-grab' not in response.text
    assert client.get('/api/poc/assessment.md').status_code == 200
    assert client.post('/api/poc/providers/google/diagnose', json={'aoi':'Divisoria'}).status_code == 403
