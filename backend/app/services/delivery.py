"""Customer delivery: exact HERE XLSX templates, pre-submission gates, manifest, QC checklist, reconciliation.

Follows the SEA Places POC Supplier Delivery Guide v1.2 §§5–8 and Appendix A. Templates are written in
place (original sheet names, headers, order and formatting). The field dictionary is not in the package, so
each column's mapping is an explicit, documented interpretation (ASSUMPTIONS) to confirm with HERE.
"""
import hashlib
import io
import re
import zipfile
from datetime import date

from openpyxl import Workbook, load_workbook

from .aoi import contains
from .matching import haversine_m
from .reference import RESOURCES, categories, data as reference_data, profanity_hits
from .review_rules import DELETE_REASONS

ISO2 = {"PHL": "PH", "IDN": "ID", "THA": "TH"}
ACTIONS = ("new", "update", "delete")
ACTION_LABEL = {"new": "New", "update": "Update", "delete": "Delete"}
# Provider-restricted URLs never leave the platform.
RESTRICTED_URL = re.compile(r"(google\.|goo\.gl|g\.page|grab\.com|maps\.apple|apple\.com/maps|waze\.com|here\.com)", re.I)
ROUTING_MAX_OFFSET_M = 300
ASSUMPTIONS = [
    "No field dictionary was supplied: column mappings below are JSAN interpretations pending HERE confirmation.",
    "New: unique_id is the stable JSAN master POI ID; latitude/Longitude repeat the display point.",
    "New: website is the official website; URL is the official branch/listing page used as evidence.",
    "Update: poi_name keeps the HERE name; Updated Name is filled only when the name changes.",
    "Update/Delete: values not reviewed are carried from the HERE baseline (Admin N <- adminN, FoodNM <- food_name).",
    "Delete: POI Status carries the delete reason; status keeps the HERE baseline status.",
    "Last Update is the reviewer's verification date (YYYY-MM-DD).",
    "groundtruth image URL is exported only for JSAN field photos; map-provider imagery is never exported.",
]


def _final(record, field):
    value = ((record["review"].get("attributes") or {}).get(field) or {}).get("final")
    return value if value not in ("", None) else None


def _here(record, key):
    value = (record.get("here_raw") or {}).get(key)
    return value if value not in ("", None) else None


def _pick(record, field, here_key=None):
    """Reviewer's final value, else the HERE baseline value."""
    value = _final(record, field)
    return value if value is not None else (_here(record, here_key) if here_key else None)


def _coord(value):
    try:
        return round(float(value), 7)
    except (TypeError, ValueError):
        return None


def _display(record):
    lat = _coord(_final(record, "latitude")) if _final(record, "latitude") is not None else _coord((record.get("here") or {}).get("latitude"))
    lon = _coord(_final(record, "longitude")) if _final(record, "longitude") is not None else _coord((record.get("here") or {}).get("longitude"))
    return lat, lon


def _routing(record):
    lat = _final(record, "routing_latitude")
    lon = _final(record, "routing_longitude")
    if lat is None and lon is None:
        lat, lon = (record.get("here") or {}).get("routing_latitude"), (record.get("here") or {}).get("routing_longitude")
    return _coord(lat), _coord(lon)


def _ground_truth_url(record):
    for item in record["review"].get("evidence") or []:
        url = (item.get("url") or "").strip()
        if item.get("type") == "field_observation" and url and not RESTRICTED_URL.search(url):
            return url
    return None


def _branch_url(record):
    for item in record["review"].get("evidence") or []:
        url = (item.get("url") or "").strip()
        if item.get("type") in ("official_website", "official_social") and url and not RESTRICTED_URL.search(url):
            return url
    return None


def _changed(record):
    return [f for f, v in (record["review"].get("attributes") or {}).items() if (v or {}).get("status") == "corrected"]


def _reason(record):
    review = record["review"]
    if record["action"] == "delete":
        text = DELETE_REASONS.get(review.get("delete_reason"), review.get("delete_reason") or "")
        if review.get("duplicate_of"):
            text += f" (duplicate of {review['duplicate_of']})"
        rule = (review.get("rule_check") or {}).get("closure", {}).get("rule")
        return f"{text}; rule {rule}" if rule and rule != "D7" else text
    if record["action"] == "update":
        return "Updated: " + ", ".join(_changed(record))
    return "New POI"


