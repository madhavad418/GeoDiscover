"""Matching and demo proposals for HERE-to-provider POI comparisons."""
import hashlib
import math
import re
import unicodedata

PROVIDERS = (
    {"id": "google", "name": "Google Maps", "color": "#4285F4"},
    {"id": "apple", "name": "Apple Maps", "color": "#FC3C44"},
    {"id": "grab", "name": "Grab Maps", "color": "#00B14F"},
)

ACTION_COLORS = {"new": "#5fd39a", "update": "#e8c27a", "delete": "#ff6b8b"}
EARTH_RADIUS_METERS = 6_371_000
MATCH_DISTANCE_METERS = 100


def _first(record, *keys):
    normalized = {re.sub(r"[^a-z0-9]", "", str(key).casefold()): value for key, value in record.items()}
    for key in keys:
        value = normalized.get(re.sub(r"[^a-z0-9]", "", key.casefold()))
        if value is not None and str(value).strip():
            return value
    return None


def normalize_place(record):
    """Read common HERE and supplier delivery field spellings into one comparison shape."""
    latitude = _first(record, "latitude", "displaylatitude", "displaypointlatitude", "lat")
    longitude = _first(record, "longitude", "displaylongitude", "displaypointlongitude", "lon", "lng")
    try:
        latitude, longitude = float(latitude), float(longitude)
        if not math.isfinite(latitude) or not math.isfinite(longitude):
            latitude = longitude = None
    except (TypeError, ValueError):
        latitude = longitude = None
    return {
        "place_id": _first(record, "placeid", "uniqueid", "unique_id", "poi_id", "poiid"),
        "name": _first(record, "name1", "poi_name", "poiname", "name"),
        "category_code": _first(record, "primarycategory", "category_code", "category"),
        "category_name": _first(record, "primarycategorynm", "category_name", "categorynm"),
        "address": _first(record, "upaddress", "unparsedaddressname", "address"),
        "transliteration": _first(record, "transliteration"),
        "phone": _first(record, "phone", "phone_numbers", "telephone", "tel"),
        "mobile": _first(record, "mobile", "mobile_numbers"),
        "tollfree": _first(record, "tollfree", "tollfree_numbers"),
        "email": _first(record, "email", "mail_address", "e_mail"),
        "website": _first(record, "website", "webaddress", "url"),
        "opening_hours": _first(record, "opening_hours", "operating_hours", "hours"),
        "street_name": _first(record, "streetname", "street_name"),
        "house_number": _first(record, "hno", "house_number", "housenumber"),
        "postal_code": _first(record, "postalcode", "postal_code", "postcode"),
        "latitude": latitude,
        "longitude": longitude,
    }


def _text(value):
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", str(value)).casefold())
    text = "".join(character for character in text if not unicodedata.combining(character))
    return " ".join(re.findall(r"\w+", text, flags=re.UNICODE))


