"""Multi-source POI linking and HERE baseline matching.

Implements the POI Spatial Validation & Delete Decision Framework v1.0 identity model:
  M1 name similarity >= 0.85 (token-set, after removing legal suffixes / chain descriptors)
  M2 category agreement at level 2   M3 exact phone   M4 address overlap   M5 website / social handle
  Identity is confirmed by M1 plus one of M3/M4/M5. Chain brands always need a unit-level signal.
  Bands: B0 0-50 m, B1 50-250 m, B2 250 m-1 km, B3 beyond (identity-led relocation search only).

Outcomes follow the consolidated requirements §3. Absence never produces POTENTIAL DELETE; only a
source-reported closure does, and the reviewer must still supply closure evidence (D5/D6).
Pure functions only: no database access, so every rule is unit-testable.
"""
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from .names import variants

RULES_VERSION = "match-20261027-v3"
NAME_THRESHOLD = 0.85        # M1
PLAUSIBLE_NAME = 0.60        # candidate worth a human look
BANDS = (("B0", 50.0), ("B1", 250.0), ("B2", 1000.0))
LOCATION_CHANGE_M = 30.0     # display point differs enough to propose a geometry update
LINK_NAME_DISTANCE_M = 50.0  # multi-source linking on name + location
LINK_STRONG_DISTANCE_M = 150.0  # multi-source linking on phone / branch URL
CELL_DEG = 0.0025            # ~275 m grid cell, so a 3x3 neighbourhood covers 250 m

OUTCOMES = {
    "no_change": "MATCHED / NO CHANGE",
    "potential_update": "POTENTIAL UPDATE",
    "potential_new": "POTENTIAL NEW",
    "verification_required": "VERIFICATION REQUIRED",
    "potential_delete": "POTENTIAL DELETE",
    "fallout_review": "FALLOUT REVIEW",
}
PRIORITY = {"fallout_review": 1, "potential_delete": 2, "potential_update": 2, "potential_new": 3,
            "verification_required": 4, "no_change": 5}
# Higher-authority sources win when building the master record.
SOURCE_PRIORITY = ["field_observation", "official_website", "store_locator", "official_social",
                   "licensed_vendor", "licensed_directory", "other_permitted"]
CLOSED = {"permanently_closed", "closed", "not_found", "non_existent"}
OPEN = {"open", "operational", "active", "existing"}
COUNTRY_CALLING = {"PHL": "63", "IDN": "62", "THA": "66"}

LEGAL_TOKENS = {
    "pt", "cv", "tbk", "ud", "ltd", "limited", "co", "company", "inc", "incorporated", "corp", "corporation",
    "llc", "plc", "bhd", "sdn", "pte", "opc", "the", "and",
    # chain / outlet descriptors (English, Indonesian, Filipino, Thai)
    "branch", "outlet", "store", "cabang", "gerai", "sangay", "สาขา", "บริษัท", "จำกัด", "มหาชน",
}
# Generic business words: sharing only these never makes two names "the same" (EN / ID / TL / TH).
GENERIC_TOKENS = {
    "shop", "store", "mart", "market", "restaurant", "resto", "cafe", "coffee", "bakery", "salon", "spa", "clinic",
    "pharmacy", "bank", "atm", "hotel", "laundry", "tailor", "school", "office", "center", "centre", "new", "test",
    "toko", "warung", "kedai", "rumah", "makan", "apotek", "bengkel", "kantor", "pasar", "kios", "kopi",
    "tindahan", "kainan", "karinderya", "botika", "ร้าน", "ตลาด", "คลินิก", "ธนาคาร", "โรงแรม",
}
SOCIAL_HOSTS = {"facebook.com", "fb.com", "instagram.com", "tiktok.com", "twitter.com", "x.com", "line.me",
                "linktr.ee", "youtube.com", "shopee.co.id", "shopee.ph", "shopee.co.th", "tokopedia.com", "lazada.com"}


