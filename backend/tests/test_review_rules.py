from datetime import date, timedelta

from app.services.review_rules import closure_assessment, confidence, validate_decision

TODAY = date(2026, 10, 27)
RECENT = (TODAY - timedelta(days=60)).isoformat()
OLD = (TODAY - timedelta(days=500)).isoformat()
CTX = {"has_here": True, "place_id": "here-1", "here_place_ids": {"here-1", "here-2"},
       "aoi_contains": lambda lon, lat: True, "category_codes": {"100-1000-0000"}}


def ev(kind, supports="existence", **kw):
    return {"type": kind, "supports": supports, "url": kw.pop("url", f"https://example.com/{kind}"), **kw}


def check(payload, ctx=CTX):
    return validate_decision({"verification_date": RECENT, **payload}, ctx, TODAY)


def test_workbook_worked_example_uses_correct_arithmetic():
    # Workbook p.6-7 lists weighted values 0.20+0.20+0.14+0.10+0.15+0.00 but states "0.89 x 10 ≈ 9".
    # They sum to 0.79, so the formula gives 7.9 ≈ 8 (Strong). Raised as a clarification with HERE.
    evidence = [ev("street_level_imagery", score=1.0), ev("pos_confirmation", score=1.0), ev("official_website", score=0.7),
                ev("official_social", score=0.5), ev("competitor_map_link", score=1.0)]
    result = confidence(evidence)
    assert result["raw"] == 7.9 and result["score"] == 8 and result["band"] == "Strong"


def test_new_needs_two_independent_types_including_imagery_or_pos():
    attrs = {f: {"final": v, "status": "corrected"} for f, v in
             {"name": "Kedai Baru", "category_code": "100-1000-0000", "latitude": -6.18, "longitude": 106.81}.items()}
    weak = check({"decision": "new", "attributes": attrs, "evidence": [ev("official_website"), ev("official_social")]})
    assert any("two independent evidence types" in e for e in weak["errors"])
    ok = check({"decision": "new", "attributes": attrs, "evidence": [ev("field_observation"), ev("official_website")]})
    assert ok["errors"] == []


def test_new_outside_aoi_or_unknown_category_is_rejected():
    attrs = {"name": {"final": "X", "status": "corrected"}, "category_code": {"final": "999-9999-9999", "status": "corrected"},
             "latitude": {"final": 1, "status": "corrected"}, "longitude": {"final": 1, "status": "corrected"}}
    result = check({"decision": "new", "attributes": attrs, "evidence": [ev("field_observation"), ev("pos_confirmation")]},
                   {**CTX, "aoi_contains": lambda lon, lat: False})
    assert any("outside the assigned AOI" in e for e in result["errors"])
    assert any("category reference" in e for e in result["errors"])


def test_update_requires_evidence_for_each_corrected_field_and_strong_source_for_names():
    attrs = {"name": {"final": "New Name", "status": "corrected"}, "phone": {"final": "0281234567", "status": "corrected"}}
    unbacked = check({"decision": "update", "attributes": attrs, "evidence": [ev("official_website", "attribute", fields=["phone"])]})
    assert any("Business name: link evidence" in e for e in unbacked["errors"])
    weak_name = check({"decision": "update", "attributes": attrs, "evidence": [
        ev("competitor_map_link", "attribute", fields=["name"]), ev("official_website", "attribute", fields=["phone"])]})
    assert any("name change needs" in e for e in weak_name["errors"])
    good = check({"decision": "update", "attributes": attrs, "evidence": [
        ev("street_level_imagery", "attribute", fields=["name"]), ev("official_website", "attribute", fields=["phone"])]})
    assert good["errors"] == []


def test_delete_framework_thresholds():
    # E2 alone (60) is not enough; E2 + E3 (95) is; E3 + E4 (45) is not; fresh imagery is an E1 override.
    assert not closure_assessment([ev("official_website", "closure")], TODAY)["deletable"]
    assert closure_assessment([ev("official_website", "closure"), ev("official_social", "closure")], TODAY)["rule"] == "D6"
    assert not closure_assessment([ev("official_social", "closure"), ev("competitor_map_link", "closure")], TODAY)["deletable"]
    assert closure_assessment([ev("street_level_imagery", "closure", observed_on=RECENT)], TODAY)["rule"] == "D5"
    assert not closure_assessment([ev("street_level_imagery", "closure", observed_on=OLD)], TODAY)["deletable"]
    pos = ev("pos_confirmation", "closure", pos_inactive_months=8, pos_prior_active_months=24)
    assert closure_assessment([pos], TODAY)["rule"] == "D5"


def test_competitor_map_alone_never_deletes_and_same_origin_counts_once():
    assert not closure_assessment([ev("competitor_map_link", "closure")], TODAY)["deletable"]
    same = [ev("official_website", "closure", url="https://shop.example/closed"),
            ev("official_social", "closure", url="https://shop.example/closed")]
    assert not closure_assessment(same, TODAY)["deletable"]


def test_liveness_blocks_deletion():
    evidence = [ev("official_website", "closure"), ev("official_social", "closure"), ev("official_website", "liveness", url="https://shop.example/menu")]
    result = check({"decision": "delete", "delete_reason": "permanently_closed", "evidence": evidence})
    assert any("blocks this deletion" in e for e in result["errors"])


def test_absence_is_not_evidence_and_duplicates_need_the_surviving_id():
    absence = check({"decision": "delete", "delete_reason": "permanently_closed",
                     "evidence": [ev("official_website", "closure", absence_only=True)]})
    assert any("absence" in e for e in absence["errors"])
    dup = check({"decision": "delete", "delete_reason": "duplicate", "duplicate_of": "here-1", "evidence": [ev("field_observation")]})
    assert any("record that stays" in e for e in dup["errors"])
    ok = check({"decision": "delete", "delete_reason": "duplicate", "duplicate_of": "here-2", "evidence": [ev("field_observation")]})
    assert ok["errors"] == []


def test_dates_field_review_and_hold():
    future = validate_decision({"decision": "no_change", "verification_date": (TODAY + timedelta(days=1)).isoformat(),
                                "evidence": [ev("official_website")]}, CTX, TODAY)
    assert any("future" in e for e in future["errors"])
    assert check({"decision": "field_review"})["errors"]
    assert check({"decision": "field_review", "field_issue": "Confirm stall number inside the market"})["errors"] == []
    assert check({"decision": "hold"})["errors"]
