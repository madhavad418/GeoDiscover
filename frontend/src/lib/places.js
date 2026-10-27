// Point ("places") layers from CSV / Excel / point GeoJSON.
import Papa from 'papaparse';
import { read, utils } from 'xlsx';
import { mergeBbox } from './geo.js';

export const CATEGORY_COLORS = ['#4FC3F7', '#FFB547', '#7BD88F', '#FF6B8B', '#B98CFF', '#3DD6C6', '#FF8A4C', '#F06292', '#D4E157'];
export const OTHER_COLOR = '#8A94A6';
export const UNCATEGORISED = 'Uncategorised';
const COMPLEX_SCRIPT = /[฀-໿က-႟ក-៿ༀ-࿿]/;

const LAT_KEYS = ['displaylatitude', 'latitude', 'lat', 'y', 'point_y', 'ycoord', 'y_coord', 'routinglatitude'];
const LON_KEYS = ['displaylongitude', 'longitude', 'lon', 'lng', 'long', 'x', 'point_x', 'xcoord', 'x_coord', 'routinglongitude'];
const ID_KEYS = ['placeid', 'place_id', 'poi_id', 'poiid', 'id', 'objectid', 'fid', 'uid'];
const NAME_KEYS = ['name1', 'name', 'poi_name', 'place_name', 'title', 'label', 'name2'];
const CAT_KEYS = ['primarycategorynm', 'category', 'category_name', 'primary_category', 'categoryname', 'type', 'amenity', 'class', 'fclass'];
const ADDRESS_KEYS = ['upaddress', 'address', 'full_address', 'formatted_address', 'addr', 'street_address'];

function findKey(fields, candidates, fuzzy) {
  const lower = new Map(fields.map((f) => [f.toLowerCase().trim(), f]));
  for (const c of candidates) if (lower.has(c)) return lower.get(c);
  return fuzzy ? fields.find((f) => fuzzy.test(f)) || null : null;
}

export function detectKeys(fields) {
  return {
    lat: findKey(fields, LAT_KEYS, /lat/i),
    lon: findKey(fields, LON_KEYS, /lon|lng/i),
    routeLat: findKey(fields, ['routinglatitude', 'entry_lat', 'nav_lat']),
    routeLon: findKey(fields, ['routinglongitude', 'entry_lon', 'nav_lon']),
    id: findKey(fields, ID_KEYS),
    name: findKey(fields, NAME_KEYS, /name/i),
    cat: findKey(fields, CAT_KEYS, /categ/i),
    address: findKey(fields, ADDRESS_KEYS, /addr/i),
  };
}

export function parseCsv(text) {
  const res = Papa.parse(text, {
    header: true,
    skipEmptyLines: 'greedy',
    transformHeader: (h) => h.replace(/^\uFEFF/, '').trim(),
  });
  return { fields: res.meta.fields || [], rows: res.data };
}

/** Every sheet that has columns; the caller decides which have coordinates. */
export function parseWorkbook(buffer) {
  const wb = read(buffer, { type: 'array' });
  return wb.SheetNames.map((sheet) => {
    const rows = utils.sheet_to_json(wb.Sheets[sheet], { defval: '', raw: true });
    const fields = rows.length ? Object.keys(rows[0]) : [];
    return { sheet, fields, rows };
  }).filter((s) => s.rows.length);
}

const validLatLon = (lat, lon) => isFinite(lat) && isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && !(lat === 0 && lon === 0);

/** Rows (objects) -> point features. Returns { features, skipped }. */
export function rowsToFeatures(rows, keys) {
  const features = [];
  let skipped = 0;
  for (const row of rows) {
    const lat = parseFloat(row[keys.lat]);
    const lon = parseFloat(row[keys.lon]);
    if (!validLatLon(lat, lon)) { skipped++; continue; }
    const properties = {};
    for (const [k, v] of Object.entries(row)) properties[k] = typeof v === 'string' ? v.trim() : v;
    features.push({ type: 'Feature', properties, geometry: { type: 'Point', coordinates: [lon, lat] } });
  }
  return { features, skipped };
}

