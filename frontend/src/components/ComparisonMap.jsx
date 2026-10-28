import { useMemo } from 'react';
import AoiViewer from '../AoiViewer.jsx';
import Icon from './Icon.jsx';
import { api } from '../lib/api.js';
import { readFiles } from '../lib/loaders.js';
import { buildPointLayer, detectKeys } from '../lib/places.js';

// Same order as the details panel lists them.
const FIELDS = ['name', 'list', 'category', 'here_place_id', 'address', 'phone', 'mobile', 'website', 'opening_hours',
  'found_in', 'changed', 'delete_basis', 'distance_m', 'possible_here_matches', 'why', 'latitude', 'longitude'];

/** One points layer per list (New, Update...), every point in that list's colour; category filters still apply. */
function kindLayer(kind, meta, features) {
  const pts = features.map((f) => ({ ...f, properties: { ...f.properties, latitude: f.geometry.coordinates[1], longitude: f.geometry.coordinates[0] } }));
  const layer = buildPointLayer({ fileName: `${kind}.geojson`, base: `comparison-${kind}`, title: meta.label, iso: '', fields: FIELDS,
    keys: { ...detectKeys(FIELDS), cat: 'category', id: 'here_place_id' }, features: pts, source: 'HERE vs Google/Grab comparison' });
  layer.data.features.forEach((f) => { f.properties._cc = meta.color; });
  return { ...layer, id: `kind-${kind}`, kindKey: kind, color: meta.color, labels: false, categories: layer.categories.map((c) => ({ ...c, color: meta.color })) };
}

/** Full-page AOI-viewer map of a comparison: AOI boundary + one layer per list, legend toggles that stay on the map in fullscreen. */
export default function ComparisonMap({ base, aoi, title, kinds, onClose }) {
  const preset = useMemo(() => ({
    message: 'Loading comparison map…',
    async load(signal) {
      const [geo, boundary] = await Promise.all([
        api(`${base}/map`, { signal }),
        api(`/sources/aois/${encodeURIComponent(aoi)}/boundary`, { signal }).catch((e) => { if (e.name === 'AbortError') throw e; return null; }),
      ]);
      const layers = [];
      if (boundary) {
        const parsed = await readFiles([{ name: `${boundary.name || aoi}.geojson`, text: async () => JSON.stringify(boundary) }], () => {});
        if (parsed.layers[0]) layers.push({ ...parsed.layers[0], id: 'aoi', title: `${aoi} boundary`, displayName: `${aoi} boundary`, color: '#71bfff', labels: false, distinct: false });
      }
      for (const [kind, meta] of Object.entries(kinds)) {
        const features = geo.features.filter((f) => f.properties.kind === kind);
        if (features.length) layers.push(kindLayer(kind, meta, features));
      }
      if (layers.length) layers[layers.length > 1 ? 1 : 0] = { ...layers[layers.length > 1 ? 1 : 0], expanded: true };
      return layers;
    },
  }), [base, aoi, kinds]);

  const overlay = (layers, update) => {
    const lists = layers.filter((l) => l.kindKey);
    return <div className="panel compare-legend" role="group" aria-label="Comparison lists">
      <div className="compare-legend-head"><strong>{title}</strong><button className="ws-button" onClick={onClose}><Icon name="x" size={14} />Close map</button></div>
      {lists.length === 0 ? <small>Loading…</small> : lists.map((l) => <label key={l.id}>
        <input type="checkbox" checked={l.visible} onChange={() => update(l.id, { visible: !l.visible })} />
        <i style={{ background: l.color }} />{l.title}<small>{l.data.features.length.toLocaleString()}</small></label>)}
    </div>;
  };
  return <div className="viewer-shell compare-map-shell"><AoiViewer preset={preset} uploads={false} overlay={overlay} /></div>;
}