def _remarks(record):
    remarks = (record["review"].get("remarks") or "").strip()
    return RESTRICTED_URL.sub("[map provider]", remarks) or None


def _last_update(record):
    return record["review"].get("verification_date")


def _poi_status(record):
    status = _final(record, "poi_status")
    if record["action"] == "delete":
        return DELETE_REASONS.get(record["review"].get("delete_reason"), "Deleted")
    return status or ("ACTIVE" if record["action"] == "new" else _here(record, "status"))


COLUMNS = {
    "new": {
        "unique_id": lambda r: r["jsan_id"], "poi_name": lambda r: _final(r, "name"),
        "Transliteration": lambda r: _final(r, "transliteration"), "category": lambda r: _final(r, "category_code"),
        "POI Status": _poi_status, "Last Update": _last_update,
        "latitude": lambda r: _display(r)[0], "Longitude": lambda r: _display(r)[1],
        "display_point_latitude": lambda r: _display(r)[0], "display_point_longitude": lambda r: _display(r)[1],
        "routing_latitude": lambda r: _routing(r)[0], "routing_longitude": lambda r: _routing(r)[1],
        "unparsed_address_name": lambda r: _final(r, "address"), "house_number": lambda r: _final(r, "house_number"),
        "street_name": lambda r: _final(r, "street_name"), "RT": lambda r: _final(r, "rt"), "RW": lambda r: _final(r, "rw"),
        "Admin 5": lambda r: _final(r, "admin5"), "Admin 4": lambda r: _final(r, "admin4"), "Admin 3": lambda r: _final(r, "admin3"),
        "Admin 2": lambda r: _final(r, "admin2"), "Admin 1": lambda r: _final(r, "admin1"),
        "postal_code": lambda r: _final(r, "postal_code"), "phone number": lambda r: _final(r, "phone"),
        "Mobile": lambda r: _final(r, "mobile"), "URL": _branch_url, "Mail address": lambda r: _final(r, "email"),
        "operating hours": lambda r: _final(r, "opening_hours"), "website": lambda r: _final(r, "website"), "Remarks": _remarks,
    },
    "update": {
        "uniqueID": lambda r: r["here_place_id"], "poi_name": lambda r: _here(r, "name1"),
        "Updated Name": lambda r: _final(r, "name") if "name" in _changed(r) else None,
        "Transliteration": lambda r: _pick(r, "transliteration", "name2"), "Category": lambda r: _pick(r, "category_code", "primarycategory"),
        "POI Status": _poi_status, "Last Update": _last_update,
        "Latitude": lambda r: _display(r)[0], "Longitude": lambda r: _display(r)[1],
        "displaylatitude": lambda r: _display(r)[0], "displaylongitude": lambda r: _display(r)[1],
        "routing_latitude": lambda r: _routing(r)[0], "routing_longitude": lambda r: _routing(r)[1],
        "chainname": lambda r: _pick(r, "chain_name", "chainname"), "cqs": lambda r: _here(r, "cqs"), "status": lambda r: _here(r, "status"),
        "unparsed_address_name": lambda r: _pick(r, "address", "upaddress"), "house_number": lambda r: _pick(r, "house_number", "hno"),
        "streetname": lambda r: _pick(r, "street_name", "streetname"), "RT": lambda r: _final(r, "rt"), "RW": lambda r: _final(r, "rw"),
        "Admin 1": lambda r: _pick(r, "admin1", "admin1"), "Admin 2": lambda r: _pick(r, "admin2", "admin2"),
        "Admin 3": lambda r: _pick(r, "admin3", "admin3"), "Admin 4": lambda r: _pick(r, "admin4", "admin4"),
        "Admin 5": lambda r: _pick(r, "admin5", "admin5"), "postalcode": lambda r: _pick(r, "postal_code", "postalcode"),
        "FoodNM": lambda r: _here(r, "food_name"), "WEBADDRESS": lambda r: _pick(r, "website", "webaddress"),
        "TOLLFREE": lambda r: _pick(r, "tollfree", "tollfree_numbers"), "URL": _branch_url,
        "PHONE": lambda r: _pick(r, "phone", "phone_numbers"), "MOBILE": lambda r: _pick(r, "mobile", "mobile_numbers"),
        "EMAIL": lambda r: _pick(r, "email", "email"), "OPERATING_HOURS": lambda r: _pick(r, "opening_hours", "opening_hours"),
        "Remarks": _remarks, "groundtruth image URL": _ground_truth_url, "Final Action": lambda r: "UPDATE",
        "Decision/Delete Reason": _reason,
    },
    "delete": {
        "UniqueID": lambda r: r["here_place_id"], "POI_Name": lambda r: _here(r, "name1"),
        "Transliteration": lambda r: _here(r, "name2"), "Category": lambda r: _here(r, "primarycategory"),
        "POI Status": _poi_status, "Last Update": _last_update,
        "Latitude": lambda r: _display(r)[0], "Longitude": lambda r: _display(r)[1],
        "displaylatitude": lambda r: _display(r)[0], "displaylongitude": lambda r: _display(r)[1],
        "routinglatitude": lambda r: _routing(r)[0], "routinglongitude": lambda r: _routing(r)[1],
        "chainname": lambda r: _here(r, "chainname"), "cqs": lambda r: _here(r, "cqs"), "status": lambda r: _here(r, "status"),
        "country": lambda r: _here(r, "country"), "House number": lambda r: _here(r, "hno"),
        "streetname": lambda r: _here(r, "streetname"), "upaddress": lambda r: _here(r, "upaddress"),
        "postalcode": lambda r: _here(r, "postalcode"), "Admin 5": lambda r: _here(r, "admin5"), "Admin 4": lambda r: _here(r, "admin4"),
        "Admin 3": lambda r: _here(r, "admin3"), "Admin 2": lambda r: _here(r, "admin2"), "Admin 1": lambda r: _here(r, "admin1"),
        "FoodNM": lambda r: _here(r, "food_name"), "WEBADDRESS": lambda r: _here(r, "webaddress"),
        "PHONE": lambda r: _here(r, "phone_numbers"), "MOBILE": lambda r: _here(r, "mobile_numbers"),
        "TOLLFREE": lambda r: _here(r, "tollfree_numbers"), "EMAIL": lambda r: _here(r, "email"), "Remarks": _remarks,
        "groundtruth image URL": _ground_truth_url, "Final Action": lambda r: "DELETE", "Decision/Delete Reason": _reason,
    },
}


