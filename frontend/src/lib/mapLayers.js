// Imperative MapLibre wiring for one layer: sources, sublayers, paint and visibility.
// Boundary layers ("shapes") and place layers ("points") use different sublayer sets.
import { bboxCenter } from './geo.js';
import { FONT, ANCHOR_SHAPES, ANCHOR_POINTS, ANCHOR_LABELS, OVERVIEW_MAX_ZOOM, labelPaint } from './mapStyle.js';
import { visiblePlaces } from './places.js';

const fc = (features) => ({ type: 'FeatureCollection', features });
const pointFeature = (coordinates, properties, id) => ({ type: 'Feature', id, properties, geometry: { type: 'Point', coordinates } });

const SUBLAYERS = {
  shapes: ['fill', 'glow', 'line', 'pt', 'halo', 'dot', 'area-lbl', 'lbl'],
  points: ['cluster', 'count', 'pt', 'ring', 'plbl'],
};
const LABEL_SUBLAYERS = new Set(['area-lbl', 'lbl', 'plbl']);
export const INTERACTIVE_SUBLAYERS = { shapes: ['dot', 'pt', 'fill', 'line'], points: ['cluster', 'pt'] };
// Unclustered places are drawn individually from this zoom on.
const CLUSTER_MAX_ZOOM = 15;

const selected = ['boolean', ['feature-state', 'selected'], false];
const hovered = ['boolean', ['feature-state', 'hover'], false];
const notCluster = ['!', ['has', 'point_count']];

export function addToMap(map, L) {
  if (L.kind === 'points') return addPoints(map, L);
  const features = L.data.features;
  map.addSource(L.id, { type: 'geojson', data: L.data });
  map.addSource(`${L.id}-lbl`, { type: 'geojson', data: fc(features.map((f, i) => pointFeature(L.stats[i].center, { _name: f.properties._name }, i))) });
  map.addSource(`${L.id}-ctr`, { type: 'geojson', data: fc([pointFeature(bboxCenter(L.bbox), { _name: L.displayName }, 0)]) });

  const isPoint = ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false];
  const add = (spec, anchor) => map.addLayer(spec, anchor);
  add({ id: `${L.id}-fill`, type: 'fill', source: L.id }, ANCHOR_SHAPES);
  add({ id: `${L.id}-glow`, type: 'line', source: L.id, layout: { 'line-join': 'round' }, paint: { 'line-blur': 6, 'line-width': ['case', selected, 12, 7] } }, ANCHOR_SHAPES);
  add({ id: `${L.id}-line`, type: 'line', source: L.id, layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-width': ['case', selected, 2.8, hovered, 2.2, 1.4] } }, ANCHOR_SHAPES);
  add({ id: `${L.id}-pt`, type: 'circle', source: L.id, filter: isPoint, paint: { 'circle-radius': 6, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' } }, ANCHOR_SHAPES);
  add({ id: `${L.id}-halo`, type: 'circle', source: `${L.id}-ctr`, maxzoom: OVERVIEW_MAX_ZOOM, paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 14, 10, 22], 'circle-blur': 0.7 } }, ANCHOR_LABELS);
  add({ id: `${L.id}-dot`, type: 'circle', source: `${L.id}-ctr`, maxzoom: OVERVIEW_MAX_ZOOM, paint: { 'circle-radius': 6, 'circle-stroke-width': 2.5, 'circle-stroke-color': '#fff' } }, ANCHOR_LABELS);
  add({ id: `${L.id}-area-lbl`, type: 'symbol', source: `${L.id}-ctr`, maxzoom: OVERVIEW_MAX_ZOOM, layout: { 'text-field': ['get', '_name'], 'text-font': FONT, 'text-size': 13, 'text-anchor': 'top', 'text-offset': [0, 1.1] } }, ANCHOR_LABELS);
  add({ id: `${L.id}-lbl`, type: 'symbol', source: `${L.id}-lbl`, minzoom: OVERVIEW_MAX_ZOOM, layout: { 'text-field': ['get', '_name'], 'text-font': FONT, 'text-size': ['interpolate', ['linear'], ['zoom'], 12, 11, 17, 14], 'text-max-width': 8, 'text-padding': 4 } }, ANCHOR_LABELS);
}

function addPoints(map, L) {
  map.addSource(L.id, { type: 'geojson', data: fc(visiblePlaces(L)), cluster: true, clusterRadius: 46, clusterMaxZoom: CLUSTER_MAX_ZOOM });
  const add = (spec, anchor = ANCHOR_POINTS) => map.addLayer(spec, anchor);
  add({
    id: `${L.id}-cluster`, type: 'circle', source: L.id, filter: ['has', 'point_count'],
    paint: { 'circle-radius': ['step', ['get', 'point_count'], 14, 25, 17, 100, 21, 500, 26, 2000, 31], 'circle-stroke-width': 6 },
  });
  add({
    id: `${L.id}-count`, type: 'symbol', source: L.id, filter: ['has', 'point_count'],
    layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': FONT, 'text-size': 12, 'text-allow-overlap': true, 'text-ignore-placement': true },
    paint: { 'text-color': '#0b0f19' },
  });
  add({
    id: `${L.id}-pt`, type: 'circle', source: L.id, filter: notCluster,
    paint: {
      'circle-color': ['get', '_cc'],
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 12, 4, 16, 6, 19, 9],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 17, 1.8],
    },
  });
  add({
    id: `${L.id}-ring`, type: 'circle', source: L.id, filter: notCluster,
    paint: {
      'circle-radius': ['case', selected, 13, 10],
      'circle-color': 'rgba(0,0,0,0)',
      'circle-stroke-width': ['case', selected, 3, hovered, 2, 0],
    },
  });
  add({
    id: `${L.id}-plbl`, type: 'symbol', source: L.id, filter: notCluster, minzoom: 16,
    layout: {
      'text-font': FONT, 'text-size': 11, 'text-variable-anchor': ['top', 'bottom', 'left', 'right'], 'text-radial-offset': 0.9, 'text-padding': 2,
      // No wrapping for complex-script places: MapLibre 6.16 line breaking throws on some Thai text.
      'text-max-width': ['case', ['to-boolean', ['get', '_nowrap']], 100, 9],
    },
  }, ANCHOR_LABELS);
}