/** Builds the in-memory model for a places layer (no map side effects). */
export function buildPointLayer({ fileName, base, title, iso, fields, keys, features, source }) {
  const counts = new Map();
  features.forEach((f, i) => {
    f.id = i;
    const p = f.properties;
    const cat = (keys.cat && String(p[keys.cat] ?? '').trim()) || UNCATEGORISED;
    p._name = (keys.name && String(p[keys.name] ?? '').trim()) || (keys.id && String(p[keys.id] ?? '')) || `Place ${i + 1}`;
    p._cat = cat;
    // MapLibre's line breaking can fail on these scripts (Thai, Lao, Myanmar, Khmer, Tibetan),
    // dropping a tile's labels; such places get single-line labels instead (see mapLayers.js).
    p._nowrap = Object.values(p).some((v) => typeof v === 'string' && COMPLEX_SCRIPT.test(v));
    counts.set(cat, (counts.get(cat) || 0) + 1);
  });
  const categories = [...counts]
    .sort((a, b) => b[1] - a[1])
    .map(([name, count], i) => ({ name, count, color: i < CATEGORY_COLORS.length && name !== UNCATEGORISED ? CATEGORY_COLORS[i] : OTHER_COLOR }));
  const colorOf = new Map(categories.map((c) => [c.name, c.color]));
  for (const f of features) f.properties._cc = colorOf.get(f.properties._cat);

  const bbox = mergeBbox(features.map(({ geometry: { coordinates: [x, y] } }) => [x, y, x, y]));
  return {
    kind: 'points',
    fileName, base, title, iso,
    displayName: iso ? `${title}, ${iso}` : title,
    data: { type: 'FeatureCollection', features },
    bbox,
    fields: fields.filter((f) => !f.startsWith('_')),
    keys,
    categories,
    hiddenCats: [],
    labelKey: keys.name || keys.id || '_name',
    geomLabel: 'place',
    totalArea: 0,
    meta: { source },
    visible: true, labels: true, opacity: 1, expanded: false,
  };
}

/** Features currently shown, after the category filter. */
export function visiblePlaces(L) {
  if (!L.hiddenCats.length) return L.data.features;
  const hidden = new Set(L.hiddenCats);
  return L.data.features.filter((f) => !hidden.has(f.properties._cat));
}

/* ---------- Details helpers ---------- */
const DAYS = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY'];

/** "MONDAY:07:30:00-16:00:00,..." -> [{ day, ranges: ['07:30–16:00'] }] or null if unparseable. */
export function parseOpeningHours(text) {
  if (!text) return null;
  const byDay = new Map();
  for (const part of String(text).split(',')) {
    const m = /^\s*([A-Z]+):(\d\d:\d\d)(?::\d\d)?-(\d\d:\d\d)(?::\d\d)?\s*$/i.exec(part);
    if (!m) return null;
    const day = m[1].toUpperCase();
    if (!byDay.has(day)) byDay.set(day, []);
    byDay.get(day).push(`${m[2]}–${m[3]}`);
  }
  return DAYS.map((day) => ({ day: day[0] + day.slice(1, 3).toLowerCase(), ranges: byDay.get(day) || null }));
}

export const splitList = (v) => String(v ?? '').split(/[,;|]/).map((s) => s.trim()).filter(Boolean);

/** All usable http(s) links in a field that may hold several, e.g. "site.com,https//www.site.com". */
export function safeUrls(v) {
  const seen = new Set();
  return splitList(v).map(safeUrl).filter((u) => {
    const key = u && u.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');
    if (!u || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function safeUrl(v) {
  // Repair a common data-entry slip: "https//host" -> "https://host".
  const s = String(v ?? '').trim().replace(/^(https?)\/\//i, '$1://');
  if (!s) return null;
  const url = /^https?:\/\//i.test(s) ? s : `https://${s}`;
  try {
    const u = new URL(url);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

/** Point to use for Street View: the routing (on-road) point when present, else the display point. */
export function streetViewPoint(L, f) {
  const lat = parseFloat(f.properties[L.keys.routeLat]);
  const lon = parseFloat(f.properties[L.keys.routeLon]);
  if (validLatLon(lat, lon)) return [lon, lat];
  return f.geometry.coordinates;
}

export const streetViewUrl = ([lon, lat]) => `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat},${lon}`;
export const mapsUrl = ([lon, lat]) => `https://www.google.com/maps/search/?api=1&query=${lat},${lon}`;
