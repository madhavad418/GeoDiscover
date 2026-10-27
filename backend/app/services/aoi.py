"""HERE-supplied AOI boundaries (WGS84) and point containment, boundary edges included."""
import json
from functools import lru_cache
from pathlib import Path

RESOURCES = Path(__file__).resolve().parents[1] / "resources"
EDGE_TOLERANCE_DEG = 1e-9


@lru_cache
def boundaries():
    data = json.loads((RESOURCES / "aoi_boundaries.json").read_text(encoding="utf-8"))
    out = {}
    for aoi, collection in data.items():
        polygons = []
        for feature in collection["features"]:
            geom = feature["geometry"]
            polygons += geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        out[aoi] = polygons
    return out


def _on_segment(x, y, x1, y1, x2, y2):
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    if abs(cross) > EDGE_TOLERANCE_DEG:
        return False
    return min(x1, x2) - EDGE_TOLERANCE_DEG <= x <= max(x1, x2) + EDGE_TOLERANCE_DEG and \
        min(y1, y2) - EDGE_TOLERANCE_DEG <= y <= max(y1, y2) + EDGE_TOLERANCE_DEG


def _in_ring(x, y, ring):
    inside = False
    for i in range(len(ring)):
        x1, y1 = ring[i][:2]
        x2, y2 = ring[i - 1][:2]
        if _on_segment(x, y, x1, y1, x2, y2):
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(aoi, lon, lat):
    """True when (lon, lat) is inside or on the edge of the AOI (ST_Covers semantics)."""
    for polygon in boundaries().get(aoi, []):
        if _in_ring(lon, lat, polygon[0]) and not any(_in_ring(lon, lat, hole) for hole in polygon[1:]):
            return True
    return False