/** Re-applies the category filter by replacing the clustered source data. */
export function applyPlaceFilter(map, L) {
  map.getSource(L.id)?.setData(fc(visiblePlaces(L)));
}

export function removeFromMap(map, L) {
  for (const s of SUBLAYERS[L.kind]) if (map.getLayer(`${L.id}-${s}`)) map.removeLayer(`${L.id}-${s}`);
  for (const src of [L.id, `${L.id}-lbl`, `${L.id}-ctr`]) if (map.getSource(src)) map.removeSource(src);
}

export function applyPaint(map, L, tone) {
  const o = L.opacity;
  const set = (s, prop, v) => map.setPaintProperty(`${L.id}-${s}`, prop, v);
  const contrast = tone === 'light' ? '#0b0f19' : '#ffffff';

  if (L.kind === 'points') {
    set('cluster', 'circle-color', L.color);
    set('cluster', 'circle-opacity', 0.92 * o);
    set('cluster', 'circle-stroke-color', L.color);
    set('cluster', 'circle-stroke-opacity', 0.28 * o);
    set('count', 'text-opacity', o);
    set('pt', 'circle-opacity', o);
    set('pt', 'circle-stroke-opacity', o);
    set('ring', 'circle-stroke-color', contrast);
    map.setLayoutProperty(`${L.id}-plbl`, 'text-field', ['to-string', ['coalesce', ['get', L.labelKey], '']]);
    for (const [k, v] of Object.entries(labelPaint(tone))) set('plbl', k, v);
    return;
  }

  const col = L.distinct ? ['get', '_c'] : L.color;
  set('fill', 'fill-color', col);
  set('fill', 'fill-opacity', ['case', selected, 0.5 * o, hovered, 0.36 * o, 0.2 * o]);
  set('glow', 'line-color', col);
  set('glow', 'line-opacity', ['case', selected, 0.7 * o, 0.3 * o]);
  set('line', 'line-color', ['case', selected, contrast, col]);
  set('line', 'line-opacity', o);
  set('pt', 'circle-color', col);
  set('pt', 'circle-opacity', o);
  set('halo', 'circle-color', L.color);
  set('halo', 'circle-opacity', 0.45 * o);
  set('dot', 'circle-color', L.color);
  set('dot', 'circle-opacity', o);
  for (const s of ['area-lbl', 'lbl']) for (const [k, v] of Object.entries(labelPaint(tone))) set(s, k, v);
}

export function applyVisibility(map, L, labelsOn) {
  for (const s of SUBLAYERS[L.kind]) {
    const on = L.visible && (!LABEL_SUBLAYERS.has(s) || (L.labels && labelsOn));
    map.setLayoutProperty(`${L.id}-${s}`, 'visibility', on ? 'visible' : 'none');
  }
}
