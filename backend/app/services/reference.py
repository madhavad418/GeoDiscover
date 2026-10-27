"""HERE reference data: category codes, chain names and the profanity list (built by build_reference_data.py)."""
import json
import re
from functools import lru_cache
from pathlib import Path

from .matching import fold, norm_name

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
CATEGORY_CODE = re.compile(r"^\d{3}-\d{4}-\d{4}$")


@lru_cache
def data():
    return json.loads((RESOURCES / "reference_data.json").read_text(encoding="utf-8"))


def categories() -> dict[str, str]:
    return data()["categories"]


@lru_cache
def category_by_name() -> dict[str, str]:
    out = {}
    for code, name in categories().items():
        out.setdefault(norm_name(name), code)
    return out


def resolve_category(code, name):
    """Return (code, name) using the supplied HERE category reference; unknown free text keeps no code."""
    code = (code or "").strip()
    if code and CATEGORY_CODE.match(code):
        return code, (name or categories().get(code))
    mapped = category_by_name().get(norm_name(name or ""))
    return mapped, name or None


def chain_names(country) -> list[str]:
    return data()["chains"].get(country, [])


@lru_cache
def _profanity(country):
    rules = []
    for rule in data()["profanity"]:
        if "ALL" in rule["countries"] or country in rule["countries"]:
            phrase = fold(rule["phrase"]).strip()
            if phrase:
                rules.append((phrase, rule["whole_name"]))
    return rules


def profanity_hits(text, country):
    """Phrases from the HERE profanity list found in `text` (whole-name rules must equal the entire name)."""
    if not text:
        return []
    folded = fold(text).strip()
    hits = []
    for phrase, whole_name in _profanity(country):
        if whole_name:
            if folded == phrase:
                hits.append(phrase)
        elif re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", folded):
            hits.append(phrase)
    return hits


def find_places() -> dict[str, str]:
    """OPR Find Places code (space-separated, e.g. 'casual dining') -> PDS category code."""
    return data().get("find_places", {})


@lru_cache
def foodtype_by_name() -> dict[str, str]:
    return {norm_name(name): code for code, name in data().get("foodtypes", {}).items()}


def foodtypes() -> dict[str, str]:
    return data().get("foodtypes", {})


def chain_ids(country) -> dict[str, str]:
    """Chain name -> HERE chainid seen in the supplied baseline extracts for this country."""
    return data().get("chain_ids", {}).get(country, {})
