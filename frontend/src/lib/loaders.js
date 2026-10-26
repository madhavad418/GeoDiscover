import shp, { combine, parseShp, parseDbf } from 'shpjs';
import {
  eachCoord, unprojectMercator, geomArea, geomPerimeter, geomBbox, mergeBbox, featureCenter, distinctColor,
} from './geo.js';
import { buildPointLayer, detectKeys, parseCsv, parseWorkbook, rowsToFeatures } from './places.js';

export const LAYER_COLORS = ['#7C9CFF', '#FFB547', '#3DD6C6', '#FF6B8B', '#B98CFF', '#7BD88F', '#FF8A4C', '#4FC3F7'];
export const ACCEPT = '.geojson,.json,.zip,.shp,.dbf,.prj,.cpg,.qmd,.csv,.tsv,.txt,.xlsx,.xls';

const extOf = (name) => (/\.([^.]+)$/.exec(name)?.[1] || '').toLowerCase();
export const baseOf = (name) => name.replace(/^.*[\\/]/, '').replace(/\.[^.]+$/, '');

// "Divisoria_PHL" -> { title: "Divisoria", iso: "PHL" }
export function prettyName(base) {
  const clean = base.replace(/-\d+$/, '');
  const m = /(?:_([A-Z]{3}))+$/.exec(clean);
  const title = (m ? clean.slice(0, m.index) : clean).replace(/_+/g, ' ').trim() || base;
  return { title, iso: m ? m[1] : '' };
}

const NAME_KEYS = ['adm5_name', 'adm4_name', 'adm3_name', 'adm2_name', 'adm1_name', 'adm0_name', 'name', 'NAME', 'Name', 'name_en', 'NAME_EN', 'shapeName', 'title', 'label'];
function featureName(p, i) {
  for (const k of NAME_KEYS) if (p[k] != null && p[k] !== '') return { name: String(p[k]), key: k };
  const k = Object.keys(p).find((key) => /name/i.test(key) && typeof p[key] === 'string' && p[key]);
  return k ? { name: p[k], key: k } : { name: `Feature ${i + 1}`, key: null };
}

function toFeatures(obj) {
  if (!obj || typeof obj !== 'object') throw new Error('not a GeoJSON object');
  if (obj.type === 'FeatureCollection') return obj.features || [];
  if (obj.type === 'Feature') return [obj];
  if (obj.type && (obj.coordinates || obj.geometries)) return [{ type: 'Feature', properties: {}, geometry: obj }];
  throw new Error('unrecognised GeoJSON structure');
}

function looksProjected(features) {
  let out = false;
  for (const f of features) {
    eachCoord(f.geometry, (c) => { if (Math.abs(c[0]) > 180 || Math.abs(c[1]) > 90) out = true; });
    if (out) return true;
  }
  return false;
}

/** Builds the in-memory layer model (no map side effects). */
function buildLayer({ fileName, base, geojson, meta = {} }, notify) {
  const crsName = geojson.crs?.properties?.name || '';
  const features = toFeatures(geojson).filter((f) => f?.geometry && (f.geometry.coordinates || f.geometry.geometries));
  if (!features.length) throw new Error('no features with geometry');

  if (/3857|900913|3785/.test(crsName) || looksProjected(features)) {
    unprojectMercator(features);
    notify(`${fileName}: reprojected from Web Mercator to WGS84`, 'warn');
  } else if (crsName && !/CRS84|4326/.test(crsName)) {
    notify(`${fileName}: CRS "${crsName}" not recognised, assuming WGS84`, 'warn');
  }

  const { title, iso } = prettyName(base);
  if (features.every((f) => f.geometry.type === 'Point')) {
    const fields = [...new Set(features.flatMap((f) => Object.keys(f.properties || {})))];
    for (const f of features) f.properties = f.properties || {};
    return buildPointLayer({ fileName, base, title, iso, fields, keys: detectKeys(fields), features, source: meta.source || 'GeoJSON points' });
  }

  const stats = [];
  features.forEach((f, i) => {
    f.id = i;
    f.properties = f.properties || {};
    const { name, key } = featureName(f.properties, i);
    f.properties._name = name;
    f.properties._c = distinctColor(i);
    stats.push({ area: geomArea(f.geometry), perim: geomPerimeter(f.geometry), bbox: geomBbox(f.geometry), center: featureCenter(f), key });
  });

  const kinds = new Set(features.map((f) => f.geometry.type.replace('Multi', '')));
  return {
    kind: 'shapes',
    fileName, base, title, iso,
    displayName: iso ? `${title}, ${iso}` : title,
    data: { type: 'FeatureCollection', features },
    stats,
    bbox: mergeBbox(stats.map((s) => s.bbox)),
    totalArea: stats.reduce((s, x) => s + x.area, 0),
    geomLabel: kinds.size === 1 ? ({ Polygon: 'polygon', LineString: 'line', Point: 'point' }[[...kinds][0]] || 'feature') : 'feature',
    meta: { crs: crsName.replace(/^urn:ogc:def:crs:/, ''), ...meta },
    // display settings
    visible: true, labels: true, opacity: 1, distinct: features.length > 1, expanded: false,
  };
}