def template_path(action):
    return RESOURCES / "templates" / reference_data()["templates"][action]["file"]


def template_headers(action):
    wb = load_workbook(template_path(action), read_only=True)
    ws = wb.worksheets[0]
    headers = [c for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    while headers and headers[-1] in (None, ""):
        headers.pop()
    title = ws.title
    wb.close()
    return title, [str(h) for h in headers]


def check_templates():
    """File-level gate: template unchanged since the reference build, and every header has a mapping."""
    issues = []
    for action in ACTIONS:
        path = template_path(action)
        if hashlib.sha256(path.read_bytes()).hexdigest() != reference_data()["templates"][action]["sha256"]:
            issues.append(f"{ACTION_LABEL[action]} template changed since the reference build; re-run build_reference_data.py.")
        _, headers = template_headers(action)
        unmapped = [h for h in headers if h not in COLUMNS[action]]
        extra = [h for h in COLUMNS[action] if h not in headers]
        if unmapped or extra:
            issues.append(f"{ACTION_LABEL[action]} template headers don't match the mapping (unmapped: {unmapped}; missing: {extra}).")
    return issues


def record_checks(record, aoi, country, here_ids, seen_ids):
    """Record-level gates. Returns (blockers, majors) as lists of messages."""
    blockers, majors = [], []
    action, review = record["action"], record["review"]
    if not record.get("qc_independent"):
        blockers.append("QC approval missing or not independent of the reviewer")
    if not review.get("verification_date"):
        blockers.append("No last verified date")
    if (review.get("rule_check") or {}).get("errors"):
        blockers.append("Evidence rules not met")
    if not record.get("sources_licensed", True):
        blockers.append("A contributing source has no recorded licence/permission")
    identifier = record["jsan_id"] if action == "new" else record.get("here_place_id")
    if not identifier:
        blockers.append("Missing unique ID / HERE place ID")
    elif action != "new" and identifier not in here_ids:
        blockers.append("HERE place ID is not in the supplied baseline")
    elif (action, identifier) in seen_ids:
        blockers.append("Duplicate ID in the same action file")
    seen_ids.add((action, identifier))
    if action == "new":
        for field, label in (("name", "name"), ("category_code", "category")):
            if not _final(record, field):
                majors.append(f"Mandatory {label} missing")
    category = _final(record, "category_code") if action == "new" or "category_code" in _changed(record) else None
    if category and category not in categories():
        majors.append(f"Category {category} not in the supplied HERE category reference")
    lat, lon = _display(record)
    if lat is None or lon is None:
        majors.append("Display coordinates missing or invalid")
    elif action != "delete" and not contains(aoi, lon, lat):
        majors.append("Display point outside the assigned AOI")
    rlat, rlon = _routing(record)
    if lat is not None and rlat is not None and rlon is not None and haversine_m(lat, lon, rlat, rlon) > ROUTING_MAX_OFFSET_M:
        majors.append(f"Routing point more than {ROUTING_MAX_OFFSET_M} m from the display point (possibly transposed)")
    for field in ("name", "transliteration"):
        hits = profanity_hits(_final(record, field), country)
        if hits:
            majors.append(f"Profanity check: {field} contains {', '.join(hits[:3])}")
    hits = profanity_hits(_remarks(record), country)
    if hits:
        majors.append("Profanity check: remarks")
    return blockers, majors


def cross_file_conflicts(records):
    """The same HERE record may appear in only one action file; a duplicate's survivor can't be deleted too."""
    by_id = {}
    for r in records:
        if r["action"] != "new" and r.get("here_place_id"):
            by_id.setdefault(r["here_place_id"], []).append(r["action"])
    conflicts = {pid for pid, actions in by_id.items() if len(set(actions)) > 1}
    deleted = {r["here_place_id"] for r in records if r["action"] == "delete"}
    for r in records:
        survivor = r["review"].get("duplicate_of")
        if r["action"] == "delete" and survivor and survivor in deleted:
            conflicts.add(r["here_place_id"])
    return conflicts


def _write_cell(ws, row, col, value):
    cell = ws.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str):
        cell.data_type = "s"  # literal text: a leading "=" never becomes a formula


