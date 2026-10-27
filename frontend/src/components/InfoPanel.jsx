import { useEffect, useRef } from 'react';
import Icon from './Icon.jsx';
import PlaceDetails from './PlaceDetails.jsx';
import { TranslateToggle, TransliterateToggle, Tx, useTranslate } from './Translate.jsx';
import { countCoords, fmtArea, fmtCoord, fmtDist, fmtNum } from '../lib/geo.js';

function BoundaryDetails({ layer: L, fid, onClose, onZoom, onCopy, onExport, onCollect }) {
  const f = L.data.features[fid];
  const p = f.properties;
  const st = L.stats[fid];
  const key = st.key;
  const level = key && /^adm(\d)_name$/.exec(key)?.[1];
  const local = key && p[`${key}1`];
  const pcode = key ? p[key.replace(/_name$/, '_pcode')] : null;
  const crumbs = [];
  if (level != null) for (let n = +level - 1; n >= 0; n--) if (p[`adm${n}_name`]) crumbs.push(p[`adm${n}_name`]);
  const share = L.totalArea && L.data.features.length > 1 ? (st.area / L.totalArea) * 100 : null;
  const reported = parseFloat(p.area_sqkm);
  const color = L.distinct ? p._c : L.color;
  const attrs = Object.entries(p).filter(([k, v]) => !k.startsWith('_') && v !== null && v !== '');
  // Local-script names (e.g. Thai adm3_name1 "ถนนพญาไท") can be translated on request.
  const tr = useTranslate(attrs.map(([, v]) => v).filter((v) => typeof v === 'string'));

  return (
    <>
      <div className="info-hero" style={{ '--c': color }}>
        <button className="icon-btn close" onClick={onClose} title="Close (Esc)"><Icon name="x" /></button>
        <div className="kicker">{L.displayName}</div>
        <h2>{p._name}</h2>
        {local && <div className="local-name"><Tx tr={tr} value={local} /></div>}
        {crumbs.length > 0 && (
          <div className="crumbs">
            {crumbs.map((c, i) => <span key={c} className="crumb">{i > 0 && <i>›</i>}<span>{c}</span></span>)}
          </div>
        )}
        <div className="hero-actions"><TranslateToggle tr={tr} /><TransliterateToggle tr={tr} /></div>
      </div>

      <div className="info-sec" style={{ '--c': color }}>
        <h3>Measurements</h3>
        <div className="stat-grid">
          {st.area > 0 && <div className="stat"><label>Area</label><b>{fmtArea(st.area)}</b></div>}
          {st.perim > 0 && <div className="stat"><label>{st.area ? 'Perimeter' : 'Length'}</label><b>{fmtDist(st.perim)}</b></div>}
          {isFinite(reported) && <div className="stat"><label>Reported area</label><b>{reported.toFixed(3)} <small>km²</small></b></div>}
          <div className="stat"><label>Vertices</label><b>{fmtNum(countCoords(f.geometry))}</b></div>
          {pcode && <div className="stat mono"><label>P-code</label><b>{pcode}</b></div>}
          {p.valid_on && <div className="stat mono"><label>Valid on</label><b>{p.valid_on}</b></div>}
          <div className="stat wide mono"><label>Centre</label><b>{fmtCoord(st.center[1], st.center[0])}</b></div>
        </div>
        {share != null && (
          <div className="share-bar">
            <div className="track"><div className="fill" style={{ width: `${Math.max(share, 1.5)}%` }} /></div>
            <p>{share.toFixed(1)}% of {L.title} ({fmtArea(L.totalArea)} across {L.data.features.length} features)</p>
          </div>
        )}
      </div>

      <details className="info-sec" open={attrs.length <= 14}>
        <summary><h3>Attributes · {attrs.length}</h3><span className="chev"><Icon name="chevron" size={14} /></span></summary>
        <table className="kv">
          <tbody>
            {attrs.map(([k, v]) => <tr key={k}><td>{k}</td><td>{typeof v === 'object' ? JSON.stringify(v) : typeof v === 'string' ? <Tx tr={tr} value={v} /> : String(v)}</td></tr>)}
          </tbody>
        </table>
      </details>

      <div className="info-actions">
        {['Polygon','MultiPolygon'].includes(f.geometry.type) && <button className="btn-ghost" onClick={() => onCollect?.(f)}><Icon name="download" size={14} />Collect POIs (APIs)</button>}
        <button className="btn-ghost" onClick={onZoom}><Icon name="target" size={14} />Zoom to</button>
        <button className="btn-ghost" onClick={onCopy}><Icon name="copy" size={14} />Copy centre</button>
        <button className="btn-ghost" onClick={onExport}><Icon name="download" size={14} />GeoJSON</button>
      </div>
    </>
  );
}

export default function InfoPanel({ layer, fid, ...handlers }) {
  // Keep showing the last selection while the panel slides out.
  const last = useRef(null);
  if (layer) last.current = { layer, fid };
  const bodyRef = useRef(null);
  const key = layer ? `${layer.id}:${fid}` : null;
  useEffect(() => { if (key && bodyRef.current) bodyRef.current.scrollTop = 0; }, [key]);

  return (
    <aside className="panel info" aria-hidden={!layer}>
      <div className="info-body" ref={bodyRef}>
        {last.current && last.current.layer.data.features[last.current.fid] && (
          // Keyed by feature so per-record state (e.g. translations) resets, but not while sliding out.
          last.current.layer.kind === 'points'
            ? <PlaceDetails key={`${last.current.layer.id}:${last.current.fid}`} {...last.current} {...handlers} />
            : <BoundaryDetails key={`${last.current.layer.id}:${last.current.fid}`} {...last.current} {...handlers} />
        )}
      </div>
    </aside>
  );
}
