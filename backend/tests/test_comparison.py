from app.services.comparison import build_demo_proposals, classify_candidate, normalize_place


def test_matching_uses_identifier_then_name_category_and_distance():
    base = normalize_place({
        "placeid": "here-1", "name1": "Corner Café", "primarycategory": "100",
        "primarycategorynm": "Cafe", "upaddress": "1 Main St",
        "displaylatitude": 13.75, "displaylongitude": 100.5,
    })
    exact_id = classify_candidate([base], {**base, "name": "Corner Cafe Updated"})
    assert exact_id["action"] == "update"
    assert exact_id["matched_by"] == "place_id"
    assert exact_id["changed_fields"] == ["name"]

    supplier_row = {
        "poi_name": "Corner Café", "category": "100", "address": "1 Main St",
        "latitude": 13.75001, "longitude": 100.5,
    }
    name_match = classify_candidate([base], supplier_row)
    assert name_match["action"] == "unchanged"
    assert name_match["matched_by"] == "name_category_distance"

    contact_update = classify_candidate([base], {**supplier_row, "phone_numbers": "+66123456789"})
    assert contact_update["action"] == "update"
    assert contact_update["changed_fields"] == ["phone"]


def test_new_and_explicit_delete_are_not_inferred_from_missing_provider_rows():
    base = normalize_place({
        "placeid": "here-1", "name1": "Corner Cafe", "primarycategory": "100",
        "displaylatitude": 13.75, "displaylongitude": 100.5,
    })
    new = classify_candidate([base], {"name": "Different Place", "latitude": 13.75, "longitude": 100.5})
    assert new["action"] == "new"
    assert classify_candidate([base], {**base, "operation": "DELETE"})["action"] == "delete"

    unlinked_delete = classify_candidate([base], {"name": "Different Place", "operation": "delete"})
    assert unlinked_delete["action"] == "unmatched"


def test_demo_proposals_include_actions_for_each_simulated_source():
    baseline = [
        {"placeid": f"here-{i}", "name1": f"Place {i}", "primarycategory": "100",
         "primarycategorynm": "Restaurant", "displaylatitude": 13.75 + i * 0.001,
         "displaylongitude": 100.5 + i * 0.001}
        for i in range(4)
    ]
    demos = build_demo_proposals(baseline, "Demo AOI")
    assert set(demos) == {"google", "apple", "grab"}
    for proposals in demos.values():
        assert {proposal["action"] for proposal in proposals} == {"new", "update", "delete"}
        assert all(proposal["review_status"] == "pending" for proposal in proposals)
