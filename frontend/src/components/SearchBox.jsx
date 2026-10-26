import { forwardRef, useMemo, useState } from 'react';
import Icon from './Icon.jsx';
import { collator, fmtArea } from '../lib/geo.js';
import { visiblePlaces } from '../lib/places.js';

function Highlight({ text, q }) {
  const i = text.toLowerCase().indexOf(q);
  if (i < 0) return text;
  return <>{text.slice(0, i)}<mark>{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>;
}

const MAX_PLACE_HITS = 60;

function searchPlaces(L, q, hits) {
  let n = 0;
  for (const f of visiblePlaces(L)) {
    const p = f.properties;
    const id = L.keys.id ? String(p[L.keys.id] ?? '') : '';
    const at = p._name.toLowerCase().indexOf(q);
    if (at < 0 && !id.toLowerCase().includes(q)) continue;
    hits.push({ L, fid: f.id, name: p._name, sub: `${p._cat} · ${L.displayName}`, color: p._cc, place: true, rank: at === 0 ? 3 : 4 });
    if (++n >= MAX_PLACE_HITS) break;
  }
}

function search(layers, q) {
  const hits = [];
  for (const L of layers) {
    if (L.kind === 'points') { searchPlaces(L, q, hits); continue; }
    // Single-feature layers are covered by their feature result, which also opens details.
    if (L.data.features.length > 1 && (L.title.toLowerCase().includes(q) || L.iso.toLowerCase() === q)) {
      hits.push({ L, fid: null, name: L.displayName, sub: `Layer · ${L.data.features.length} features`, rank: 0 });
    }
    L.data.features.forEach((f, i) => {
      const p = f.properties;
      const key = L.stats[i].key;
      // Also match local-script names (e.g. Thai adm3_name1) and P-codes.
      const hay = [p._name, key && p[`${key}1`], key && p[key.replace(/_name$/, '_pcode')], L.data.features.length === 1 && L.title]
        .filter(Boolean).join(' ').toLowerCase();
      const at = hay.indexOf(q);
      if (at >= 0) hits.push({ L, fid: i, name: p._name, sub: `${L.displayName} · ${fmtArea(L.stats[i].area)}`, rank: at === 0 ? 1 : 2 });
    });
  }
  return hits.sort((a, b) => a.rank - b.rank || collator.compare(a.name, b.name)).slice(0, 20);
}

const SearchBox = forwardRef(function SearchBox({ layers, onPick }, inputRef) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = query.trim().toLowerCase();
  const hits = useMemo(() => (q ? search(layers, q) : []), [layers, q]);

  const pick = (h) => {
    if (!h) return;
    onPick(h);
    setOpen(false);
    inputRef.current?.blur();
  };

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      if (hits.length) setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + hits.length) % hits.length);
    } else if (e.key === 'Enter') pick(hits[active]);
    else if (e.key === 'Escape') { setOpen(false); e.currentTarget.blur(); }
  };

  return (
    <div className="search">
      <span className="search-ic"><Icon name="search" /></span>
      <input
        ref={inputRef}
        type="text"
        placeholder="Search areas & places…"
        autoComplete="off"
        spellCheck="false"
        value={query}
        onChange={(e) => { setQuery(e.target.value); setActive(0); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      <kbd>/</kbd>
      {open && q && (
        <div className="search-results open">
          {hits.length === 0 && <div className="sr-empty">{layers.length ? 'No matching areas or places' : 'Load files to search them'}</div>}
          {hits.map((h, i) => (
            <button
              key={`${h.L.id}-${h.fid}`}
              className={`sr-item ${i === active ? 'active' : ''}`}
              style={{ '--c': h.color || (h.fid != null && h.L.distinct ? h.L.data.features[h.fid].properties._c : h.L.color) }}
              onMouseDown={(e) => { e.preventDefault(); pick(h); }}
              onMouseEnter={() => setActive(i)}
            >
              <span className="sr-ic"><Icon name={h.place ? 'pin' : h.fid == null ? 'layers' : 'polygon'} size={15} /></span>
              <span className="sr-text"><b><Highlight text={h.name} q={q} /></b><small>{h.sub}</small></span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
});

export default SearchBox;
