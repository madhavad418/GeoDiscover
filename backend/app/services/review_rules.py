"""Decision validation for review and QC.

Sources: POI Evidence Weighting & Confidence Scoring Workbook (weights, rubric, minimum evidence §4b) and
POI Delete Decision Framework v1.0 (closure tiers E1–E4, threshold 70 from >= 2 tiers, liveness block, D5/D6).
The confidence score is advisory: it informs QC and never approves a record by itself.
"""
from datetime import date, timedelta

RULES_VERSION = "review-20261027-v1"
DECISIONS = ("new", "update", "delete", "no_change", "field_review", "hold")
DELETE_REASONS = {
    "permanently_closed": "Permanently closed",
    "non_existent": "Non-existent / never at this location",
    "duplicate": "Duplicate of another HERE POI",
    "relocated": "Relocated with no valid retained representation",
}
EVIDENCE_TYPES = {
    # type: (label, workbook weight, scoring type)
    "street_level_imagery": ("Street-level imagery (SLI)", 0.20, "street_level_imagery"),
    "field_observation": ("Field observation / geotagged photo", 0.20, "street_level_imagery"),
    "pos_confirmation": ("POS terminal / transaction confirmation", 0.20, "pos_confirmation"),
    "official_website": ("Official website / store locator", 0.20, "official_website"),
    "official_social": ("Official social media", 0.20, "official_social"),
    "competitor_map_link": ("Competitor map link / third-party site (reference only)", 0.15, "competitor_map_link"),
    "other_image": ("Other images", 0.05, "other_image"),
}
WEIGHTS = {"street_level_imagery": 0.20, "pos_confirmation": 0.20, "official_website": 0.20, "official_social": 0.20,
           "competitor_map_link": 0.15, "other_image": 0.05}
SUPPORTS = ("existence", "attribute", "closure", "liveness")
IMAGERY_OR_POS = {"street_level_imagery", "field_observation", "pos_confirmation"}
WEAK_FOR_NAME = {"competitor_map_link", "other_image"}
CLOSURE_TIERS = {"official_website": ("E2", 60), "official_social": ("E3", 35), "competitor_map_link": ("E4", 10)}
TIER_RANK = {"E1": 1, "E2": 2, "E3": 3, "E4": 4, "other": 5}
CLOSURE_THRESHOLD = 70
E1_IMAGERY_MAX_AGE = timedelta(days=365)
# Draft annotation says "any two of E2/E3/E4"; the specification text requires >= 70 AND >= 2 tiers.
# Kept strict until HERE confirms (see clarifications).
ANY_TWO_TIERS_DELETES = False

ATTRIBUTES = {
    "name": "Business name", "transliteration": "Transliteration", "category_code": "HERE category",
    "poi_status": "POI status", "latitude": "Display latitude", "longitude": "Display longitude",
    "routing_latitude": "Routing latitude", "routing_longitude": "Routing longitude",
    "house_number": "House number", "street_name": "Street name", "address": "Full address", "unit": "Unit / stall",
    "rt": "RT", "rw": "RW", "admin5": "Admin 5", "admin4": "Admin 4", "admin3": "Admin 3", "admin2": "Admin 2",
    "admin1": "Admin 1", "postal_code": "Postal code", "phone": "Phone", "mobile": "Mobile", "tollfree": "Toll-free",
    "email": "Email", "website": "Website", "opening_hours": "Opening hours", "chain_name": "Chain name",
}
ATTRIBUTE_STATUS = ("confirmed", "corrected", "conflict", "unavailable")


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def confidence(evidence):
    """Workbook Part 3: best rubric score per type × weight, summed, × 10. Returns raw and rounded score."""
    best = {}
    for item in evidence:
        scoring = EVIDENCE_TYPES.get(item.get("type"), (None, 0, None))[2]
        if scoring:
            try:
                score = min(1.0, max(0.0, float(item.get("score", 0))))
            except (TypeError, ValueError):
                score = 0.0
            best[scoring] = max(best.get(scoring, 0.0), score)
    raw = sum(WEIGHTS[t] * s for t, s in best.items()) * 10
    rounded = round(raw)
    band = ("Excellent" if rounded >= 9 else "Strong" if raw > 5 else "Developing" if raw > 4
            else "Needs strengthening" if rounded >= 3 else "Requires resubmission")
    return {"raw": round(raw, 2), "score": rounded, "band": band, "by_type": best}