# ---------- Normalization ----------
def _tokens(text):
    """Split on anything that isn't a letter, mark or digit (keeps Thai vowel marks inside words)."""
    out, current = [], []
    for ch in text:
        if unicodedata.category(ch)[0] in "LMN":
            current.append(ch)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def fold(text):
    """NFKC, casefold, and drop accents on Latin letters only (Thai/other marks are meaningful)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    out, base_latin = [], False
    for ch in unicodedata.normalize("NFKD", text):
        if unicodedata.combining(ch):
            if base_latin:
                continue
        else:
            base_latin = ch.isascii() or "LATIN" in unicodedata.name(ch, "")
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def norm_name(name):
    return " ".join(t for t in _tokens(fold(name)) if t not in LEGAL_TOKENS)


def _ratio(a, b, cutoff=0.0):
    """SequenceMatcher ratio; returns 0 early when even the upper bound can't reach `cutoff`."""
    if not a or not b:
        return 0.0
    if cutoff:
        la, lb = len(a), len(b)
        if 2.0 * min(la, lb) / (la + lb) < cutoff:
            return 0.0
        matcher = SequenceMatcher(None, a, b, autojunk=False)
        if matcher.quick_ratio() < cutoff:
            return 0.0
        return matcher.ratio()
    return SequenceMatcher(None, a, b, autojunk=False).ratio()


