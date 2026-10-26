"""Opt-in PostGIS integration tests. All fixture writes roll back after each test.

Run with RUN_DATABASE_TESTS=1 against a migrated database.
"""
import os
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import engine, get_db
from app.main import app

pytestmark = pytest.mark.skipif(os.environ.get('RUN_DATABASE_TESTS') != '1', reason='Opt-in PostGIS integration tests')


@pytest.fixture
def client_and_db():
    assert engine is not None
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode='create_savepoint') as session:
            def override():
                yield session
            app.dependency_overrides[get_db] = override
            try:
                with TestClient(app) as client:
                    yield client, session
            finally:
                app.dependency_overrides.pop(get_db, None)
        transaction.rollback()


def test_excel_persistence_search_geometry_and_duplicate_upload(client_and_db):
    client, db = client_and_db
    unique = str(uuid4())
    book = Workbook()
    book.active.append(['placeid', 'name1', 'primarycategorynm', 'displaylatitude', 'displaylongitude', 'routinglatitude', 'routinglongitude', 'country', 'phone_numbers'])
    book.active.append([unique, 'Test Café สยาม', 'Restaurant', 13.75, 100.5, 13.751, 100.501, 'THA', '0012345'])
    buffer = BytesIO()
    book.save(buffer)
    payload = buffer.getvalue()
    result = client.post('/api/customer-data/imports', data={'aoi':'Thanon Phaya Thai'}, files={'file':('test.xlsx',payload)})
    assert result.status_code == 201, result.text
    dataset_id = result.json()['id']
    result = client.get(f'/api/customer-data/datasets/{dataset_id}/records', params={'q':unique,'category':'Restaurant','page_size':1})
    assert result.status_code == 200
    data = result.json()
    assert data['total'] == 1
    assert data['records'][0]['raw']['phone_numbers'] == '0012345'
    geo = client.get(f'/api/customer-data/datasets/{dataset_id}/geojson').json()
    assert geo['features'][0]['geometry']['coordinates'] == [100.5, 13.75]
    point = db.execute(text('SELECT ST_SRID(display_point), ST_X(display_point), ST_Y(routing_point) FROM customer_pois WHERE dataset_id=:id'), {'id':dataset_id}).one()
    assert tuple(point) == (4326, 100.5, 13.751)
    duplicate = client.post('/api/customer-data/imports', data={'aoi':'Thanon Phaya Thai'}, files={'file':('test.xlsx',payload)})
    assert duplicate.status_code == 409
    assert client.get(f'/api/customer-data/datasets/{uuid4()}/records').status_code == 404
    assert client.get(f'/api/customer-data/datasets/{dataset_id}/records?page=0').status_code == 422
    assert client.get(f'/api/customer-data/datasets/{dataset_id}/records?q=%25').json()['total'] == 0


def test_invalid_import_is_atomic(client_and_db):
    client, db = client_and_db
    before = db.execute(text('SELECT count(*) FROM customer_datasets')).scalar()
    payload = f'placeid,name1,displaylatitude,displaylongitude\n{uuid4()},Good,14,120\n{uuid4()},Bad,NaN,120'.encode()
    result = client.post('/api/customer-data/imports', data={'aoi':'Divisoria'}, files={'file':('invalid.csv',payload)})
    assert result.status_code == 422
    assert result.json()['detail']['issues'][0]['row'] == 3
    assert db.execute(text('SELECT count(*) FROM customer_datasets')).scalar() == before