def fill_template(action, records):
    wb = load_workbook(template_path(action))
    ws = wb.worksheets[0]
    _, headers = template_headers(action)
    for r_index, record in enumerate(records, start=2):
        for c_index, header in enumerate(headers, start=1):
            value = COLUMNS[action][header](record)
            _write_cell(ws, r_index, c_index, value if value not in ("",) else None)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename(supplier, country, aoi, action, version, day=None):
    day = (day or date.today()).strftime("%Y%m%d")
    return f"{supplier}_{ISO2.get(country, country)}_{re.sub(r'[^A-Za-z0-9]', '', aoi.title())}_{ACTION_LABEL[action]}_{day}_v{version}.xlsx"


def _simple_workbook(title, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    for r_index, row in enumerate(rows, start=1):
        for c_index, value in enumerate(row, start=1):
            _write_cell(ws, r_index, c_index, value)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_package(*, supplier, contact, aoi, country, version, records, held_back, majors, here_total, approved_total):
    """Return {kind: (filename, bytes, row_count, customer_facing)} for the delivery package."""
    files = {}
    counts = {a: 0 for a in ACTIONS}
    for action in ACTIONS:
        rows = [r for r in records if r["action"] == action]
        counts[action] = len(rows)
        name = filename(supplier, country, aoi, action, version)
        files[action] = (name, fill_template(action, rows), len(rows), True)
        # Reopen and reconcile the written workbook against what we intended to write.
        check = load_workbook(io.BytesIO(files[action][1]), read_only=True)
        written = sum(1 for row in check.worksheets[0].iter_rows(min_row=2, values_only=True) if any(v not in (None, "") for v in row))
        check.close()
        if written != len(rows):
            raise RuntimeError(f"{ACTION_LABEL[action]} file reconciliation failed: wrote {written}, expected {len(rows)}.")
    today = date.today().isoformat()
    manifest = [
        ["Field", "Value"], ["Supplier", supplier], ["Contact", contact], ["Submission version", version],
        ["First complete submission", "Yes" if version.startswith("1.") else "No"], ["Delivery date (UTC)", today],
        ["AOI", f"{aoi} ({country})"], ["AOI coverage status", "Partial — limited to permitted sources reviewed to date"],
        ["Record totals", f"New {counts['new']}, Update {counts['update']}, Delete {counts['delete']}, Total {sum(counts.values())}"],
        *[["File", f"{files[a][0]} — {ACTION_LABEL[a]} — {files[a][2]} rows — v{version}"] for a in ACTIONS],
        ["Coverage limitations", "Map-provider sources (Google, Grab, Apple) were not used as data sources. "
                                 f"{here_total} HERE baseline records; {approved_total} QC-approved decisions."],
        ["QC declaration", "Blocker checks passed for every exported row; records with Blockers were withheld."
                           + (f" {len(majors)} Major issue(s) remain and are listed in the QC checklist." if majors else " No Major issues remain.")],
        ["Schema deviations", "None. Template headers, order and sheet names are unchanged."],
        *[["Mapping assumption", a] for a in ASSUMPTIONS],
    ]
    files["manifest"] = (f"{supplier}_{ISO2.get(country, country)}_{re.sub(r'[^A-Za-z0-9]', '', aoi.title())}_Manifest_{today.replace('-', '')}_v{version}.xlsx",
                         _simple_workbook("Manifest", manifest), len(manifest) - 1, True)
    checklist = [["Check", "Status", "Notes"],
                 ["HERE baseline and AOI package used as source of truth", "Done", aoi],
                 ["Latest New, Update and Delete templates completed", "Done", "Original templates, unchanged structure"],
                 ["Mandatory fields complete and formatted", "Done" if not majors else "See issues", f"{len(majors)} Major issue(s)"],
                 ["Unique IDs, duplicates and cross-file conflicts checked", "Done", f"{len(held_back)} record(s) withheld"],
                 ["HERE categories mapped; unmapped disclosed", "Done", "See category mapping workbook"],
                 ["Display and routing coordinates sanity-checked", "Done", f"AOI containment; routing within {ROUTING_MAX_OFFSET_M} m"],
                 ["Address hierarchy and postal codes checked", "Partial", "Structural checks only; no postal reference supplied"],
                 ["Last verified date present for every record", "Done", "Records without it were withheld"],
                 ["Parent-child and chain relationships checked", "Partial", "Chain names checked; no relationship records in this package"],
                 ["Profanity/text hygiene checks completed", "Done", "HERE profanity list, country/whole-name rules"],
                 ["Delivery manifest completed and row counts reconciled", "Done", "Workbooks reopened and counted"],
                 ["QC checklist completed with no unresolved Blockers", "Done", "Independent QC approval required for every row"],
                 ["Known limitations and approved deviations documented", "Done", "See manifest"],
                 *[["Major issue", m["record"], m["issue"]] for m in majors]]
    files["qc_checklist"] = (f"{supplier}_QC_Checklist_{today.replace('-', '')}_v{version}.xlsx", _simple_workbook("QC Checklist", checklist), len(checklist) - 1, True)
    used = {}
    for r in records:
        code = _final(r, "category_code") or _here(r, "primarycategory")
        used.setdefault(code or "(none)", 0)
        used[code or "(none)"] += 1
    mapping = [["HERE category code", "HERE category name", "Records", "Mapped"]] + \
              [[code, categories().get(code, ""), n, "Yes" if code in categories() else "No — disclosed"] for code, n in sorted(used.items())]
    files["category_mapping"] = (f"{supplier}_Category_Mapping_{today.replace('-', '')}_v{version}.xlsx", _simple_workbook("Category mapping", mapping), len(mapping) - 1, True)
    reconciliation = [["Record", "Action", "Status", "Reason"]] + \
                     [[r.get("jsan_id") if r["action"] == "new" else r.get("here_place_id"), r["action"], "Exported", ""] for r in records] + \
                     [[h["record"], h["action"], "Withheld", h["reason"]] for h in held_back]
    files["reconciliation"] = (f"INTERNAL_Reconciliation_{today.replace('-', '')}_v{version}.xlsx", _simple_workbook("Reconciliation", reconciliation), len(reconciliation) - 1, False)
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content, _, customer in files.values():
            if customer:
                zf.writestr(name, content)
    files["package"] = (f"{supplier}_{ISO2.get(country, country)}_{re.sub(r'[^A-Za-z0-9]', '', aoi.title())}_Delivery_{today.replace('-', '')}_v{version}.zip",
                        package.getvalue(), sum(counts.values()), True)
    return files, counts