def token_set_ratio(a, b, cutoff=0.0):
    """Token-set similarity in [0, 1] (as fuzzywuzzy's token_set_ratio, without the dependency).

    With `cutoff`, scores that cannot reach it may be reported as 0 (used to skip hopeless pairs fast).
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    common = ta & tb
    inter = " ".join(sorted(common))
    if not inter or common <= GENERIC_TOKENS:
        # Sharing only generic words ("shop", "toko", "bank") is not identity: compare the whole names.
        return _ratio(" ".join(sorted(ta)), " ".join(sorted(tb)), cutoff)
    if common == ta or common == tb:
        return 1.0  # one name is contained in the other
    sa = f"{inter} {' '.join(sorted(ta - tb))}"
    sb = f"{inter} {' '.join(sorted(tb - ta))}"
    return max(_ratio(inter, sa, cutoff), _ratio(inter, sb, cutoff), _ratio(sa, sb, cutoff))


GRAM_PREFILTER = 0.35  # bigram Dice below this can't plausibly reach PLAUSIBLE_NAME; skip the costly ratio


def bigrams(text):
    text = text.replace(" ", "")
    return frozenset(text[i:i + 2] for i in range(len(text) - 1)) or frozenset([text])


def name_grams(names):
    return [bigrams(n) for n in names]


def gram_overlap(grams_a, grams_b):
    """Best overlap coefficient |a∩b| / min(|a|,|b|) between names' bigram sets.

    Containment-aware on purpose: token-set similarity scores "7-Eleven" vs "7-Eleven Phaya Thai" as 1.0,
    so the prefilter must not reject a short name contained in a long one.
    """
    best = 0.0
    for a in grams_a:
        for b in grams_b:
            if a and b:
                best = max(best, len(a & b) / min(len(a), len(b)))
    return best


def quick_link_possible(a, b):
    """Cheap test that a pair could produce any matching signal; avoids building signals for hopeless pairs."""
    return (gram_overlap(a["grams"], b["grams"]) >= GRAM_PREFILTER or bool(a["phones"] & b["phones"])
            or bool(a["webs"] & b["webs"]))


def best_name_similarity(names_a, names_b, cutoff=0.0):
    best = 0.0
    for a in names_a:
        for b in names_b:
            if a and b:
                best = max(best, token_set_ratio(a, b, max(cutoff, best)))
                if best == 1.0:
                    return best
    return best


def norm_phones(values, country):
    """National significant numbers (last 9 digits) from comma/semicolon lists; drops Excel-mangled 6.39E+11."""
    code = COUNTRY_CALLING.get(country, "")
    out = set()
    for value in values or []:
        for part in re.split(r"[,;/|]", str(value)):
            if re.search(r"[eE]\+", part):
                continue
            digits = re.sub(r"\D", "", part)
            if code and digits.startswith(code) and len(digits) > 9:
                digits = digits[len(code):]
            digits = digits.lstrip("0")
            if len(digits) >= 7:
                out.add(digits[-9:])
    return out


def web_key(url):
    """Domain for owned websites; domain + handle for social/marketplace pages; None if unusable."""
    if not url:
        return None
    text = str(url).strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", text, re.I):
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    if host in SOCIAL_HOSTS or any(host.endswith("." + s) for s in SOCIAL_HOSTS):
        handle = next((p for p in parts.path.split("/") if p), "")
        return f"{host}/{handle.lower()}" if handle else None
    return host


def web_keys(*values):
    """Website/social keys from fields that may hold several comma-separated URLs (HERE webaddress does)."""
    keys = set()
    for value in values:
        for part in re.split(r"[,;\s|]+(?=(?:https?://|www\.|[a-z0-9-]+\.[a-z]))", str(value or "").strip(), flags=re.I):
            key = web_key(part.strip(" ,;"))
            if key:
                keys.add(key)
    return keys


def norm_house(value):
    return re.sub(r"[^0-9a-z/]", "", fold(value)) if value else ""


def category_level2(code):
    return code[:8] if code and len(code) >= 8 else None


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(a)))


def band_for(distance):
    for name, limit in BANDS:
        if distance <= limit:
            return name
    return "B3"


def sha(*parts):
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()


# ---------- Record shapes ----------
def name_keys(names, translations=None):
    """Normalized names plus transliterated / translated forms of non-Latin names (Thai, CJK, Arabic...)."""
    return sorted({norm_name(v) for n in names if n for v in variants(str(n), translations)} - {""})


def here_record(row, country, translations=None):
    """Normalize a HERE baseline row (customer_pois + raw columns) for matching."""
    raw = row.get("raw") or {}
    names = [row.get("name"), raw.get("name2")]
    return {
        "kind": "here", "id": row["id"], "place_id": str(row["place_id"]), "name": row.get("name") or "",
        "names": (here_names := name_keys(names, translations)), "grams": name_grams(here_names),
        "category_code": row.get("category_code"), "category_name": row.get("category_name"),
        "lat": float(row["latitude"]), "lon": float(row["longitude"]),
        "phones": norm_phones([raw.get("phone_numbers"), raw.get("mobile_numbers"), raw.get("tollfree_numbers")], country),
        "webs": (here_webs := web_keys(raw.get("webaddress"))), "web": min(here_webs) if here_webs else None,
        "house": norm_house(raw.get("hno")), "street": norm_name(raw.get("streetname")),
        "postal": (raw.get("postalcode") or "").strip(),
        "chain": str(raw.get("chainid") or "").strip() not in ("", "0"),
        "hours": (raw.get("opening_hours") or "").strip(),
        "address": row.get("address") or raw.get("upaddress") or "",
        "raw": raw,
    }


def observation_record(obs, country, translations=None):
    names = [obs.get("name"), *(obs.get("alt_names") or [])]
    return {
        "kind": "obs", "id": obs["id"], "batch_id": str(obs["batch_id"]), "source_type": obs["source_type"],
        "source_name": obs.get("source_name", ""), "source_record_id": str(obs["source_record_id"]),
        "name": obs.get("name") or "", "names": (obs_names := name_keys(names, translations)),
        "grams": name_grams(obs_names),
        "category_code": obs.get("category_code"), "category_name": obs.get("category_name"),
        "lat": float(obs["latitude"]), "lon": float(obs["longitude"]),
        "phones": norm_phones(obs.get("phones") or [], country),
        "web": web_key(obs.get("website")), "social": web_key(obs.get("social_url")),
        "webs": web_keys(obs.get("website"), obs.get("social_url")),
        "house": norm_house(obs.get("house_number")), "street": norm_name(obs.get("street_name")),
        "unit": norm_house(obs.get("unit")), "postal": (obs.get("postal_code") or "").strip(),
        "status": (obs.get("business_status") or "unknown").lower(),
        "hours": (obs.get("opening_hours") or "").strip(),
        "address": obs.get("address") or "", "here_place_id": (obs.get("here_place_id") or "").strip() or None,
        "website": obs.get("website"), "phones_raw": obs.get("phones") or [],
        "observed_on": obs.get("observed_on"), "source_url": obs.get("source_url"),
    }


class Grid:
    def __init__(self, records):
        self.cells = defaultdict(list)
        for r in records:
            self.cells[self.cell(r["lat"], r["lon"])].append(r)

    @staticmethod
    def cell(lat, lon):
        return (math.floor(lat / CELL_DEG), math.floor(lon / CELL_DEG))

    def near(self, lat, lon, radius_m):
        span = max(1, math.ceil(radius_m / 270.0))
        cy, cx = self.cell(lat, lon)
        for dy in range(-span, span + 1):
            for dx in range(-span, span + 1):
                yield from self.cells.get((cy + dy, cx + dx), ())


# ---------- Signals ----------
def signals(a, b, distance=None):
    """Identity signals between two normalized records (either may be HERE or an observation/master).

    Name similarities below PLAUSIBLE_NAME may be reported as 0; no rule distinguishes them.
    """
    if distance is None:
        distance = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
    webs_a, webs_b = a["webs"], b["webs"]
    if gram_overlap(a["grams"], b["grams"]) < GRAM_PREFILTER:
        sim = 0.0
    else:
        sim = best_name_similarity(a["names"], b["names"], PLAUSIBLE_NAME)
    l2a, l2b = category_level2(a.get("category_code")), category_level2(b.get("category_code"))
    m2 = None if not (l2a and l2b) else l2a == l2b
    m4 = bool(a.get("house") and b.get("house") and a["house"] == b["house"] and a.get("street") and b.get("street")
              and token_set_ratio(a["street"], b["street"]) >= NAME_THRESHOLD) or bool(a.get("unit") and a.get("unit") == b.get("unit"))
    return {
        "distance_m": round(distance, 1), "band": band_for(distance), "name_similarity": round(sim, 3),
        "M1": sim >= NAME_THRESHOLD, "M2": m2, "M3": bool(a["phones"] & b["phones"]),
        "M4": m4, "M5": bool(webs_a & webs_b),
        "phone_conflict": bool(a["phones"] and b["phones"] and not a["phones"] & b["phones"]),
        "house_conflict": bool(a.get("house") and b.get("house") and a["house"] != b["house"]),
    }


# ---------- Multi-source linking ----------
def link_observations(observations):
    """Cluster observations of the same physical business across sources.

    Never links two records from the same source batch (a source lists a business once), never links on
    a shared coordinate alone, and refuses links contradicted by both phone and house number.
    """
    grid = Grid(observations)
    candidates = []
    for a in observations:
        for b in grid.near(a["lat"], a["lon"], LINK_STRONG_DISTANCE_M):
            if b["id"] <= a["id"] or b["batch_id"] == a["batch_id"]:
                continue
            distance = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
            if distance > LINK_STRONG_DISTANCE_M:
                continue
            if not quick_link_possible(a, b):
                continue
            s = signals(a, b, distance)
            if s["phone_conflict"] and s["house_conflict"]:
                continue
            # A shared social handle is branch-level; a shared brand domain alone is not (chains share domains).
            strong = s["M3"] or any("/" in w for w in a["webs"] & b["webs"])
            by_name = s["M1"] and s["distance_m"] <= LINK_NAME_DISTANCE_M and s["M2"] is not False and not s["phone_conflict"]
            by_identity = strong and s["name_similarity"] >= PLAUSIBLE_NAME and s["distance_m"] <= LINK_STRONG_DISTANCE_M
            if by_name or by_identity:
                score = s["name_similarity"] + (0.5 if strong else 0) - s["distance_m"] / 1000
                reason = "name+location" if by_name else ("phone" if s["M3"] else "website/social")
                candidates.append((score, a["id"], b["id"], reason, s))
    parent = {o["id"]: o["id"] for o in observations}
    batches = {o["id"]: {o["batch_id"]} for o in observations}
    reasons = defaultdict(list)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for score, a, b, reason, s in sorted(candidates, key=lambda c: -c[0]):
        ra, rb = find(a), find(b)
        if ra == rb or batches[ra] & batches[rb]:
            continue
        parent[rb] = ra
        batches[ra] |= batches.pop(rb)
        reasons[ra] += reasons.pop(rb, []) + [{"a": a, "b": b, "reason": reason, "distance_m": s["distance_m"],
                                                "name_similarity": s["name_similarity"]}]
    groups = defaultdict(list)
    for o in observations:
        groups[find(o["id"])].append(o)
    return [(members, reasons.get(root, [])) for root, members in groups.items()]


def build_master(members, link_reasons, country):
    ranked = sorted(members, key=lambda o: (SOURCE_PRIORITY.index(o["source_type"]) if o["source_type"] in SOURCE_PRIORITY else 99, o["id"]))
    lead = ranked[0]
    key = sha(min(f"{o['batch_id']}:{o['source_record_id']}" for o in members))
    first = lambda field: next((o[field] for o in ranked if o.get(field)), None)  # noqa: E731
    statuses = {o["status"] for o in members} - {"unknown", ""}
    conflicts = []
    if statuses & CLOSED and statuses & OPEN:
        conflicts.append({"field": "status", "values": sorted(statuses)})
    names = [o["name"] for o in members]
    if len(members) > 1 and min(best_name_similarity([norm_name(names[0])], [norm_name(n)]) for n in names) < NAME_THRESHOLD:
        conflicts.append({"field": "name", "values": sorted(set(names))})
    codes = {o["category_code"] for o in members if o.get("category_code")}
    if len({c[:8] for c in codes}) > 1:
        conflicts.append({"field": "category", "values": sorted(codes)})
    iso2 = {"PHL": "PH", "IDN": "ID", "THA": "TH"}.get(country, country[:2])
    return {
        "kind": "master", "master_key": key, "jsan_id": f"JSAN-{iso2}-{key[:10].upper()}",
        "name": lead["name"], "names": (master_names := sorted({n for o in members for n in o["names"]})),
        "grams": name_grams(master_names),
        "category_code": first("category_code"), "category_name": first("category_name"),
        "lat": lead["lat"], "lon": lead["lon"],
        "phones": set().union(*(o["phones"] for o in members)),
        "web": first("web"), "social": first("social"), "webs": set().union(*(o["webs"] for o in members)),
        "house": first("house"), "street": first("street"),
        "unit": first("unit"), "postal": first("postal"), "hours": first("hours"), "address": first("address"),
        "status": next((o["status"] for o in ranked if o["status"] not in ("unknown", "")), "unknown"),
        "statuses": sorted(statuses), "here_refs": sorted({o["here_place_id"] for o in members if o.get("here_place_id")}),
        "observation_ids": sorted(o["id"] for o in members), "members": ranked, "link_reasons": link_reasons,
        "conflicts": conflicts,
    }


# ---------- HERE comparison ----------
def _is_chain(here, here_by_name, chain_names):
    if here["chain"] or any(n in chain_names for n in here["names"]):
        return True
    return any(len(here_by_name.get(n, ())) > 1 for n in here["names"])


def _candidate(master, here, here_by_name, chain_names, distance):
    s = signals(master, here, distance)
    ref = here["place_id"] in master["here_refs"]
    chain = _is_chain(here, here_by_name, chain_names)
    confirmed = ref or (s["M1"] and (s["M3"] or s["M4"] or s["M5"]))
    # B0 direct match on name + category for a non-chain POI, used when sources carry no unit-level signal.
    probable = not confirmed and s["M1"] and s["M2"] is not False and s["band"] == "B0" and not chain
    plausible = (s["name_similarity"] >= PLAUSIBLE_NAME and s["distance_m"] <= BANDS[1][1]) or s["M3"] or s["M5"] or (s["M1"] and s["band"] != "B3")
    level = "confirmed" if confirmed else "probable" if probable else "plausible" if plausible else None
    return {**s, "here_id": here["id"], "place_id": here["place_id"], "here_name": here["name"], "chain": chain,
            "reference_match": ref, "level": level}


def attribute_differences(master, here):
    diffs = []
    observed = lambda field: [{"value": o.get(field), "observation_id": o["id"], "source": o["source_name"] or o["source_type"]}  # noqa: E731
                              for o in master["members"] if o.get(field)]
    if master["names"] and not set(master["names"]) & set(here["names"]):
        diffs.append({"field": "name", "kind": "differs", "here": here["name"], "observed": observed("name")})
    if master.get("category_code") and here.get("category_code") and master["category_code"] != here["category_code"]:
        diffs.append({"field": "category", "kind": "differs", "here": here["category_code"], "observed": observed("category_code")})
    if master["phones"] and not master["phones"] & here["phones"]:
        diffs.append({"field": "phone", "kind": "missing_in_here" if not here["phones"] else "differs",
                      "here": here["raw"].get("phone_numbers"), "observed": observed("phones_raw")})
    master_sites = {w for w in master["webs"] if "/" not in w}
    here_sites = {w for w in here["webs"] if "/" not in w}
    if master_sites and not master_sites & here_sites:
        diffs.append({"field": "website", "kind": "missing_in_here" if not here_sites else "differs",
                      "here": here["raw"].get("webaddress"), "observed": observed("website")})
    if master.get("hours") and not here.get("hours"):
        diffs.append({"field": "opening_hours", "kind": "missing_in_here", "here": None, "observed": observed("hours")})
    address_differs = (master.get("house") and here.get("house") and master["house"] != here["house"]) or \
        (master.get("street") and here.get("street") and token_set_ratio(master["street"], here["street"]) < NAME_THRESHOLD) or \
        (master.get("postal") and here.get("postal") and master["postal"] != here["postal"])
    if address_differs:
        diffs.append({"field": "address", "kind": "differs", "here": here["address"], "observed": observed("address")})
    distance = haversine_m(master["lat"], master["lon"], here["lat"], here["lon"])
    if distance > LOCATION_CHANGE_M:
        diffs.append({"field": "location", "kind": "differs", "distance_m": round(distance, 1),
                      "here": [here["lat"], here["lon"]], "observed": [{"value": [o["lat"], o["lon"]], "observation_id": o["id"],
                                                                        "source": o["source_name"] or o["source_type"]} for o in master["members"]]})
    return diffs


def _here_summary(h):
    return {"id": h["id"], "place_id": h["place_id"], "name": h["name"], "category_code": h["category_code"],
            "category_name": h["category_name"], "lat": h["lat"], "lon": h["lon"], "address": h["address"]}


def _master_summary(m):
    return {"jsan_id": m["jsan_id"], "name": m["name"], "category_code": m.get("category_code"), "lat": m["lat"], "lon": m["lon"],
            "status": m["status"], "observation_ids": m["observation_ids"],
            "sources": sorted({o["source_name"] or o["source_type"] for o in m["members"]}), "conflicts": m["conflicts"],
            "link_reasons": m["link_reasons"]}


def compare(here_rows, observations, country, dataset_id, chain_names=(), translations=None):
    """Link observations into masters and classify everything against the HERE baseline.

    Returns {"masters": [...], "results": [...], "stats": {...}}. Each result has a stable result_key
    (identity) and content_hash (what was found), which make task generation idempotent.
    """
    here = [here_record(r, country, translations) for r in here_rows]
    obs = [observation_record(o, country, translations) for o in observations]
    chain_names = {norm_name(n) for n in chain_names}
    here_grid = Grid(here)
    here_by_name, here_by_phone, here_by_web = defaultdict(list), defaultdict(list), defaultdict(list)
    for h in here:
        for n in h["names"]:
            here_by_name[n].append(h)
        for p in h["phones"]:
            here_by_phone[p].append(h)
        for w in h["webs"]:
            here_by_web[w].append(h)
    here_index = {h["id"]: h for h in here}
    here_by_place = defaultdict(list)
    for h in here:
        here_by_place[h["place_id"]].append(h)

    masters = [build_master(members, reasons, country) for members, reasons in link_observations(obs)]
    proposals = []
    for m in masters:
        # Spatial candidates within B1 (250 m); beyond that only identity-led ones (same name, phone, website
        # or an explicit HERE reference), which covers B2 and B3 relocation without scanning the whole AOI.
        pool = {}
        for h in here_grid.near(m["lat"], m["lon"], BANDS[1][1]):
            d = haversine_m(m["lat"], m["lon"], h["lat"], h["lon"])
            if d <= BANDS[1][1]:
                pool[h["id"]] = (h, d)
        identity_led = [h for n in m["names"] for h in here_by_name.get(n, ())]
        identity_led += [h for p in m["phones"] for h in here_by_phone.get(p, ())]
        identity_led += [h for w in m["webs"] for h in here_by_web.get(w, ())]
        identity_led += [h for ref in m["here_refs"] for h in here_by_place.get(ref, ())]
        for h in identity_led:
            if h["id"] not in pool:
                pool[h["id"]] = (h, haversine_m(m["lat"], m["lon"], h["lat"], h["lon"]))
        cands = [c for c in (_candidate(m, h, here_by_name, chain_names, d) for h, d in pool.values()
                             if h["place_id"] in m["here_refs"] or quick_link_possible(m, h)) if c["level"]]
        cands.sort(key=lambda c: ({"confirmed": 0, "probable": 1, "plausible": 2}[c["level"]], -c["name_similarity"], c["distance_m"]))
        proposals.append((m, cands))

    # A HERE POI claimed by more than one master is contended: send all claimants to fallout.
    claims = defaultdict(list)
    for m, cands in proposals:
        strong = [c for c in cands if c["level"] in ("confirmed", "probable")]
        if len(strong) == 1:
            claims[strong[0]["here_id"]].append(m["master_key"])

    results, matched_here, referenced_here = [], set(), set()
    for m, cands in proposals:
        confirmed = [c for c in cands if c["level"] == "confirmed"]
        strong = confirmed or [c for c in cands if c["level"] == "probable"]
        reasons = []
        outcome, match = None, None
        if len(strong) > 1:
            outcome, reasons = "fallout_review", [f"{len(strong)} HERE POIs match this business; choose one or mark as duplicates."]
        elif len(strong) == 1 and len(claims[strong[0]["here_id"]]) > 1:
            outcome, reasons = "fallout_review", ["Another discovered business also matches the same HERE POI."]
        elif len(strong) == 1:
            match = strong[0]
            if match["chain"] and match["level"] != "confirmed":
                outcome, reasons = "fallout_review", ["Chain brand: a unit-level signal (phone, address or branch page) is required."]
        elif cands:
            outcome, reasons = "fallout_review", ["Possible HERE match, but identity is not confirmed."]
        else:
            outcome = "potential_new"
            reasons = ["No HERE POI within 1 km shares this identity. Confirm it is not represented under another name or parent."]
        if match and not outcome:
            if any(c["field"] in ("name", "category", "status") for c in m["conflicts"]):
                outcome, reasons = "fallout_review", ["Linked sources disagree: " + ", ".join(c["field"] for c in m["conflicts"]) + "."]
            elif m["status"] in CLOSED:
                outcome = "potential_delete"
                reasons = ["A permitted source reports this business as closed. Delete still needs closure evidence (D5/D6)."]
        here_rec = here_index.get(match["here_id"]) if match else None
        diffs = attribute_differences(m, here_rec) if here_rec else []
        if match and not outcome:
            outcome = "potential_update" if diffs else "no_change"
            reasons = [f"Identity {match['level']} in band {match['band']} ({match['distance_m']} m)."] + \
                      ([f"Differences: {', '.join(d['field'] for d in diffs)}."] if diffs else [])
        if here_rec:
            matched_here.add(here_rec["id"])
        if outcome == "fallout_review":
            # These HERE POIs are reviewed inside the fallout task; don't also queue them for verification.
            referenced_here.update(c["here_id"] for c in cands)
        identity = f"here:{here_rec['place_id']}" if here_rec and outcome != "fallout_review" else f"master:{m['master_key']}"
        rule = {"B0": "D1", "B1": "D2", "B2": "D3", "B3": "D4"}.get(match["band"]) if match else None
        explanation = {
            "label": OUTCOMES[outcome], "reasons": reasons, "match": match, "candidates": cands[:5],
            "changed_fields": diffs, "master": _master_summary(m), "here": _here_summary(here_rec) if here_rec else None,
        }
        results.append(_result(dataset_id, identity, outcome, m, here_rec, match, rule, explanation))

    for h in here:
        if h["id"] in matched_here or h["id"] in referenced_here:
            continue
        explanation = {
            "label": OUTCOMES["verification_required"],
            "reasons": ["No permitted source observed this HERE POI. Absence is not a deletion; verify existence."],
            "match": None, "candidates": [], "changed_fields": [], "master": None, "here": _here_summary(h),
        }
        results.append(_result(dataset_id, f"here:{h['place_id']}", "verification_required", None, h, None, "D7", explanation))

    stats = {
        "rules_version": RULES_VERSION, "here_records": len(here), "observations": len(obs),
        "masters": len(masters), "multi_source_masters": sum(1 for m in masters if len(m["members"]) > 1),
        "duplicates_removed": len(obs) - len(masters),
        "outcomes": {k: sum(1 for r in results if r["outcome"] == k) for k in OUTCOMES},
        "by_source": _source_stats(masters, results),
    }
    return {"masters": masters, "results": results, "stats": stats}


def _result(dataset_id, identity, outcome, master, here_rec, match, rule, explanation):
    content = {"outcome": outcome, "here": here_rec["place_id"] if here_rec else None,
               "observations": master["observation_ids"] if master else [],
               "fields": sorted(d["field"] for d in explanation["changed_fields"]),
               "candidates": sorted(c["place_id"] for c in explanation["candidates"]), "rules": RULES_VERSION}
    return {
        "result_key": sha(dataset_id, identity), "content_hash": sha(json.dumps(content, sort_keys=True)),
        "outcome": outcome, "master_key": master["master_key"] if master else None,
        "here_id": here_rec["id"] if here_rec else None, "here_place_id": here_rec["place_id"] if here_rec else None,
        "distance_m": match["distance_m"] if match else None, "band": match["band"] if match else None,
        "decision_rule": rule, "priority": PRIORITY[outcome], "explanation": explanation,
    }


def _source_stats(masters, results):
    by_master = {r["master_key"]: r["outcome"] for r in results if r["master_key"]}
    stats = defaultdict(lambda: {"observations": 0, "matched": 0, "unmatched": 0, "shared_with_other_sources": 0})
    for m in masters:
        sources = {o["source_name"] or o["source_type"] for o in m["members"]}
        outcome = by_master.get(m["master_key"])
        for o in m["members"]:
            s = stats[o["source_name"] or o["source_type"]]
            s["observations"] += 1
            s["matched" if outcome in ("no_change", "potential_update", "potential_delete") else "unmatched"] += 1
            if len(sources) > 1:
                s["shared_with_other_sources"] += 1
    return dict(stats)