def closure_assessment(evidence, today=None):
    """Delete Framework §4: E1 override, or weighted E2–E4 >= 70 from >= 2 independent tiers; liveness blocks."""
    today = today or date.today()
    tiers, liveness, notes = {}, [], []
    seen_origins = set()
    for item in evidence:
        kind, supports = item.get("type"), item.get("supports")
        origin = (item.get("origin") or item.get("url") or "").strip().lower()
        if supports == "closure" and origin and origin in seen_origins:
            notes.append("Duplicate closure evidence from the same origin counted once.")
            continue
        if origin:
            seen_origins.add(origin)
        observed = _parse_date(item.get("observed_on"))
        if kind in ("street_level_imagery", "field_observation"):
            tier = "E1" if observed and today - observed <= E1_IMAGERY_MAX_AGE else None
            if supports == "closure" and not tier:
                notes.append("Imagery closure evidence needs an observation date within the last 12 months to count as E1.")
        elif kind == "pos_confirmation":
            inactive = float(item.get("pos_inactive_months") or 0)
            prior = float(item.get("pos_prior_active_months") or 0)
            tier = "E1" if supports != "closure" or (inactive >= 6 and prior >= 3) else None
            if supports == "closure" and not tier:
                notes.append("POS closure needs >= 6 months inactivity after >= 3 months of prior activity.")
        else:
            tier = CLOSURE_TIERS.get(kind, ("other", 0))[0]
        if supports == "closure" and tier:
            tiers[tier] = max(tiers.get(tier, 0), CLOSURE_TIERS.get(kind, (tier, 0))[1])
        elif supports == "liveness":
            liveness.append(tier or "other")
    e1 = "E1" in tiers
    weighted = sum(v for t, v in tiers.items() if t != "E1")
    weighted_tiers = [t for t in tiers if t in ("E2", "E3", "E4")]
    weighted_ok = (weighted >= CLOSURE_THRESHOLD or ANY_TWO_TIERS_DELETES) and len(weighted_tiers) >= 2
    best_closure = min((TIER_RANK[t] for t in tiers), default=None)
    blocked = best_closure is not None and any(TIER_RANK[t] <= best_closure for t in liveness)
    rule = None if blocked else "D5" if e1 else "D6" if weighted_ok else None
    return {"tiers": sorted(tiers), "weighted_score": weighted, "e1_override": e1, "weighted_ok": weighted_ok,
            "liveness_block": sorted(set(liveness)) if blocked else [], "rule": rule or "D7", "deletable": rule is not None,
            "notes": sorted(set(notes))}


