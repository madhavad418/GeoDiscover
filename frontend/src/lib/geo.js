// Geometry measurements and display formatting. Coordinates are WGS84 [lon, lat].

const RAD = Math.PI / 180;
export const EARTH_RADIUS = 6378137;

export function eachCoord(geom, fn) {
  if (!geom) return;
  if (geom.type === 'GeometryCollection') return geom.geometries.forEach((g) => eachCoord(g, fn));
  (function walk(c) {
    if (typeof c[0] === 'number') fn(c);
    else c.forEach(walk);
  })(geom.coordinates);
}

// Spherical ring area (Chamberlain & Duquette), in m².
export function ringArea(ring) {
  const n = ring.length;
  if (n < 3) return 0;
  let a = 0;
  for (let i = 0; i < n; i++) {
    const [x1, y1] = ring[i];
    const [x2, y2] = ring[(i + 1) % n];
    a += (x2 - x1) * RAD * (2 + Math.sin(y1 * RAD) + Math.sin(y2 * RAD));
  }
  return Math.abs((a * EARTH_RADIUS * EARTH_RADIUS) / 2);
}

const polygonArea = (rings) => rings.reduce((sum, ring, i) => sum + (i === 0 ? 1 : -1) * ringArea(ring), 0);

export function geomArea(g) {
  if (!g) return 0;
  if (g.type === 'Polygon') return polygonArea(g.coordinates);
  if (g.type === 'MultiPolygon') return g.coordinates.reduce((s, p) => s + polygonArea(p), 0);
  if (g.type === 'GeometryCollection') return g.geometries.reduce((s, x) => s + geomArea(x), 0);
  return 0;
}

export function haversine([x1, y1], [x2, y2]) {
  const dLat = (y2 - y1) * RAD;
  const dLon = (x2 - x1) * RAD;
  const a = Math.sin(dLat / 2) ** 2 + Math.cos(y1 * RAD) * Math.cos(y2 * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS * Math.asin(Math.min(1, Math.sqrt(a)));
}

export function lineLength(coords) {
  let d = 0;
  for (let i = 1; i < coords.length; i++) d += haversine(coords[i - 1], coords[i]);
  return d;
}

export function geomPerimeter(g) {
  if (!g) return 0;
  switch (g.type) {
    case 'LineString': return lineLength(g.coordinates);
    case 'MultiLineString':
    case 'Polygon': return g.coordinates.reduce((s, r) => s + lineLength(r), 0);
    case 'MultiPolygon': return g.coordinates.reduce((s, p) => s + p.reduce((t, r) => t + lineLength(r), 0), 0);
    case 'GeometryCollection': return g.geometries.reduce((s, x) => s + geomPerimeter(x), 0);
    default: return 0;
  }
}

export function geomBbox(g) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  eachCoord(g, ([x, y]) => {
    if (x < b[0]) b[0] = x;
    if (y < b[1]) b[1] = y;
    if (x > b[2]) b[2] = x;
    if (y > b[3]) b[3] = y;
  });
  return b;
}

export function mergeBbox(list) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  for (const x of list) {
    if (!x || !isFinite(x[0])) continue;
    b[0] = Math.min(b[0], x[0]);
    b[1] = Math.min(b[1], x[1]);
    b[2] = Math.max(b[2], x[2]);
    b[3] = Math.max(b[3], x[3]);
  }
  return isFinite(b[0]) ? b : null;
}

export const bboxCenter = (b) => [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2];

export function countCoords(g) {
  let n = 0;
  eachCoord(g, () => n++);
  return n;
}

function ringCentroid(ring) {
  // Planar centroid, offset by the first vertex for numerical stability.
  const [ox, oy] = ring[0];
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const x1 = ring[i][0] - ox, y1 = ring[i][1] - oy;
    const next = ring[(i + 1) % ring.length];
    const x2 = next[0] - ox, y2 = next[1] - oy;
    const k = x1 * y2 - x2 * y1;
    a += k;
    cx += (x1 + x2) * k;
    cy += (y1 + y2) * k;
  }
  if (!a) return null;
  return [cx / (3 * a) + ox, cy / (3 * a) + oy];
}

export function featureCenter(f) {
  const p = f.properties;
  const g = f.geometry;
  const lat = parseFloat(p.center_lat ?? p.centroid_lat);
  const lon = parseFloat(p.center_lon ?? p.centroid_lon);
  if (isFinite(lat) && isFinite(lon)) return [lon, lat];
  if (g.type === 'Point') return g.coordinates;
  const polys = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : null;
  if (polys) {
    const largest = polys.reduce((best, poly) => (ringArea(poly[0]) > ringArea(best[0]) ? poly : best));
    const c = ringCentroid(largest[0]);
    if (c) return c;
  }
  return bboxCenter(geomBbox(g));
}

function pointInRing([x, y], ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
const pointInPolygon = (pt, rings) => pointInRing(pt, rings[0]) && !rings.slice(1).some((h) => pointInRing(pt, h));

export function pointInGeom(pt, g) {
  if (g.type === 'Polygon') return pointInPolygon(pt, g.coordinates);
  if (g.type === 'MultiPolygon') return g.coordinates.some((p) => pointInPolygon(pt, p));
  if (g.type === 'GeometryCollection') return g.geometries.some((x) => pointInGeom(pt, x));
  return false;
}

export const inBbox = ([x, y], b) => x >= b[0] && x <= b[2] && y >= b[1] && y <= b[3];

// Converts EPSG:3857 metres to WGS84 degrees in place.
export function unprojectMercator(features) {
  for (const f of features) {
    eachCoord(f.geometry, (c) => {
      c[0] = c[0] / EARTH_RADIUS / RAD;
      c[1] = (2 * Math.atan(Math.exp(c[1] / EARTH_RADIUS)) - Math.PI / 2) / RAD;
    });
  }
}

/* ---------- Formatting ---------- */
export function fmtArea(m2) {
  if (m2 >= 1e5) return `${(m2 / 1e6).toLocaleString(undefined, { maximumFractionDigits: m2 >= 1e8 ? 0 : m2 >= 1e7 ? 1 : 2 })} km²`;
  return `${(m2 / 1e4).toFixed(m2 >= 1e3 ? 1 : 2)} ha`;
}
export const fmtDist = (m) => (m < 1000 ? `${m.toFixed(0)} m` : `${(m / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })} km`);
export const fmtNum = (n) => n.toLocaleString();
export const fmtCoord = (lat, lon, d = 5) =>
  `${Math.abs(lat).toFixed(d)}° ${lat >= 0 ? 'N' : 'S'}, ${Math.abs(lon).toFixed(d)}° ${lon >= 0 ? 'E' : 'W'}`;
export const distinctColor = (i) => `hsl(${Math.round((i * 137.508 + 215) % 360)}, 78%, 64%)`;
export const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
export const plural = (n, word, many = `${word}s`) => `${fmtNum(n)} ${n === 1 ? word : many}`;
