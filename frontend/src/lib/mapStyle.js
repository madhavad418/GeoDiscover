// Esri's public raster services need no API key (CARTO's now watermark keyless requests).
const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services';
const esri = (service, maxzoom = 18, attr = '') => ({ tiles: [`${ESRI}/${service}/MapServer/tile/{z}/{y}/{x}`], maxzoom, attr });
const thumb = (service) => `${ESRI}/${service}/MapServer/tile/5/14/24`;
// Canvas label tiles stop at z16; overzoomed raster text turns huge and blurry, so hide it past this.
const CANVAS_LABEL_MAX = 16.6;
const ESRI_ATTR = 'Tiles © <a href="https://www.esri.com">Esri</a> — Esri, HERE, Garmin, © OpenStreetMap contributors';

export const FONT = ['Noto Sans Medium'];
const GLYPHS = 'https://protomaps.github.io/basemaps-assets/fonts/{fontstack}/{range}.pbf';

export const BASEMAPS = {
  dark: {
    label: 'Dark', tone: 'dark', bg: '#242424', thumb: thumb('Canvas/World_Dark_Gray_Base'),
    sources: [esri('Canvas/World_Dark_Gray_Base', 16, ESRI_ATTR), { ...esri('Canvas/World_Dark_Gray_Reference', 16), hideAbove: CANVAS_LABEL_MAX }],
  },
  light: {
    label: 'Light', tone: 'light', bg: '#e8e8e6', thumb: thumb('Canvas/World_Light_Gray_Base'),
    sources: [esri('Canvas/World_Light_Gray_Base', 16, ESRI_ATTR), { ...esri('Canvas/World_Light_Gray_Reference', 16), hideAbove: CANVAS_LABEL_MAX }],
  },
  streets: { label: 'Streets', tone: 'light', bg: '#f5f3ee', thumb: thumb('World_Street_Map'), sources: [esri('World_Street_Map', 18, ESRI_ATTR)] },
  satellite: {
    label: 'Satellite', tone: 'dark', bg: '#0a0d16', thumb: thumb('World_Imagery'),
    sources: [
      esri('World_Imagery', 18, 'Imagery © Esri, Maxar, Earthstar Geographics'),
      esri('Reference/World_Boundaries_and_Places', 18),
    ],
  },
};

// Data layers are inserted below these so ordering stays stable: shapes < places < labels < measure.
export const ANCHOR_SHAPES = 'anchor-shapes';
export const ANCHOR_POINTS = 'anchor-points';
export const ANCHOR_LABELS = 'anchor-labels';

// Below this zoom each layer collapses to a glowing marker so far-apart AOIs stay visible.
export const OVERVIEW_MAX_ZOOM = 11;

export function buildStyle(basemap) {
  const sources = {};
  const layers = [{ id: 'bg', type: 'background', paint: { 'background-color': BASEMAPS[basemap].bg } }];
  for (const [key, bm] of Object.entries(BASEMAPS)) {
    bm.sources.forEach((s, i) => {
      const id = `bm-${key}-${i}`;
      sources[id] = { type: 'raster', tiles: s.tiles, tileSize: 256, maxzoom: s.maxzoom, attribution: s.attr };
      layers.push({
        id, type: 'raster', source: id,
        ...(s.hideAbove && { maxzoom: s.hideAbove }),
        layout: { visibility: key === basemap ? 'visible' : 'none' },
      });
    });
  }
  for (const id of [ANCHOR_SHAPES, ANCHOR_POINTS, ANCHOR_LABELS]) {
    layers.push({ id, type: 'background', layout: { visibility: 'none' }, paint: { 'background-color': '#000' } });
  }
  return { version: 8, glyphs: GLYPHS, sources, layers };
}

export function labelPaint(tone) {
  return tone === 'light'
    ? { 'text-color': '#151b29', 'text-halo-color': 'rgba(255,255,255,0.95)', 'text-halo-width': 1.6 }
    : { 'text-color': '#F4F6FB', 'text-halo-color': 'rgba(8,11,20,0.9)', 'text-halo-width': 1.6 };
}
