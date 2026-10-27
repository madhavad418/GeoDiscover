from app.services.matching import (
    band_for, compare, link_observations, norm_name, norm_phones, observation_record, token_set_ratio, web_key, web_keys,
)

DATASET = "11111111-1111-1111-1111-111111111111"
BASE = (14.6000, 120.9700)  # Divisoria


def here(i, name, dlat=0.0, dlon=0.0, code="100-1000-0000", **raw):
    return {"id": i, "place_id": f"here-{i}", "name": name, "category_code": code, "category_name": "Restaurant",
            "latitude": BASE[0] + dlat, "longitude": BASE[1] + dlon, "address": raw.pop("address", ""), "raw": raw}


_seq = iter(range(1, 10_000))


def obs(batch, name, dlat=0.0, dlon=0.0, code="100-1000-0000", source_type="official_website", **kw):
    i = next(_seq)
    return {"id": i, "batch_id": batch, "source_type": source_type, "source_name": batch, "source_record_id": f"r{i}",
            "name": name, "alt_names": kw.pop("alt_names", []), "category_code": code, "category_name": None,
            "latitude": BASE[0] + dlat, "longitude": BASE[1] + dlon, **kw}


def run(here_rows, observations, chains=()):
    return compare(here_rows, observations, "PHL", DATASET, chains)


def outcomes(result):
    return sorted((r["outcome"], r["here_place_id"]) for r in result["results"])


# ---------- normalization ----------
def test_name_normalization_handles_legal_suffixes_accents_and_thai():
    assert norm_name("PT. Café Sejahtera Tbk") == "cafe sejahtera"
    assert norm_name("Mang-Inasal (Branch)") == "mang inasal"
    thai = norm_name("วัตสัน สาขา เซ็นเตอร์ วัน")
    assert "วัตสัน" in thai and "สาขา" not in thai and "ั" in thai  # Thai vowel marks are kept
    assert token_set_ratio(norm_name("Mang Inasal"), norm_name("Mang Inasal Divisoria Mall")) == 1.0
    assert token_set_ratio(norm_name("Jollibee"), norm_name("Chowking")) < 0.6
    # Sharing only a generic word is not identity, even when one name "contains" the other.
    assert token_set_ratio(norm_name("Shop"), norm_name("Laundry Baru Shop")) < 0.85
    assert token_set_ratio(norm_name("Toko"), norm_name("Toko Sejahtera")) < 0.85
    assert token_set_ratio(norm_name("Sejahtera"), norm_name("Toko Sejahtera")) == 1.0


def test_phone_and_web_keys():
    assert norm_phones(["+63 2 8242 1109", "028242-1109"], "PHL") == {"282421109"}
    assert norm_phones(["6.39283E+11"], "PHL") == set()  # Excel-mangled numbers are ignored, not guessed
    assert web_key("https://www.Jollibee.com.ph/stores/divisoria?x=1") == "jollibee.com.ph"
    assert web_key("facebook.com/MangInasalDivisoria") == "facebook.com/manginasaldivisoria"
    assert web_key("not a url") is None
    assert web_keys("http://www.klikbca.com,https://www.bca.co.id,https://www.bca.co.id/id/individu") == {"klikbca.com", "bca.co.id"}


def test_bands():
    assert [band_for(d) for d in (10, 50, 51, 250, 900, 1500)] == ["B0", "B0", "B1", "B1", "B2", "B3"]


# ---------- linking ----------
def test_one_outlet_across_sources_becomes_one_master():
    a = obs("site", "Mang Inasal Divisoria", phones=["+63 2 8242 1109"])
    b = obs("directory", "Mang Inasal", dlat=0.0001, phones=["(02) 8242-1109"], source_type="licensed_directory")
    c = obs("vendor", "MANG INASAL - DIVISORIA", dlat=-0.0001, source_type="licensed_vendor")
    clusters = link_observations([observation_record(o, "PHL") for o in (a, b, c)])
    assert len(clusters) == 1 and len(clusters[0][0]) == 3


def test_tenants_sharing_coordinates_stay_separate():
    shops = [obs("site", "Shoe MGK"), obs("directory", "Toy Kingdom", source_type="licensed_directory")]
    assert len(link_observations([observation_record(o, "PHL") for o in shops])) == 2


def test_same_source_never_merges_and_conflicting_branches_stay_apart():
    same_source = [obs("site", "Watsons"), obs("site", "Watsons", dlat=0.0001)]
    assert len(link_observations([observation_record(o, "PHL") for o in same_source])) == 2
    branches = [obs("a", "Watsons", phones=["0281111111"], house_number="12"),
                obs("b", "Watsons", dlat=0.0002, phones=["0282222222"], house_number="40", source_type="licensed_directory")]
    assert len(link_observations([observation_record(o, "PHL") for o in branches])) == 2


