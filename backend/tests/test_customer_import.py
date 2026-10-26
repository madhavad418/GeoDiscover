from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.customer_import import ImportInvalid, parse_file


HEADER = 'placeid,name1,primarycategory,primarycategorynm,displaylatitude,displaylongitude,routinglatitude,routinglongitude,country,phone_numbers'


def csv_bytes(*rows):
    return ('\ufeff' + HEADER + '\n' + '\n'.join(rows)).encode('utf-8')


def test_here_csv_preserves_ids_unicode_and_source_fields():
    records, columns = parse_file(csv_bytes('000123,Café สยาม,100-1000-0000,Restaurant,13.75,100.5,13.751,100.501,THA,+660123'), 'here.csv', 'Thanon Phaya Thai')
    row = records[0]
    assert row['place_id'] == '000123'
    assert row['name'] == 'Café สยาม'
    assert row['raw']['phone_numbers'] == '+660123'
    assert row['routing_longitude'] == 100.501
    assert len(columns) == 10


@pytest.mark.parametrize('coords', ['NaN,100', '91,100', '10,181', ',100', 'Infinity,100'])
def test_invalid_coordinates_reject_entire_import(coords):
    with pytest.raises(ImportInvalid) as result:
        parse_file(csv_bytes('a,Valid,,,14,120,,,PHL,', f'b,Invalid,,,{coords},,,PHL,'), 'here.csv', 'Divisoria')
    assert result.value.issues[0]['row'] == 3


def test_duplicate_ids_rejected_with_row_number():
    with pytest.raises(ImportInvalid) as result:
        parse_file(csv_bytes('a,First,,,14,120,,,PHL,', 'a,Second,,,14,120,,,PHL,'), 'here.csv', 'Divisoria')
    assert 'Duplicate place ID' in result.value.issues[0]['message']


def test_country_must_match_aoi():
    with pytest.raises(ImportInvalid) as result:
        parse_file(csv_bytes('a,Wrong country,,,14,120,,,THA,'), 'here.csv', 'Divisoria')
    assert 'Country' in result.value.issues[0]['message']


def test_optional_routing_pair_cannot_be_half_populated():
    with pytest.raises(ImportInvalid):
        parse_file(csv_bytes('a,Name,,,14,120,14,,PHL,'), 'here.csv', 'Divisoria')


def test_excel_template_aliases_and_blank_formatted_rows():
    book = Workbook()
    sheet = book.active
    sheet.append(['unique_id', 'poi_name', 'display_point_latitude', 'display_point_longitude', 'routing_latitude', 'routing_longitude', 'Remarks'])
    sheet.append(['00042', 'Toko', -6.18, 106.81, None, None, 'Original remarks'])
    sheet.cell(100, 1).number_format = '@'
    buffer = BytesIO()
    book.save(buffer)
    rows, columns = parse_file(buffer.getvalue(), 'customer.xlsx', 'Kampung Bali')
    assert len(rows) == 1
    assert rows[0]['place_id'] == '00042'
    assert rows[0]['country'] == 'IDN'
    assert rows[0]['routing_latitude'] is None
    assert rows[0]['raw']['Remarks'] == 'Original remarks'


@pytest.mark.parametrize('content', [b'placeid,place_id\nx,y', b'placeid,,name1\nx,y,z', b'name1,latitude,longitude\nx,1,2'])
def test_ambiguous_or_missing_headers_rejected(content):
    with pytest.raises(ImportInvalid):
        parse_file(content, 'invalid.csv', 'Divisoria')


def test_empty_template_is_not_a_dataset():
    with pytest.raises(ImportInvalid, match='no populated'):
        parse_file(HEADER.encode(), 'empty.csv', 'Divisoria')


def test_bad_excel_reports_validation_error():
    with pytest.raises(ImportInvalid, match='Cannot read'):
        parse_file(b'not a workbook', 'broken.xlsx', 'Divisoria')
