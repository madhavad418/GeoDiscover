import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import {
  Map as MapLibreMap, AttributionControl, ScaleControl, NavigationControl, FullscreenControl, setWorkerUrl,
} from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import 'maplibre-gl/dist/maplibre-gl.css';
import { BASEMAPS, buildStyle } from '../lib/mapStyle.js';
import { addToMap, removeFromMap, applyPaint, applyVisibility, applyPlaceFilter, INTERACTIVE_SUBLAYERS } from '../lib/mapLayers.js';
import { fmtArea, fmtCoord, fmtDist, lineLength, ringArea, plural } from '../lib/geo.js';
import MeasureHud from './MeasureHud.jsx';
import Loading from './Loading.jsx';

setWorkerUrl(workerUrl);

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sameTarget = (a, b) => a?.layerId === b?.layerId && a?.fid === b?.fid;
const MOBILE = 860;

function viewPadding(infoOpen) {
  const mobile = innerWidth <= MOBILE;
  const pad = {
    top: mobile ? 80 : 110,
    bottom: mobile && infoOpen ? innerHeight * 0.62 + 20 : 100, // room for overview labels under markers
    left: mobile ? 30 : 340 + 64,
    right: !mobile && infoOpen ? 370 + 64 : 60,
  };
  // Never let padding swallow the whole viewport.
  if (pad.left + pad.right > innerWidth - 80) pad.left = pad.right = 30;
  if (pad.top + pad.bottom > innerHeight - 80) pad.top = pad.bottom = 30;
  return pad;
}