def validate_decision(payload, context, today=None):
    """Check a review decision has the inputs and evidence its action requires.

    `context` carries: has_here (bool), here_place_ids (set of baseline IDs), aoi_contains(lon, lat) -> bool,
    category_codes (set). Returns {"errors": [...], "warnings": [...], "confidence": ..., "closure": ...}.
    """
    today = today or date.today()
    errors, warnings = [], []
    decision = payload.get("decision")
    attributes = payload.get("attributes") or {}
    evidence = payload.get("evidence") or []
    if decision not in DECISIONS:
        return {"errors": ["Choose NEW, UPDATE, DELETE, NO CHANGE, FIELD REVIEW or HOLD."], "warnings": []}

    for i, item in enumerate(evidence, 1):
        if item.get("type") not in EVIDENCE_TYPES:
            errors.append(f"Evidence {i}: choose an evidence type.")
        if item.get("supports") not in SUPPORTS:
            errors.append(f"Evidence {i}: say what it supports (existence, attribute, closure or liveness).")
        if not (item.get("url") or item.get("description") or item.get("source_observation_id")):
            errors.append(f"Evidence {i}: add a URL, a source observation or a description.")
        if item.get("absence_only"):
            errors.append(f"Evidence {i}: absence from a website, map or directory is not evidence.")
        observed = _parse_date(item.get("observed_on"))
        if item.get("observed_on") and not observed:
            errors.append(f"Evidence {i}: observed date must be YYYY-MM-DD.")
        elif observed and observed > today:
            errors.append(f"Evidence {i}: observed date is in the future.")
    for field, value in attributes.items():
        if field not in ATTRIBUTES:
            errors.append(f"Unknown attribute {field}.")
        elif (value or {}).get("status") not in ATTRIBUTE_STATUS:
            errors.append(f"{ATTRIBUTES[field]}: mark it confirmed, corrected, conflict or unavailable.")

    if decision in ("new", "update", "delete", "no_change"):
        vdate = _parse_date(payload.get("verification_date"))
        if not vdate:
            errors.append("Enter the verification date (YYYY-MM-DD).")
        elif vdate > today:
            errors.append("The verification date can't be in the future.")

    final = {f: (v or {}).get("final") for f, v in attributes.items()}
    existence_types = {e.get("type") for e in evidence if e.get("supports") == "existence"}

    if decision == "new":
        for field in ("name", "category_code", "latitude", "longitude"):
            if final.get(field) in (None, ""):
                errors.append(f"NEW needs a final {ATTRIBUTES[field].lower()}.")
        if final.get("category_code") and final["category_code"] not in context.get("category_codes", set()):
            errors.append("NEW needs a category from the supplied HERE category reference.")
        try:
            lat, lon = float(final.get("latitude")), float(final.get("longitude"))
            if not context["aoi_contains"](lon, lat):
                errors.append("The display point is outside the assigned AOI.")
        except (TypeError, ValueError):
            pass
        if len(existence_types) < 2 or not existence_types & IMAGERY_OR_POS:
            errors.append("NEW needs at least two independent evidence types supporting existence, one of them "
                          "street-level imagery, a field observation or POS confirmation.")
    elif decision == "update":
        if not context.get("has_here"):
            errors.append("UPDATE needs a matched HERE place ID. Use NEW or FALLOUT handling instead.")
        corrected = [f for f, v in attributes.items() if (v or {}).get("status") == "corrected"]
        if not corrected:
            errors.append("UPDATE needs at least one corrected attribute.")
        for field in corrected:
            if final.get(field) in (None, ""):
                errors.append(f"{ATTRIBUTES[field]}: enter the corrected value.")
            backing = [e for e in evidence if field in (e.get("fields") or [])]
            if not backing:
                errors.append(f"{ATTRIBUTES[field]}: link evidence that directly supports this change.")
            elif field == "name" and all(e.get("type") in WEAK_FOR_NAME for e in backing):
                errors.append("A name change needs current imagery or an official source, not only a competitor map link.")
    elif decision == "delete":
        if not context.get("has_here"):
            errors.append("DELETE needs a matched HERE place ID.")
        reason = payload.get("delete_reason")
        if reason not in DELETE_REASONS:
            errors.append("Choose a delete reason.")
        elif reason == "duplicate":
            other = (payload.get("duplicate_of") or "").strip()
            if not other or other not in context.get("here_place_ids", set()) or other == context.get("place_id"):
                errors.append("A duplicate delete needs the HERE place ID of the record that stays.")
            if not evidence:
                errors.append("A duplicate delete needs evidence that both records are the same business.")
        elif reason == "relocated":
            if not any(e.get("supports") in ("existence", "attribute") and e.get("type") in
                       ("official_website", "official_social", "field_observation", "street_level_imagery") for e in evidence):
                errors.append("A relocation delete needs official or field evidence of the move. Relocations inside "
                              "the AOI should be UPDATE (geometry), not DELETE.")
        else:
            closure = closure_assessment(evidence, today)
            if closure["liveness_block"]:
                errors.append("Active-business evidence of equal or higher tier blocks this deletion; route to review.")
            elif not closure["deletable"]:
                errors.append("Closure evidence is insufficient: need E1 (imagery <= 12 months or POS inactivity), or "
                              ">= 70 points from at least two of official website (60), social (35), competitor map (10).")
    elif decision == "no_change":
        if not existence_types:
            errors.append("NO CHANGE needs at least one item of evidence that the business exists as recorded.")
    elif decision == "field_review":
        if not (payload.get("field_issue") or "").strip():
            errors.append("Describe exactly what the field verifier must check.")
    elif decision == "hold":
        if not (payload.get("remarks") or "").strip():
            errors.append("Explain why the record is on hold.")

    if decision in ("new", "update") and any(e.get("type") == "competitor_map_link" for e in evidence):
        warnings.append("Competitor map links are internal corroboration only; they are never exported to HERE.")
    result = {"errors": errors, "warnings": warnings, "confidence": confidence(evidence), "rules_version": RULES_VERSION}
    if decision == "delete":
        result["closure"] = closure_assessment(evidence, today)
    return result
