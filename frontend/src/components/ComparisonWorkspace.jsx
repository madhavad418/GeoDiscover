import { useEffect, useMemo, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import Loading from './Loading.jsx';
import MapView from './MapView.jsx';
import Toasts, { useToasts } from './Toasts.jsx';
import { detectKeys, buildPointLayer } from '../lib/places.js';
import { download, readFiles } from '../lib/loaders.js';
import { api } from '../lib/api.js';

const ACTION_COLOR = { new: '#5fd39a', update: '#e8c27a', delete: '#ff6b8b' };
const ACTION_LABEL = { new: 'New', update: 'Update', delete: 'Delete' };
const FIELD_NAMES = ['placeid', 'name1', 'primarycategory', 'primarycategorynm', 'displaylatitude', 'displaylongitude', 'upaddress'];

function makeProviderLayer(provider, proposals) {
  const features = proposals.flatMap((proposal, index) => {
    const place = proposal.action === 'delete' ? proposal.base : proposal.proposed;
    if (!place || place.latitude == null || place.longitude == null) return [];
    return [{
      type: 'Feature',
      id: index,
      properties: {
        placeid: place.place_id || proposal.key,
        name1: place.name || 'Unnamed place',
        primarycategory: place.category_code || '',
        primarycategorynm: place.category_name || '',
        displaylatitude: place.latitude,
        displaylongitude: place.longitude,
        upaddress: place.address || '',
        _comparison_key: proposal.key,
        _comparison_action: proposal.action,
      },
      geometry: { type: 'Point', coordinates: [place.longitude, place.latitude] },
    }];
  });
  if (!features.length) return null;
  const layer = buildPointLayer({
    fileName: `${provider.name} demo proposals`,
    base: `demo-${provider.id}`,
    title: `${provider.name} · DEMO`,
    iso: '',
    fields: FIELD_NAMES,
    keys: detectKeys(FIELD_NAMES),
    features,
    source: 'Simulated provider proposals',
  });
  layer.id = `compare-${provider.id}`;
  layer.title = `${provider.name} · DEMO`;
  layer.displayName = layer.title;
  layer.color = provider.color;
  layer.labels = false;
  layer.expanded = false;
  for (const feature of layer.data.features) {
    const action = feature.properties._comparison_action;
    feature.properties._cat = ACTION_LABEL[action];
    feature.properties._cc = ACTION_COLOR[action];
  }
  return layer;
}

function ReviewCard({ provider, proposal, busy, onReview, onShow }) {
  const place = proposal.action === 'delete' ? proposal.base : proposal.proposed;
  const base = proposal.base;
  return (
    <article className={`comparison-card ${proposal.review_status}`} style={{ '--action-color': ACTION_COLOR[proposal.action] }}>
      <div className="comparison-card-head">
        <span className={`change-badge ${proposal.action}`}>{ACTION_LABEL[proposal.action]}</span>
        <span className="comparison-provider">{provider.name}</span>
        <span className={`review-badge ${proposal.review_status}`}>{proposal.review_status}</span>
      </div>
      <h3>{place?.name || 'Unnamed place'}</h3>
      {proposal.action === 'update' && (
        <div className="comparison-diff"><span>{base?.name}</span><b aria-hidden="true">→</b><strong>{proposal.proposed?.name}</strong></div>
      )}
      {proposal.action === 'delete' && <p className="comparison-reason">Proposed removal from {provider.name}; HERE baseline record stays unchanged unless approved.</p>}
      {proposal.action === 'new' && <p className="comparison-reason">No confident HERE match. Review before adding to the delivery.</p>}
      <p className="comparison-match">
        {proposal.action === 'new'
          ? 'No HERE match'
          : `${proposal.match_method === 'place_id' ? 'Matched by HERE place ID' : 'Matched by name and location'} · ${Math.round(proposal.match_confidence * 100)}%`}
      </p>
      {proposal.changed_fields?.length > 0 && <p className="comparison-fields">Changed: {proposal.changed_fields.join(', ')}</p>}
      <div className="comparison-card-actions">
        <button className="ws-link" type="button" onClick={() => onShow(proposal)}><Icon name="target" size={13} />Show on map</button>
        <span className="comparison-action-spacer" />
        {proposal.review_status !== 'approved' && <button className="review-action approve" type="button" disabled={busy} onClick={() => onReview(proposal, 'approved')}>{busy ? 'Saving…' : 'Approve'}</button>}
        {proposal.review_status !== 'rejected' && <button className="review-action reject" type="button" disabled={busy} onClick={() => onReview(proposal, 'rejected')}>{busy ? 'Saving…' : 'Reject'}</button>}
        {proposal.review_status !== 'pending' && <button className="review-action reset" type="button" disabled={busy} onClick={() => onReview(proposal, 'pending')}>Reset</button>}
      </div>
      {proposal.review_note && <p className="review-note">Reviewer note: {proposal.review_note}</p>}
    </article>
  );
}

export default function ComparisonWorkspace({ datasets, datasetId, onDatasetChange, onBack }) {
  const [selectedDatasetId, setSelectedDatasetId] = useState(datasetId || datasets[0]?.id || '');
  const [comparison, setComparison] = useState(null);
  const [layers, setLayers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [hover, setHover] = useState(null);
  const [providerFilter, setProviderFilter] = useState('all');
  const [actionFilter, setActionFilter] = useState('all');
  const [loading, setLoading] = useState(false);
  const [savingKey, setSavingKey] = useState('');
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [reloadToken, setReloadToken] = useState(0);
  const [toasts, toast] = useToasts();
  const mapRef = useRef(null);
  const mapReady = useRef(false);
  const pendingBbox = useRef(null);

  useEffect(() => {
    if (datasetId && datasetId !== selectedDatasetId) setSelectedDatasetId(datasetId);
  }, [datasetId, selectedDatasetId]);
  useEffect(() => {
    if (!selectedDatasetId && datasets.length) setSelectedDatasetId(datasets[0].id);
  }, [datasets, selectedDatasetId]);

  useEffect(() => {
    if (!selectedDatasetId) {
      setComparison(null);
      setLayers([]);
      return undefined;
    }
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setComparison(null);
    setLayers([]);
    setSelected(null);
    Promise.all([
      api(`/customer-data/datasets/${encodeURIComponent(selectedDatasetId)}/comparison`, { signal: controller.signal }),
      fetch(`/api/customer-data/datasets/${encodeURIComponent(selectedDatasetId)}/geojson`, { signal: controller.signal }),
    ]).then(async ([data, geoResponse]) => {
      if (!geoResponse.ok) throw new Error('Could not load the HERE baseline map data.');
      const geojson = await geoResponse.json();
      const notices = [];
      const parsed = await readFiles([{
        name: `${data.dataset.aoi}_${data.dataset.country}_HERE.geojson`,
        text: async () => JSON.stringify(geojson),
      }], (message, type) => notices.push({ message, type }));
      const base = parsed.layers[0];
      if (!base) throw new Error(notices.find((notice) => notice.type === 'error')?.message || 'The HERE dataset contains no map-ready POIs.');
      base.id = 'compare-here';
      base.title = `HERE · ${data.dataset.aoi}`;
      base.displayName = base.title;
      base.color = '#a9b1c4';
      base.labels = false;
      base.expanded = false;
      const providerLayers = data.providers.map((provider) => makeProviderLayer(provider, provider.proposals)).filter(Boolean);
      if (controller.signal.aborted) return;
      setComparison(data);
      setLayers([base, ...providerLayers]);
      const allCoordinates = [base, ...providerLayers].flatMap((layer) => layer.bbox ? [layer.bbox] : []);
      const b = allCoordinates.reduce((bounds, item) => [
        Math.min(bounds[0], item[0]), Math.min(bounds[1], item[1]),
        Math.max(bounds[2], item[2]), Math.max(bounds[3], item[3]),
      ], [Infinity, Infinity, -Infinity, -Infinity]);
      pendingBbox.current = Number.isFinite(b[0]) ? b : null;
    }).catch((cause) => {
      if (cause.name !== 'AbortError') setError(cause.message);
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [selectedDatasetId, reloadToken]);

  useEffect(() => {
    if (mapReady.current && pendingBbox.current) {
      mapRef.current?.fitBbox(pendingBbox.current);
      pendingBbox.current = null;
    }
  }, [layers]);

  const proposals = useMemo(() => (comparison?.providers || [])
    .filter((provider) => providerFilter === 'all' || provider.id === providerFilter)
    .flatMap((provider) => provider.proposals.map((proposal) => ({ provider, proposal })))
    .filter(({ proposal }) => actionFilter === 'all' || proposal.action === actionFilter), [comparison, providerFilter, actionFilter]);
  const totals = useMemo(() => {
    const all = (comparison?.providers || []).flatMap((provider) => provider.proposals);
    return {
      new: all.filter((item) => item.action === 'new').length,
      update: all.filter((item) => item.action === 'update').length,
      delete: all.filter((item) => item.action === 'delete').length,
      approved: all.filter((item) => item.review_status === 'approved').length,
    };
  }, [comparison]);

  function changeDataset(id) {
    setSelectedDatasetId(id);
    setProviderFilter('all');
    setActionFilter('all');
    onDatasetChange(id);
  }

  function toggleLayer(id) {
    setLayers((current) => current.map((layer) => layer.id === id ? { ...layer, visible: !layer.visible } : layer));
  }

  function selectFeature(target) {
    setSelected(target);
    if (target) {
      const layer = layers.find((item) => item.id === target.layerId);
      const feature = layer?.data.features[target.fid];
      if (feature) mapRef.current?.fitBbox([
        feature.geometry.coordinates[0], feature.geometry.coordinates[1],
        feature.geometry.coordinates[0], feature.geometry.coordinates[1],
      ]);
    }
  }

  function showProposal(provider, proposal) {
    const layer = layers.find((item) => item.id === `compare-${provider.id}`);
    const feature = layer?.data.features.find((item) => item.properties._comparison_key === proposal.key);
    if (!layer || !feature) return;
    setSelected({ layerId: layer.id, fid: feature.id });
    mapRef.current?.fitBbox([
      feature.geometry.coordinates[0], feature.geometry.coordinates[1],
      feature.geometry.coordinates[0], feature.geometry.coordinates[1],
    ]);
  }

  async function reviewProposal(provider, proposal, status) {
    const busyKey = `${provider.id}:${proposal.key}`;
    setSavingKey(busyKey);
    try {
      const saved = await api(
        `/customer-data/datasets/${encodeURIComponent(selectedDatasetId)}/comparison/${provider.id}/${proposal.key}`,
        { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) },
      );
      setComparison((current) => ({
        ...current,
        providers: current.providers.map((item) => item.id !== provider.id ? item : {
          ...item,
          proposals: item.proposals.map((candidate) => candidate.key !== proposal.key ? candidate : {
            ...candidate, review_status: saved.status, review_note: saved.note, reviewed_at: saved.updated_at,
          }),
        }),
      }));
      toast(`${ACTION_LABEL[proposal.action]} marked ${saved.status}.`);
    } catch (cause) {
      toast(cause.message, 'error');
    } finally {
      setSavingKey('');
    }
  }

  async function exportDelivery() {
    setExporting(true);
    try {
      const response = await fetch(`/api/customer-data/datasets/${encodeURIComponent(selectedDatasetId)}/comparison/delivery.csv`);
      if (!response.ok) throw new Error('Could not export approved decisions.');
      // download() appends the link and revokes the URL later; revoking right after click() can cancel it.
      download(await response.blob(), `${comparison.dataset.aoi.toLowerCase().replace(/\s+/g, '-')}-poi-decisions.csv`);
      toast(`Exported ${totals.approved} approved decision${totals.approved === 1 ? '' : 's'}.`);
    } catch (cause) {
      toast(cause.message, 'error');
    } finally {
      setExporting(false);
    }
  }

  const activeDataset = datasets.find((dataset) => dataset.id === selectedDatasetId);
  const canExport = totals.approved > 0;

  return (
    <>
      <MapView
        ref={mapRef}
        layers={layers}
        basemap="dark"
        labelsOn={false}
        selected={selected}
        hover={hover}
        measuring={false}
        onHover={setHover}
        onSelect={(layerId, fid) => selectFeature({ layerId, fid })}
        onClearSelection={() => selectFeature(null)}
        onZoomTo={(bbox) => mapRef.current?.fitBbox(bbox)}
        onExitMeasure={() => {}}
        onReady={() => {
          mapReady.current = true;
          if (pendingBbox.current) {
            mapRef.current?.fitBbox(pendingBbox.current);
            pendingBbox.current = null;
          }
        }}
      />

      <div className="compare-toolbar panel">
        <div className="compare-title"><span className="metric-icon"><Icon name="layers" /></span><div><strong>POI comparison</strong><small>{activeDataset ? `${activeDataset.aoi} · HERE baseline` : 'Select a baseline'}</small></div></div>
        <label className="compare-dataset-select">HERE baseline
          <select aria-label="HERE baseline dataset" value={selectedDatasetId} onChange={(event) => changeDataset(event.target.value)} disabled={!datasets.length}>
            {datasets.map((dataset) => <option key={dataset.id} value={dataset.id}>{dataset.aoi} · {dataset.filename}</option>)}
          </select>
        </label>
        <div className="compare-map-layers" aria-label="Map layers">
          {layers.map((layer) => (
            <label key={layer.id} title={layer.title}>
              <input type="checkbox" checked={layer.visible !== false} onChange={() => toggleLayer(layer.id)} />
              <i style={{ '--layer-color': layer.kind === 'points' && layer.id !== 'compare-here' ? layer.color : '#a9b1c4' }} />
              {layer.id === 'compare-here' ? 'HERE' : layer.title.replace(' · DEMO', '')}
            </label>
          ))}
        </div>
      </div>

      <aside className="compare-panel panel" aria-label="Comparison proposals">
        <header className="compare-panel-heading">
          <div><span className="demo-label">SIMULATED PROVIDER DATA</span><h2>Review changes</h2></div>
          <button className="icon-btn" type="button" title="Return to Customer Data" aria-label="Return to Customer Data" onClick={onBack}><Icon name="x" /></button>
        </header>
        <div className="compare-warning">Google Maps, Apple Maps, and Grab Maps records below are demo examples—not live provider data.</div>
        <div className="compare-counts" aria-label="Comparison counts">
          {Object.entries(ACTION_LABEL).map(([action, label]) => (
            <button type="button" key={action} className={`compare-count ${action} ${actionFilter === action ? 'active' : ''}`} onClick={() => setActionFilter(actionFilter === action ? 'all' : action)}>
              <strong>{totals[action]}</strong><span>{label}</span>
            </button>
          ))}
        </div>
        <div className="compare-filters" role="tablist" aria-label="Provider filter">
          {[['all', 'All'], ['google', 'Google'], ['apple', 'Apple'], ['grab', 'Grab']].map(([id, label]) => (
            <button type="button" role="tab" aria-selected={providerFilter === id} className={providerFilter === id ? 'active' : ''} key={id} onClick={() => setProviderFilter(id)}>{label}</button>
          ))}
        </div>
        <div className="compare-list" aria-live="polite">
          {loading && <div className="compare-state"><Loading>Comparing HERE with demo sources…</Loading></div>}
          {error && <div className="compare-state error" role="alert">{error}<button type="button" className="ws-link" onClick={() => setReloadToken((current) => current + 1)}>Retry</button></div>}
          {!loading && !error && !datasets.length && <div className="compare-state">Import a HERE baseline before starting a comparison.</div>}
          {!loading && !error && datasets.length > 0 && proposals.length === 0 && <div className="compare-state">No proposals match these filters.</div>}
          {!loading && proposals.map(({ provider, proposal }) => (
            <ReviewCard
              key={`${provider.id}:${proposal.key}`}
              provider={provider}
              proposal={proposal}
              busy={savingKey === `${provider.id}:${proposal.key}`}
              onReview={(item, status) => reviewProposal(provider, item, status)}
              onShow={(item) => showProposal(provider, item)}
            />
          ))}
        </div>
        <footer className="compare-panel-footer">
          <span>{totals.approved} approved · {totals.new + totals.update + totals.delete} demo proposals</span>
          <button type="button" className="ws-button primary" disabled={!canExport || exporting || loading} onClick={exportDelivery}>
            <Icon name="download" size={14} />{exporting ? 'Exporting…' : 'Export approved'}
          </button>
        </footer>
      </aside>
      <Toasts toasts={toasts} />
    </>
  );
}