const MapView = forwardRef(function MapView(props, ref) {
  const { layers, basemap, labelsOn, selected, hover, measuring, onExitMeasure } = props;
  const containerRef = useRef(null);
  const tooltipRef = useRef(null);
  const coordsRef = useRef(null);
  const zoomRef = useRef(null);
  const mapRef = useRef(null);
  const mountedRef = useRef(new Map());
  const appliedRef = useRef({ hover: null, selected: null });
  const propsRef = useRef(props);
  propsRef.current = props;

  const [ready, setReady] = useState(false);
  const [mapLoading, setMapLoading] = useState(true);
  const [mapError, setMapError] = useState(false);
  const [measure, setMeasure] = useState({ pts: [], done: false });
  const [cursor, setCursor] = useState(null);

  useImperativeHandle(ref, () => ({
    fitBbox(b) {
      const map = mapRef.current;
      if (!map || !b) return;
      const padding = viewPadding(!!propsRef.current.selected);
      // Always fitBounds: flyTo({ padding }) would leave that padding on the map permanently, and the
      // next fitBounds would add its padding on top ("Map cannot fit within canvas").
      const point = b[2] - b[0] < 1e-7 && b[3] - b[1] < 1e-7;
      const d = point ? 0.0004 : 0; // ~45 m box around a single place
      map.fitBounds([[b[0] - d, b[1] - d], [b[2] + d, b[3] + d]], {
        padding, maxZoom: 17, duration: point ? 1400 : 1500, essential: true,
      });
    },
    screenshot() {
      const map = mapRef.current;
      return new Promise((resolve) => {
        map.once('render', () => map.getCanvas().toBlob(resolve));
        map.triggerRepaint();
      });
    },
  }), []);

  /* ----- Create the map once ----- */
  useEffect(() => {
    const map = new MapLibreMap({
      container: containerRef.current,
      style: buildStyle(propsRef.current.basemap),
      center: [110, 6],
      zoom: 3.4,
      canvasContextAttributes: { preserveDrawingBuffer: true }, // lets "Save PNG" read the canvas
      attributionControl: false,
    });
    mapRef.current = map;
    map.addControl(new AttributionControl({ compact: true }), 'bottom-right');
    map.addControl(new ScaleControl({ maxWidth: 110 }), 'bottom-right');
    map.addControl(new NavigationControl({ visualizePitch: true }), 'bottom-right');
    // Fullscreen the map's whole view (toolbar, sidebar, overlays), not just the canvas.
    map.addControl(new FullscreenControl({ container: containerRef.current.parentElement }), 'bottom-right');

    map.on('dataloading', () => setMapLoading(true));
    map.on('idle', () => setMapLoading(false));
    map.on('error', () => { setMapLoading(false); setMapError(true); });
    map.on('load', () => {
      map.addSource('measure', { type: 'geojson', data: { type: 'FeatureCollection', features: [] } });
      map.addLayer({ id: 'measure-fill', type: 'fill', source: 'measure', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': '#E8C27A', 'fill-opacity': 0.12 } });
      map.addLayer({ id: 'measure-line', type: 'line', source: 'measure', filter: ['==', ['geometry-type'], 'LineString'], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#E8C27A', 'line-width': 2.5, 'line-dasharray': [2, 1.5] } });
      map.addLayer({ id: 'measure-pts', type: 'circle', source: 'measure', filter: ['==', ['geometry-type'], 'Point'], paint: { 'circle-radius': 5, 'circle-color': '#0a0d16', 'circle-stroke-color': '#E8C27A', 'circle-stroke-width': 2.5 } });
      setReady(true);
      propsRef.current.onReady?.();
    });
    map.on('error', (e) => console.warn('[map]', e.error?.message || e.type, e.error ?? ''));

    const hitTest = (point) => {
      const visible = propsRef.current.layers.filter((l) => l.visible);
      const ids = visible.flatMap((l) => INTERACTIVE_SUBLAYERS[l.kind].map((s) => `${l.id}-${s}`)).filter((id) => map.getLayer(id));
      if (!ids.length) return null;
      const f = map.queryRenderedFeatures(point, { layers: ids })[0];
      if (!f) return null;
      const L = visible.find((l) => f.layer.id.startsWith(`${l.id}-`));
      return L ? { L, role: f.layer.id.slice(L.id.length + 1), f } : null;
    };

    const tip = tooltipRef.current;
    const hideTip = () => tip.classList.remove('show');
    const showTip = (point, html) => {
      tip.innerHTML = html;
      tip.classList.add('show');
      const { width, height } = tip.getBoundingClientRect();
      let x = point.x + 16, y = point.y + 16;
      if (x + width > innerWidth - 8) x = point.x - width - 12;
      if (y + height > innerHeight - 8) y = point.y - height - 12;
      tip.style.transform = `translate(${x}px, ${y}px)`;
    };
    const emitHover = (target) => {
      if (!sameTarget(target, propsRef.current.hover)) propsRef.current.onHover(target);
    };

    map.on('mousemove', (e) => {
      coordsRef.current.textContent = fmtCoord(e.lngLat.lat, e.lngLat.lng);
      if (propsRef.current.measuring) {
        setCursor(e.lngLat.toArray());
        return;
      }
      const hit = hitTest(e.point);
      map.getCanvas().style.cursor = hit ? 'pointer' : '';
      if (!hit) { emitHover(null); hideTip(); return; }
      const { L, role, f } = hit;
      if (role === 'dot') {
        emitHover(null);
        showTip(e.point, `<strong>${esc(L.displayName)}</strong><span>${plural(L.data.features.length, L.geomLabel)} · ${fmtArea(L.totalArea)} · click to zoom</span>`);
      } else if (role === 'cluster') {
        emitHover(null);
        showTip(e.point, `<strong>${plural(f.properties.point_count, 'place')}</strong><span>${esc(L.displayName)} · click to expand</span>`);
      } else if (L.kind === 'points') {
        emitHover({ layerId: L.id, fid: f.id });
        const p = f.properties;
        const id = L.keys.id && p[L.keys.id];
        showTip(e.point, `<strong>${esc(p._name)}</strong><span><i class="tip-dot" style="background:${esc(p._cc)}"></i>${esc(p._cat)}</span>${id ? `<span class="tip-id">${esc(id)}</span>` : ''}`);
      } else {
        emitHover({ layerId: L.id, fid: f.id });
        const st = L.stats[f.id];
        showTip(e.point, `<strong>${esc(f.properties._name)}</strong><span>${st.area ? fmtArea(st.area) : fmtDist(st.perim)} · ${esc(L.title)}</span>`);
      }
    });
    map.getCanvas().addEventListener('mouseleave', () => { emitHover(null); hideTip(); });

    map.on('click', (e) => {
      const p = propsRef.current;
      if (p.measuring) {
        setMeasure((m) => {
          const pts = m.done ? [] : m.pts;
          const last = pts[pts.length - 1];
          // Skip the duplicate click that precedes a double-click.
          if (last) {
            const lp = map.project(last);
            if (Math.hypot(lp.x - e.point.x, lp.y - e.point.y) < 5) return m;
          }
          return { pts: [...pts, e.lngLat.toArray()], done: false };
        });
        return;
      }
      const hit = hitTest(e.point);
      if (!hit) p.onClearSelection();
      else if (hit.role === 'dot') p.onZoomTo(hit.L.bbox);
      else if (hit.role === 'cluster') {
        map.getSource(hit.L.id).getClusterExpansionZoom(hit.f.properties.cluster_id)
          .then((zoom) => map.easeTo({ center: hit.f.geometry.coordinates, zoom: zoom + 0.3, duration: 700 }))
          .catch(() => {});
      } else p.onSelect(hit.L.id, hit.f.id);
    });
    map.on('dblclick', (e) => {
      if (!propsRef.current.measuring) return;
      e.preventDefault();
      setMeasure((m) => ({ ...m, done: m.pts.length > 0 }));
    });
    // A tooltip left under a still cursor would describe whatever was there before the camera moved.
    map.on('movestart', hideTip);
    map.on('zoom', () => { zoomRef.current.textContent = `z ${map.getZoom().toFixed(1)}`; });

    return () => {
      map.remove();
      mapRef.current = null;
      mountedRef.current = new Map();
      appliedRef.current = { hover: null, selected: null };
      setReady(false);
    };
  }, []);

  /* ----- Sync data layers ----- */
  useEffect(() => {
    const map = mapRef.current;
    if (!ready) return;
    const tone = BASEMAPS[basemap].tone;
    const ids = new Set(layers.map((l) => l.id));
    // mounted: id -> the layer object as last synced (used to detect filter changes)
    for (const [id, prev] of mountedRef.current) {
      if (!ids.has(id)) { removeFromMap(map, prev); mountedRef.current.delete(id); }
    }
    for (const L of layers) {
      const prev = mountedRef.current.get(L.id);
      if (!prev) addToMap(map, L);
      else if (L.kind === 'points' && prev.hiddenCats !== L.hiddenCats) applyPlaceFilter(map, L);
      mountedRef.current.set(L.id, L);
      applyPaint(map, L, tone);
      applyVisibility(map, L, labelsOn);
    }
  }, [ready, layers, basemap, labelsOn]);

  /* ----- Basemap ----- */
  useEffect(() => {
    const map = mapRef.current;
    if (!ready) return;
    for (const [k, b] of Object.entries(BASEMAPS)) {
      b.sources.forEach((_, i) => map.setLayoutProperty(`bm-${k}-${i}`, 'visibility', k === basemap ? 'visible' : 'none'));
    }
    map.setPaintProperty('bg', 'background-color', BASEMAPS[basemap].bg);
  }, [ready, basemap]);

  /* ----- Hover & selection feature-state ----- */
  useEffect(() => {
    if (!ready) return;
    const map = mapRef.current;
    for (const [key, target] of [['hover', hover], ['selected', selected]]) {
      const prev = appliedRef.current[key];
      if (sameTarget(prev, target)) continue;
      if (prev && map.getSource(prev.layerId)) map.setFeatureState({ source: prev.layerId, id: prev.fid }, { [key]: false });
      if (target && map.getSource(target.layerId)) map.setFeatureState({ source: target.layerId, id: target.fid }, { [key]: true });
      appliedRef.current[key] = target;
    }
  }, [ready, hover, selected, layers]);

  /* ----- Measure tool ----- */
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (measuring) {
      map.doubleClickZoom.disable();
      map.getCanvas().style.cursor = 'crosshair';
      tooltipRef.current.classList.remove('show');
    } else {
      map.doubleClickZoom.enable();
      map.getCanvas().style.cursor = '';
      setMeasure({ pts: [], done: false });
      setCursor(null);
    }
  }, [measuring]);

  const path = measuring && cursor && measure.pts.length && !measure.done ? [...measure.pts, cursor] : measure.pts;
  useEffect(() => {
    const src = ready && mapRef.current.getSource('measure');
    if (!src) return;
    const features = [];
    if (path.length >= 3) features.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [[...path, path[0]]] } });
    if (path.length >= 2) features.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: path } });
    measure.pts.forEach((c) => features.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: c } }));
    src.setData({ type: 'FeatureCollection', features });
  });

  return (
    <>
      <div id="map" ref={containerRef} />
      {measuring && (
        <MeasureHud
          distance={fmtDist(lineLength(path))}
          area={path.length >= 3 ? fmtArea(ringArea([...path, path[0]])) : '—'}
          points={measure.pts.length}
          onUndo={() => setMeasure((m) => ({ pts: m.pts.slice(0, -1), done: false }))}
          onClear={() => setMeasure({ pts: [], done: false })}
          onClose={onExitMeasure}
        />
      )}
      <div className="status">
        <span ref={coordsRef}>Move over the map</span>
        {mapLoading ? <Loading size={12}>Loading map…</Loading> : mapError ? <span role="status">Some map resources could not load</span> : null}
        <span className="sep" />
        <span ref={zoomRef}>z 3.4</span>
      </div>
      <div className="tooltip" ref={tooltipRef} />
    </>
  );
});

export default MapView;