def _distance_meters(a, b):
    if None in (a.get("latitude"), a.get("longitude"), b.get("latitude"), b.get("longitude")):
        return None
    lat1, lon1, lat2, lon2 = map(math.radians, (a["latitude"], a["longitude"], b["latitude"], b["longitude"]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    haversine = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * math.asin(min(1, math.sqrt(haversine)))


def _find_match(baseline, candidate):
    candidate_id = candidate.get("matched_place_id") or candidate.get("place_id")
    if candidate_id:
        for base in baseline:
            if str(base.get("place_id") or "") == str(candidate_id):
                return base, "place_id", 1.0

    candidate_name = _text(candidate.get("name"))
    if not candidate_name:
        return None, None, 0.0
    best = None
    for base in baseline:
        if _text(base.get("name")) != candidate_name:
            continue
        base_category = _text(base.get("category_code") or base.get("category_name"))
        candidate_category = _text(candidate.get("category_code") or candidate.get("category_name"))
        if base_category and candidate_category and base_category != candidate_category:
            continue
        distance = _distance_meters(base, candidate)
        if distance is None or distance > MATCH_DISTANCE_METERS:
            continue
        score = 0.95
        if best is None or score > best[1]:
            best = (base, score)
    return (best[0], "name_category_distance", best[1]) if best else (None, None, 0.0)


def classify_candidate(baseline, candidate):
    """Return new/update/delete/unchanged/unmatched; missing provider coverage is not a deletion."""
    baseline = [normalize_place(record) for record in baseline]
    source = candidate
    candidate = normalize_place(source)
    candidate["operation"] = str(source.get("operation") or "").strip().casefold()
    candidate["matched_place_id"] = source.get("matched_place_id")
    match, matched_by, confidence = _find_match(baseline, candidate)
    if candidate.get("operation") == "delete":
        if match is None:
            return {"action": "unmatched", "match": None, "matched_by": None, "confidence": 0.0, "changed_fields": []}
        return {"action": "delete", "match": match, "matched_by": matched_by, "confidence": confidence,
                "changed_fields": []}
    if match is None:
        return {"action": "new", "match": None, "matched_by": None, "confidence": 0.0, "changed_fields": []}

    changed = []
    for field in (
        "name", "category_code", "category_name", "address", "transliteration",
        "phone", "mobile", "tollfree", "email", "website", "opening_hours",
        "street_name", "house_number", "postal_code",
    ):
        if candidate.get(field) is not None and _text(match.get(field)) != _text(candidate.get(field)):
            changed.append(field)
    distance = _distance_meters(match, candidate)
    if distance is not None and distance > 5:
        changed.append("location")
    action = "update" if changed else "unchanged"
    return {"action": action, "match": match, "matched_by": matched_by, "confidence": confidence,
            "changed_fields": changed}


def build_demo_proposals(records, aoi):
    """Create visibly synthetic new/update/delete examples based on a few real HERE points."""
    baseline = [normalize_place(record) for record in records]
    baseline = [record for record in baseline if record.get("place_id") and record.get("name")]
    if not baseline:
        return {provider["id"]: [] for provider in PROVIDERS}

    by_provider = {}
    for provider_index, provider in enumerate(PROVIDERS):
        proposals = []
        update_base = baseline[provider_index % len(baseline)]
        update = {**update_base, "name": f'{update_base["name"]} - {provider["name"]} demo update'}
        if update.get("address"):
            update["address"] = f'{update["address"]}, demo correction'
        result = classify_candidate(baseline, {**update, "matched_place_id": update_base["place_id"]})
        proposals.append(_proposal(provider, "update", update_base, update, result,
                                   "Simulated provider correction to a matched HERE place."))

        delete_base = baseline[(provider_index + 1) % len(baseline)]
        deleted = {**delete_base, "operation": "delete"}
        result = classify_candidate(baseline, deleted)
        proposals.append(_proposal(provider, "delete", delete_base, None, result,
                                   "Simulated explicit removal proposal; absence alone never triggers a delete."))

        anchor = baseline[provider_index % len(baseline)]
        delta = (provider_index + 1) * 0.00015
        latitude = max(-89.999, min(89.999, anchor["latitude"] + delta))
        longitude = max(-179.999, min(179.999, anchor["longitude"] + delta))
        new_place = {
            "place_id": f'demo-{provider["id"]}-poi-{provider_index + 1}',
            "name": f'{aoi} {provider["name"]} demo place',
            "category_code": "100-1000-0000",
            "category_name": "Restaurant",
            "address": f'{aoi} (simulated provider listing)',
            "latitude": latitude,
            "longitude": longitude,
        }
        result = classify_candidate(baseline, new_place)
        proposals.append(_proposal(provider, "new", None, new_place, result,
                                   "Simulated provider listing with no confident HERE match."))
        by_provider[provider["id"]] = proposals
    return by_provider


def _proposal(provider, expected_action, base, proposed, result, reason):
    action = result["action"]
    if action != expected_action:
        raise ValueError(f"Demo proposal was classified as {action}, expected {expected_action}.")
    identity = base.get("place_id") if base else proposed.get("place_id")
    record_key = hashlib.sha256(f'{provider["id"]}:{action}:{identity}'.encode()).hexdigest()[:32]
    return {
        "key": record_key,
        "action": action,
        "reason": reason,
        "match_method": result["matched_by"],
        "match_confidence": result["confidence"],
        "changed_fields": result["changed_fields"],
        "base": base,
        "proposed": proposed,
        "review_status": "pending",
        "review_note": "",
        "reviewed_at": None,
    }
