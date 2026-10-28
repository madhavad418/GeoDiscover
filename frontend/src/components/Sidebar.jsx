import Icon from './Icon.jsx';
import LayerCard from './LayerCard.jsx';
import { fmtArea, fmtNum } from '../lib/geo.js';

function Summary({ layers }) {
  if (!layers.length) return null;
  const count = (kind) => layers.filter((l) => l.kind === kind).reduce((s, l) => s + l.data.features.length, 0);
  const areas = count('shapes');
  const places = count('points');
  const area = layers.reduce((s, l) => s + l.totalArea, 0);
  const countries = new Set(layers.map((l) => l.iso).filter(Boolean)).size;
  return (
    <footer className="sidebar-foot">
      {areas > 0 && <span><b>{fmtNum(areas)}</b> areas · <b>{fmtArea(area)}</b></span>}
      {places > 0 && <span><b>{fmtNum(places)}</b> places</span>}
      {countries > 0 && <span><b>{countries}</b> countr{countries > 1 ? 'ies' : 'y'}</span>}
    </footer>
  );
}

export default function Sidebar({ layers, selected, dragging, allowUpload = true, onBrowse, onClose, onClearAll, layerHandlers }) {
  return (
    <aside className="panel sidebar">
      <button className="icon-btn only-mobile sidebar-close" onClick={onClose} aria-label="Close sidebar" title="Close sidebar"><Icon name="x" /></button>

      {allowUpload && <button className={`dropzone ${dragging ? 'over' : ''}`} onClick={onBrowse}>
        <span className="dz-icon"><Icon name="upload" size={18} /></span>
        <strong>Drop boundary files or <u>browse</u></strong>
        <span className="dz-hint">Boundaries: GeoJSON · Shapefile · .qmd<br />Places: CSV · Excel (.xlsx/.xls)</span>
      </button>}

      <div className="section-head">
        <span>Layers</span>
        <span className="badge">{layers.length}</span>
        <div className="spacer" />
        {layers.length > 0 && allowUpload && <button className="text-btn" onClick={onClearAll}>Clear all</button>}
      </div>

      <div className="layers">
        {layers.length === 0
          ? <div className="layers-empty">{allowUpload ? 'No layers yet. Add boundary files above.' : 'Loading layers…'}</div>
          : layers.map((L) => (
            <LayerCard
              key={L.id}
              layer={L}
              selectedFid={selected?.layerId === L.id ? selected.fid : -1}
              onUpdate={(patch) => layerHandlers.update(L.id, patch)}
              onZoom={() => layerHandlers.zoom(L.bbox)}
              onSelectFeature={(fid) => layerHandlers.select(L.id, fid, true)}
              onHoverFeature={(fid) => layerHandlers.hover(fid == null ? null : { layerId: L.id, fid })}
              onExport={() => layerHandlers.export(L)}
              onRemove={() => layerHandlers.remove(L.id)}
            />
          ))}
      </div>

      <Summary layers={layers} />
    </aside>
  );
}
