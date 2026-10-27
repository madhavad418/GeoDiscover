"""Parse permitted-source POI observations (CSV/XLSX) into normalized, validated records.

Source policy: map-provider content (Google, Grab, Apple, Waze, HERE) is reference-only and is rejected here.
Each batch must carry a licence/permission reference; values that a source didn't provide stay blank.
"""
import csv
import io
import math
import re
from datetime import date, datetime
from urllib.parse import urlsplit

from openpyxl import load_workbook

from .aoi import contains
from .customer_import import MAX_BYTES, MAX_ROWS, ImportInvalid, key, string
from .reference import resolve_category

SOURCE_TYPES = {
    "official_website": "Official business website / branch page",
    "store_locator": "Official store locator",
    "official_social": "Official social media (owner-managed)",
    "licensed_directory": "Licensed directory / Yellow Pages",
    "licensed_vendor": "Licensed vendor dataset",
    "field_observation": "Verified field observation",
    "other_permitted": "Other authorized website or registry",
}
MAP_PROVIDER_HOSTS = ("google.", "goo.gl", "g.page", "grab.com", "grabmaps", "maps.apple", "apple.com/maps",
                      "waze.com", "here.com", "wego.here")
STATUSES = {
    "open": "open", "operational": "open", "active": "open", "existing": "open", "operating": "open",
    "temporarily closed": "temporarily_closed", "temporarily_closed": "temporarily_closed", "temp closed": "temporarily_closed",
    "permanently closed": "permanently_closed", "permanently_closed": "permanently_closed", "closed": "permanently_closed",
    "moved": "moved", "relocated": "moved", "not found": "not_found", "not_found": "not_found",
}
FIELDS = {
    "source_record_id": ["sourcerecordid", "sourceid", "recordid", "listingid", "id", "uniqueid"],
    "name": ["name", "businessname", "poiname", "name1", "title"],
    "alt_names": ["altname", "alternatename", "localname", "name2", "transliteration", "othernames"],
    "category_code": ["herecategorycode", "categorycode", "primarycategory"],
    "category_name": ["category", "categoryname", "type", "businesstype"],
    "address": ["address", "fulladdress", "upaddress"],
    "street_name": ["streetname", "street"],
    "house_number": ["housenumber", "hno", "buildingnumber"],
    "unit": ["unit", "unitnumber", "stall", "stallnumber", "shopnumber"],
    "postal_code": ["postalcode", "postcode", "zip", "zipcode"],
    "phones": ["phone", "phones", "phonenumber", "phonenumbers", "telephone", "mobile", "tel"],
    "website": ["website", "branchurl", "storeurl", "webaddress", "url"],
    "social_url": ["socialurl", "facebook", "instagram", "social"],
    "opening_hours": ["openinghours", "hours", "operatinghours"],
    "latitude": ["latitude", "lat", "displaylatitude"],
    "longitude": ["longitude", "lon", "lng", "displaylongitude"],
    "routing_latitude": ["routinglatitude", "entrancelatitude"],
    "routing_longitude": ["routinglongitude", "entrancelongitude"],
    "business_status": ["businessstatus", "status"],
    "observed_on": ["observedon", "observedat", "publishedon", "publishedat", "lastseen", "lastupdated", "verifiedon"],
    "source_url": ["sourceurl", "listingurl", "pageurl"],
    "here_place_id": ["hereplaceid", "placeid"],
}
REQUIRED = ("source_record_id", "name", "latitude", "longitude")


def _column_map(headers):
    normalized = {key(h): h for h in headers}
    out = {}
    for field, aliases in FIELDS.items():
        found = next((normalized[a] for a in aliases if a in normalized), None)
        if found:
            out[field] = found
    missing = [f for f in REQUIRED if f not in out]
    if missing:
        raise ImportInvalid(f"Missing required column(s): {', '.join(missing)}. "
                            f"Accepted names include: {'; '.join(f'{m}: {FIELDS[m][0]}' for m in missing)}.")
    return out


def _date(value, field):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value).strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                parsed = datetime.strptime(text[:19], fmt).date()
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"{field}: use YYYY-MM-DD (got {text[:20]!r})")
    if parsed > date.today():
        raise ValueError(f"{field} is in the future")
    return parsed


def _coordinate_pair(lat, lon, optional=False):
    if optional and lat in (None, "") and lon in (None, ""):
        return None, None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        raise ValueError("A complete numeric latitude/longitude pair is required") from None
    if not (math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180):
        raise ValueError("Coordinates must be WGS84 decimal degrees")
    return lat, lon


def _map_provider(url):
    if not url:
        return False
    text = str(url).lower()
    host = urlsplit(text if "://" in text else "https://" + text).netloc + urlsplit(text if "://" in text else "https://" + text).path
    return any(marker in host for marker in MAP_PROVIDER_HOSTS)


