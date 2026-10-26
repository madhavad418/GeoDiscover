import { useMemo, useState } from 'react';
import Icon from './Icon.jsx';
import { collator, fmtArea, fmtNum, plural } from '../lib/geo.js';

const TOP_CATEGORIES = 12;

function BoundaryBody({ layer: L, selectedFid, onUpdate, onSelectFeature, onHoverFeature }) {
  const n = L.data.features.length;
  const crs = L.meta.qmdCrs || L.meta.crs;
  const order = useMemo(
    () => L.data.features.map((_, i) => i).sort((a, b) => collator.compare(L.data.features[a].properties._name, L.data.features[b].properties._name)),
    [L.data],
  );
  return (
    <>
      <div className="chips">
        {n > 1 && <button className={`chip ${L.distinct ? 'on' : ''}`} onClick={() => onUpdate({ distinct: !L.distinct })}>Distinct colours</button>}
        <button className={`chip ${L.labels ? 'on' : ''}`} onClick={() => onUpdate({ labels: !L.labels })}>Labels</button>
      </div>
      {(crs || L.meta.source) && (
        <div className="crs-line">
          {crs && <>CRS <code>{crs}</code></>}
          {L.meta.source && <span>{L.meta.source}</span>}
          {L.meta.qmdCrs && <span>· via .qmd</span>}
        </div>
      )}
      {n > 1 && (
        <div className="feat-list" onMouseLeave={() => onHoverFeature(null)}>
          {order.map((i) => {
            const f = L.data.features[i];
            return (
              <button key={i} className={`feat ${i === selectedFid ? 'active' : ''}`} onClick={() => onSelectFeature(i)} onMouseEnter={() => onHoverFeature(i)}>
                <i style={{ background: L.distinct ? f.properties._c : L.color }} />
                <span>{f.properties._name}</span>
                <em>{L.stats[i].area ? fmtArea(L.stats[i].area) : ''}</em>
              </button>
            );
          })}
        </div>
      )}
    </>
  );
}

function PlacesBody({ layer: L, onUpdate }) {
  const [query, setQuery] = useState('');
  const [showAll, setShowAll] = useState(false);
  const hidden = useMemo(() => new Set(L.hiddenCats), [L.hiddenCats]);
  const q = query.trim().toLowerCase();
  const matching = q ? L.categories.filter((c) => c.name.toLowerCase().includes(q)) : L.categories;
  const list = q || showAll ? matching : matching.slice(0, TOP_CATEGORIES);

  const toggle = (name) => onUpdate({ hiddenCats: hidden.has(name) ? L.hiddenCats.filter((c) => c !== name) : [...L.hiddenCats, name] });
  // "Only" / "All" / "None" act on the categories currently matching the search box.
  const setShown = (names) => {
    const target = new Set(names);
    const scope = new Set(matching.map((c) => c.name));
    onUpdate({ hiddenCats: L.categories.filter((c) => (scope.has(c.name) ? !target.has(c.name) : hidden.has(c.name))).map((c) => c.name) });
  };

  return (
    <>
      <div className="chips">
        <button className={`chip ${L.labels ? 'on' : ''}`} onClick={() => onUpdate({ labels: !L.labels })}>Labels</button>
      </div>
      <div className="row">
        <label>Label by</label>
        <select className="select" value={L.labelKey} onChange={(e) => onUpdate({ labelKey: e.target.value })}>
          {L.fields.map((f) => <option key={f} value={f}>{f}{f === L.keys.id ? ' (identifier)' : f === L.keys.name ? ' (name)' : ''}</option>)}
        </select>
      </div>
      <div className="crs-line">
        {L.meta.source && <span>{L.meta.source}</span>}
        <span>· lat/lon <code>{L.keys.lat}</code> <code>{L.keys.lon}</code></span>
      </div>

      <div className="cat-head">
        <span>Categories · {fmtNum(L.categories.length)}</span>
        <div className="spacer" />
        <button className="text-btn" onClick={() => setShown(matching.map((c) => c.name))}>All</button>
        <button className="text-btn" onClick={() => setShown([])}>None</button>
      </div>
      <input className="cat-search" type="search" placeholder="Filter categories…" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="feat-list cats">
        {list.map((c) => (
          <div key={c.name} className={`cat ${hidden.has(c.name) ? 'off' : ''}`}>
            <button className="cat-toggle" onClick={() => toggle(c.name)} title={hidden.has(c.name) ? 'Show' : 'Hide'}>
              <i style={{ background: c.color }} />
              <span>{c.name}</span>
              <em>{fmtNum(c.count)}</em>
            </button>
            <button className="cat-only" onClick={() => setShown([c.name])} title="Show only this category">only</button>
          </div>
        ))}
        {list.length === 0 && <div className="sr-empty">No categories match</div>}
      </div>
      {!q && L.categories.length > TOP_CATEGORIES && (
        <button className="text-btn more" onClick={() => setShowAll(!showAll)}>
          {showAll ? 'Show top categories' : `Show all ${L.categories.length} categories`}
        </button>
      )}
    </>
  );
}

