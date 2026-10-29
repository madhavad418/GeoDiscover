import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import Loading from './Loading.jsx';
import MapView from './MapView.jsx';
import { Signals } from './ComparisonDashboard.jsx';
import { api } from '../lib/api.js';
import { readFiles } from '../lib/loaders.js';
import { buildPointLayer, detectKeys } from '../lib/places.js';
import { mergeBbox } from '../lib/geo.js';
import { OUTCOMES } from '../lib/platform.js';

const FIELDS = ['result_id', 'name', 'category', 'here_place_id', 'jsan_id', 'latitude', 'longitude'];

/** A points layer whose "category" is the comparison outcome, coloured with the outcome palette. */
function pointLayer(id, title, features, colorFor, labelFor) {
  if (!features.length) return null;
  features.forEach((f) => { f.properties.category = labelFor(f); });
  const layer = buildPointLayer({ fileName: title, base: id, title, iso: '', fields: FIELDS, keys: detectKeys(FIELDS), features, source: 'Comparison run' });
  const colors = new Map(layer.data.features.map((f) => [f.properties._cat, colorFor(f)]));
  layer.data.features.forEach((f) => { f.properties._cc = colors.get(f.properties._cat); });
  layer.categories = layer.categories.map((c) => ({ ...c, color: colors.get(c.name) }));
  return { ...layer, id, title, displayName: title, color: '#a9b1c4', labels: false, expanded: false };
}

export default function ResultsMap({ runId, onBack }) {
  const [run, setRun] = useState(null);
  const [layers, setLayers] = useState([]);
  const [hidden, setHidden] = useState([]);
  const [selected, setSelected] = useState(null);
  const [hover, setHover] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const mapRef = useRef(null);
  const pending = useRef(null);

  useEffect(() => {
    const c = new AbortController();
    (async () => {
      try {
        const r = await api(`/comparison/runs/${runId}`, { signal: c.signal });
        const [map, boundary] = await Promise.all([api(`/comparison/runs/${runId}/map`, { signal: c.signal }),
          api(`/sources/aois/${encodeURIComponent(r.aoi)}/boundary`, { signal: c.signal })]);
        const parsed = await readFiles([{ name: `${boundary.name}.geojson`, text: async () => JSON.stringify(boundary) }], () => {});
        const aoiLayer = parsed.layers[0] && { ...parsed.layers[0], id: 'aoi', color: '#71bfff', distinct: false, labels: false, expanded: false };
        const toPoint = (f, lat, lon) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] },
          properties: { ...f.properties, latitude: lat, longitude: lon } });
        const discovered = map.features.map((f) => toPoint(f, f.geometry.coordinates[1], f.geometry.coordinates[0]));
        const herePositions = map.features.filter((f) => f.properties.here_lat != null && f.properties.outcome !== 'verification_required')
          .map((f) => toPoint(f, f.properties.here_lat, f.properties.here_lon));
        const results = pointLayer('results', 'Discovered / proposed', discovered, (f) => OUTCOMES[f.properties.outcome].color, (f) => OUTCOMES[f.properties.outcome].label);
        const here = pointLayer('here', 'HERE position of matched records', herePositions, () => '#c9d2dc', () => 'HERE position');
        const all = [aoiLayer, here, results].filter(Boolean);
        setRun(r);
        setLayers(all);
        pending.current = mergeBbox(all.map((l) => l.bbox));
        if (mapRef.current) { mapRef.current.fitBbox(pending.current); pending.current = null; }
      } catch (e) {
        if (e.name !== 'AbortError') setError(e.message);
      }
    })();
    return () => c.abort();
  }, [runId]);

  const shown = useMemo(() => layers.map((l) => (l.id === 'results' ? { ...l, hiddenCats: hidden } : l)), [layers, hidden]);

  function select(layerId, fid) {
    const layer = layers.find((l) => l.id === layerId);
    const f = layer?.data.features[fid];
    if (!f?.properties.result_id) return;
    setSelected({ layerId, fid });
    setDetail(null);
    api(`/comparison/results/${f.properties.result_id}`).then(setDetail).catch((e) => setError(e.message));
  }

  const counts = run?.stats.outcomes || {};
  return (
    <>
      <MapView ref={mapRef} layers={shown} basemap="light" labelsOn={false} selected={selected} hover={hover} measuring={false}
        onHover={setHover} onSelect={select} onClearSelection={() => { setSelected(null); setDetail(null); }}
        onZoomTo={(b) => mapRef.current?.fitBbox(b)} onExitMeasure={() => {}}
        onReady={() => { if (pending.current) { mapRef.current?.fitBbox(pending.current); pending.current = null; } }} />
      <div className="compare-toolbar panel">
        <div className="compare-title"><span className="metric-icon"><Icon name="map" /></span><div><strong>Comparison map</strong>
          <small>{run ? `${run.aoi} · ${run.stats.masters} discovered POIs · ${run.stats.here_records} HERE` : 'Loading…'}</small></div></div>
        <div className="outcome-toggles">{Object.entries(OUTCOMES).map(([k, o]) => (
          <label key={k}><input type="checkbox" checked={!hidden.includes(o.label)}
            onChange={() => setHidden((h) => (h.includes(o.label) ? h.filter((x) => x !== o.label) : [...h, o.label]))} />
            <i style={{ background: o.color }} />{o.label} <small>{counts[k] || 0}</small></label>))}
          <span className="legend-note"><i style={{ background: '#c9d2dc' }} />HERE position of matched records</span></div>
        <button className="ws-button" onClick={onBack}><Icon name="x" />Close map</button>
      </div>
      {error && <div className="viewer-loading" role="alert">{error}</div>}
      {!run && !error && <div className="viewer-loading"><Loading size={16}>Loading comparison map…</Loading></div>}
      {(detail || selected) && (
        <aside className="compare-panel panel" aria-label="Result details">
          <header className="compare-panel-heading"><div><span className="demo-label">{detail?.label || 'Loading…'}</span>
            <h2>{detail?.master_name || detail?.here_name || '…'}</h2></div>
            <button className="icon-btn" onClick={() => { setSelected(null); setDetail(null); }} aria-label="Close"><Icon name="x" /></button></header>
          {!detail ? <Loading>Loading…</Loading> : <div className="compare-list">
            <ul className="reason-list">{detail.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <dl className="kv-list"><dt>HERE</dt><dd>{detail.here_place_id || '—'} {detail.here_name ? `· ${detail.here_name}` : ''}</dd>
              <dt>JSAN</dt><dd>{detail.jsan_id || '—'}</dd><dt>Sources</dt><dd>{detail.sources.join(', ') || '—'}</dd>
              <dt>Distance</dt><dd>{detail.distance_m != null ? `${detail.distance_m} m (${detail.band}) · rule ${detail.decision_rule}` : '—'}</dd></dl>
            {detail.explanation.match && <Signals s={detail.explanation.match} />}
            {detail.changed_fields.length > 0 && <p>Changed: {detail.changed_fields.join(', ')}</p>}
          </div>}
        </aside>)}
    </>
  );
}