# ---------- classification ----------
def test_identical_record_is_no_change_and_spelling_variation_is_not_new():
    result = run([here(1, "Mang Inasal")], [obs("site", "Mang-Inasal")])
    assert outcomes(result) == [("no_change", "here-1")]
    r = result["results"][0]
    assert r["decision_rule"] == "D1" and r["band"] == "B0"


def test_supported_difference_is_potential_update_with_explanation():
    result = run([here(1, "Mang Inasal", phone_numbers="0281111111")],
                 [obs("site", "Mang Inasal", phones=["0281111111"], website="https://manginasal.com", opening_hours="MON:08:00-20:00")])
    r = result["results"][0]
    assert r["outcome"] == "potential_update"
    fields = {d["field"]: d["kind"] for d in r["explanation"]["changed_fields"]}
    assert fields == {"website": "missing_in_here", "opening_hours": "missing_in_here"}
    assert r["explanation"]["match"]["M3"] is True


def test_location_deviation_with_identity_is_geometry_update_not_new():
    # ~180 m away (band B1) but the same phone number: D2, update geometry, never delete or add.
    result = run([here(1, "Minimarket Sejahtera", phone_numbers="0281234567")],
                 [obs("site", "Minimarket Sejahtera", dlat=0.0016, phones=["0281234567"])])
    r = result["results"][0]
    assert r["outcome"] == "potential_update" and r["band"] == "B1" and r["decision_rule"] == "D2"
    assert "location" in {d["field"] for d in r["explanation"]["changed_fields"]}


def test_same_name_in_b1_without_identity_signal_is_fallout():
    result = run([here(1, "Kopi Kenangan")], [obs("site", "Kopi Kenangan", dlat=0.0016)])
    assert outcomes(result) == [("fallout_review", None)]


def test_external_only_is_potential_new_and_here_only_is_verification_required():
    result = run([here(1, "Old Bakery", dlat=0.004)], [obs("site", "Brand New Laundry")])
    assert outcomes(result) == [("potential_new", None), ("verification_required", "here-1")]
    vr = next(r for r in result["results"] if r["outcome"] == "verification_required")
    assert vr["decision_rule"] == "D7"  # absence is never a deletion


def test_reported_closure_is_potential_delete_but_status_conflict_is_fallout():
    closed = run([here(1, "Toko Lama")], [obs("site", "Toko Lama", business_status="permanently_closed")])
    assert outcomes(closed) == [("potential_delete", "here-1")]
    conflict = run([here(1, "Toko Lama")], [
        obs("site", "Toko Lama", business_status="permanently_closed"),
        obs("field", "Toko Lama", dlat=0.00005, business_status="open", source_type="field_observation"),
    ])
    # The reviewer still sees which HERE POI the conflicting sources point at.
    assert outcomes(conflict) == [("fallout_review", "here-1")]


def test_multiple_possible_matches_and_contention_are_fallout():
    dupes = run([here(1, "Jollibee"), here(2, "Jollibee", dlat=0.0001)], [obs("site", "Jollibee")])
    assert outcomes(dupes) == [("fallout_review", None)]  # chain-like duplicate names need unit signals
    contended = run([here(1, "Kedai Kopi Asli")], [
        obs("a", "Kedai Kopi Asli", dlat=0.0001), obs("a", "Kedai Kopi Asli", dlat=-0.0001)])
    assert [r["outcome"] for r in contended["results"]] == ["fallout_review", "fallout_review"]


def test_chain_branch_needs_unit_level_signal():
    no_signal = run([here(1, "Watsons", chainid="7019")], [obs("site", "Watsons")])
    assert outcomes(no_signal) == [("fallout_review", None)]
    with_phone = run([here(1, "Watsons", chainid="7019", phone_numbers="0287654321")],
                     [obs("site", "Watsons", phones=["0287654321"])])
    assert outcomes(with_phone) == [("no_change", "here-1")]


def test_source_reference_to_here_id_confirms_identity():
    result = run([here(1, "Toko Baru", dlat=0.005)], [obs("site", "Toko Baru Jaya", here_place_id="here-1")])
    assert result["results"][0]["here_place_id"] == "here-1"


def test_rerun_with_same_inputs_is_identical():
    rows = [here(1, "Mang Inasal"), here(2, "Old Bakery", dlat=0.004)]
    observations = [obs("site", "Mang Inasal", website="manginasal.com"), obs("site", "New Laundry", dlat=-0.003)]
    first, second = run(rows, observations), run(rows, observations)
    key = lambda res: sorted((r["result_key"], r["content_hash"], r["outcome"]) for r in res["results"])  # noqa: E731
    assert key(first) == key(second)
    assert first["stats"]["outcomes"]["potential_update"] == 1