def _tables(content, filename):
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "csv":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ImportInvalid("Save the CSV with UTF-8 encoding and upload it again.") from None
        reader = csv.reader(io.StringIO(text))
        return [("CSV", next(reader, []), reader)], None
    if ext == "xlsx":
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = next((s for s in workbook if s.sheet_state == "visible"), None)
        if sheet is None:
            raise ImportInvalid("The workbook has no visible sheet.")
        rows = sheet.iter_rows(values_only=True)
        return [(sheet.title, next(rows, []), rows)], workbook
    raise ImportInvalid("Supported formats are .csv and .xlsx.")


def parse_observations(content: bytes, filename: str, aoi: str):
    """Return (records, columns, report). Rejects the whole file on row errors so batches stay consistent."""
    if len(content) > MAX_BYTES:
        raise ImportInvalid("Maximum file size is 25 MB.")
    tables, workbook = _tables(content, filename)
    try:
        sheet, header, rows = tables[0]
        headers = [string(h) for h in header]
        while headers and not headers[-1]:
            headers.pop()
        if not headers or any(not h for h in headers) or len({key(h) for h in headers}) != len(headers):
            raise ImportInvalid("Headers must be nonblank and unique.")
        columns = _column_map(headers)
        records, issues, seen = [], [], set()
        outside = 0
        for rownum, values in enumerate(rows, 2):
            if not any(string(v) for v in values):
                continue
            if len(records) + len(issues) >= MAX_ROWS:
                raise ImportInvalid("Maximum import size is 100,000 records.")
            raw = {h: (values[i] if i < len(values) else None) for i, h in enumerate(headers)}
            get = lambda field: raw.get(columns[field]) if field in columns else None  # noqa: E731
            try:
                record_id = string(get("source_record_id"))
                name = string(get("name"))
                if not record_id or not name:
                    raise ValueError("Source record ID and name are required")
                if record_id in seen:
                    raise ValueError(f"Duplicate source record ID: {record_id}")
                seen.add(record_id)
                for field in ("source_url", "website", "social_url"):
                    if _map_provider(get(field)):
                        raise ValueError(f"{field} points to a map provider; map-provider content is reference-only")
                lat, lon = _coordinate_pair(get("latitude"), get("longitude"))
                rlat, rlon = _coordinate_pair(get("routing_latitude"), get("routing_longitude"), optional=True)
                if not contains(aoi, lon, lat):
                    outside += 1
                    continue  # out of the HERE-supplied AOI: outside delivery scope
                status_text = string(get("business_status")).casefold().replace("-", " ")
                status = STATUSES.get(status_text, "unknown") if status_text else "unknown"
                if status_text and status == "unknown":
                    raise ValueError(f"Unknown business status {status_text!r}")
                code, category_name = resolve_category(string(get("category_code")), string(get("category_name")))
                phones = [p for p in re.split(r"[;,|/]", string(get("phones"))) if p.strip()]
                alt = [a.strip() for a in re.split(r"[;|]", string(get("alt_names"))) if a.strip()]
                records.append({
                    "source_record_id": record_id, "name": name, "alt_names": alt,
                    "category_code": code, "category_name": category_name or None,
                    "address": string(get("address")) or None, "street_name": string(get("street_name")) or None,
                    "house_number": string(get("house_number")) or None, "unit": string(get("unit")) or None,
                    "postal_code": string(get("postal_code")) or None, "phones": [p.strip() for p in phones],
                    "website": string(get("website")) or None, "social_url": string(get("social_url")) or None,
                    "opening_hours": string(get("opening_hours")) or None,
                    "latitude": lat, "longitude": lon, "routing_latitude": rlat, "routing_longitude": rlon,
                    "business_status": status, "observed_on": _date(get("observed_on"), "observed_on"),
                    "source_url": string(get("source_url")) or None, "here_place_id": string(get("here_place_id")) or None,
                    "raw": {h: string(v) for h, v in raw.items()},
                })
            except ValueError as exc:
                if len(issues) < 50:
                    issues.append({"sheet": sheet, "row": rownum, "message": str(exc)})
        if issues:
            raise ImportInvalid("Import rejected. Fix the reported rows and retry; nothing was saved. Showing up to 50 issues.", issues)
        if not records:
            raise ImportInvalid("No observations inside the selected AOI." if outside else "The file has no populated rows.")
        report = {"accepted": len(records), "outside_aoi": outside, "mapped_columns": columns,
                  "uncategorized": sum(1 for r in records if not r["category_code"])}
        return records, headers, report
    finally:
        if workbook:
            workbook.close()