function parseQmd(text) {
  const doc = new DOMParser().parseFromString(text, 'application/xml');
  const get = (sel) => doc.querySelector(sel)?.textContent?.trim() || '';
  const authid = get('crs authid');
  const desc = get('crs description');
  return { qmdCrs: authid ? `${authid}${desc ? ` · ${desc}` : ''}` : '' };
}

/**
 * Reads a batch of dropped/picked files.
 * Returns { layers, qmds: [{ base, meta }] }; problems are reported through notify(msg, type).
 */
export async function readFiles(fileList, notify) {
  const layers = [];
  const qmds = [];
  const shpParts = new Map(); // base -> { shp, dbf, prj, cpg }

  const tryBuild = (input) => {
    try { layers.push(buildLayer(input, notify)); } catch (err) { notify(`${input.fileName}: ${err.message || err}`, 'error'); }
  };
  const addPlaces = ({ fileName, base, fields, rows, source }) => {
    const keys = detectKeys(fields);
    if (!keys.lat || !keys.lon) throw new Error(`no latitude/longitude columns found (columns: ${fields.slice(0, 8).join(', ')}…)`);
    const { features, skipped } = rowsToFeatures(rows, keys);
    if (!features.length) throw new Error('no rows with valid coordinates');
    if (skipped) notify(`${fileName}: skipped ${skipped} row${skipped > 1 ? 's' : ''} without valid coordinates`, 'warn');
    const { title, iso } = prettyName(base);
    layers.push(buildPointLayer({ fileName, base, title, iso, fields, keys, features, source }));
  };

  for (const file of fileList) {
    const ext = extOf(file.name);
    const base = baseOf(file.name);
    try {
      if (ext === 'geojson' || ext === 'json') {
        tryBuild({ fileName: file.name, base, geojson: JSON.parse(await file.text()) });
      } else if (ext === 'zip') {
        const result = await shp(await file.arrayBuffer());
        const list = Array.isArray(result) ? result : [result];
        for (const gj of list) {
          const inner = list.length > 1 && gj.fileName ? baseOf(gj.fileName) : base;
          tryBuild({ fileName: file.name, base: inner, geojson: gj, meta: { source: 'Shapefile (zip)' } });
        }
      } else if (['shp', 'dbf', 'prj', 'cpg'].includes(ext)) {
        const part = shpParts.get(base) || {};
        part[ext] = ext === 'shp' || ext === 'dbf' ? await file.arrayBuffer() : await file.text();
        shpParts.set(base, part);
      } else if (['csv', 'tsv', 'txt'].includes(ext)) {
        const { fields, rows } = parseCsv(await file.text());
        addPlaces({ fileName: file.name, base, fields, rows, source: ext.toUpperCase() });
      } else if (ext === 'xlsx' || ext === 'xls') {
        const sheets = parseWorkbook(await file.arrayBuffer());
        const usable = sheets.filter((s) => { const k = detectKeys(s.fields); return k.lat && k.lon; });
        if (!usable.length) throw new Error('no sheet with latitude/longitude columns');
        for (const s of usable) {
          addPlaces({ fileName: file.name, base: usable.length > 1 ? `${base} · ${s.sheet}` : base, fields: s.fields, rows: s.rows, source: `Excel · ${s.sheet}` });
        }
      } else if (ext === 'qmd') {
        qmds.push({ base, meta: parseQmd(await file.text()) });
      } else {
        notify(`${file.name}: unsupported file type`, 'warn');
      }
    } catch (err) {
      console.error(err);
      notify(`${file.name}: ${err.message || err}`, 'error');
    }
  }

  for (const [base, part] of shpParts) {
    if (!part.shp) {
      if (part.dbf) notify(`${base}.dbf: needs the matching .shp file`, 'warn');
      continue;
    }
    try {
      const geoms = parseShp(part.shp, part.prj);
      const props = part.dbf ? parseDbf(part.dbf, part.cpg) : geoms.map(() => ({}));
      if (!part.prj) notify(`${base}.shp: no .prj supplied, assuming WGS84`, 'warn');
      tryBuild({ fileName: `${base}.shp`, base, geojson: combine([geoms, props]), meta: { source: 'Shapefile' } });
    } catch (err) {
      notify(`${base}.shp: ${err.message || err}`, 'error');
    }
  }

  return { layers, qmds };
}

export function exportableFeature(f) {
  const properties = Object.fromEntries(Object.entries(f.properties).filter(([k]) => !k.startsWith('_')));
  return { type: 'Feature', properties, geometry: f.geometry };
}

export const slug = (s) => String(s).replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '') || 'feature';

export function download(data, name, type) {
  const blob = data instanceof Blob ? data : new Blob([data], { type });
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