export default function LayerCard(props) {
  const { layer: L, onUpdate, onZoom, onExport, onRemove, onSelectFeature } = props;
  const n = L.data.features.length;
  const pct = Math.round(L.opacity * 100);
  const isPlaces = L.kind === 'points';
  const shown = isPlaces ? n - L.categories.filter((c) => L.hiddenCats.includes(c.name)).reduce((s, c) => s + c.count, 0) : n;
  const meta = isPlaces
    ? `${shown < n ? `${fmtNum(shown)} of ` : ''}${plural(n, 'place')} · ${plural(L.categories.length, 'category', 'categories')}`
    : `${plural(n, L.geomLabel)}${L.totalArea ? ` · ${fmtArea(L.totalArea)}` : ''}`;

  return (
    <div className={`layer ${L.expanded ? 'open' : ''} ${L.visible ? '' : 'off'}`} style={{ '--c': L.color }}>
      <div className="layer-head">
        <label className={`swatch ${isPlaces ? 'round' : ''}`} title="Change colour">
          <input type="color" value={L.color} onChange={(e) => onUpdate({ color: e.target.value })} />
        </label>
        <div className="layer-title" onClick={() => onUpdate({ expanded: !L.expanded })} title={L.fileName}>
          <div className="name">
            <span>{L.title}</span>
            {L.iso && <span className="iso">{L.iso}</span>}
          </div>
          <div className="meta"><span className={`kind ${L.kind}`}>{isPlaces ? 'Places' : 'Boundary'}</span>{meta}</div>
        </div>
        <button className="icon-btn" onClick={onZoom} title="Zoom to layer"><Icon name="target" /></button>
        <button className="icon-btn" onClick={() => onUpdate({ visible: !L.visible })} title={L.visible ? 'Hide layer' : 'Show layer'}>
          <Icon name={L.visible ? 'eye' : 'eyeOff'} />
        </button>
        <button className="icon-btn chev" onClick={() => onUpdate({ expanded: !L.expanded })} title="Details"><Icon name="chevron" /></button>
      </div>

      {L.expanded && (
        <div className="layer-body">
          <div className="row">
            <label>Opacity</label>
            <input type="range" min="0" max="100" value={pct} style={{ '--p': `${pct}%` }} onChange={(e) => onUpdate({ opacity: e.target.value / 100 })} />
            <output>{pct}%</output>
          </div>
          {isPlaces ? <PlacesBody {...props} /> : <BoundaryBody {...props} />}
          <div className="layer-actions">
            {!isPlaces && n === 1 && <button className="btn-ghost" onClick={() => onSelectFeature(0)}><Icon name="polygon" size={14} />Details</button>}
            <button className="btn-ghost" onClick={onExport}><Icon name="download" size={14} />Export</button>
            <button className="btn-ghost danger" onClick={onRemove}><Icon name="trash" size={14} />Remove</button>
          </div>
        </div>
      )}
    </div>
  );
}
