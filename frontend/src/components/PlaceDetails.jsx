import Icon from './Icon.jsx';
import { TranslateToggle, TransliterateToggle, Tx, useTranslate } from './Translate.jsx';
import { fmtCoord } from '../lib/geo.js';
import { parseOpeningHours, safeUrls, splitList, streetViewPoint } from '../lib/places.js';

const TODAY = (new Date().getDay() + 6) % 7; // Monday = 0

const CONTACT_KEYS = {
  phone: ['phone_numbers', 'phone', 'telephone', 'tel'],
  mobile: ['mobile_numbers', 'mobile'],
  email: ['email', 'e_mail'],
  web: ['webaddress', 'website', 'url', 'web'],
  hours: ['opening_hours', 'hours', 'openinghours'],
};
const pick = (p, keys) => keys.map((k) => p[k]).find((v) => v != null && String(v).trim() !== '');

function Row({ icon, label, children }) {
  return (
    <div className="pd-row">
      <span className="pd-ic"><Icon name={icon} size={15} /></span>
      <div><label>{label}</label><div className="pd-val">{children}</div></div>
    </div>
  );
}

export default function PlaceDetails({ layer: L, fid, containers, onClose, onZoom, onCopy, onExport, onStreetView }) {
  const f = L.data.features[fid];
  const p = f.properties;
  const [lon, lat] = f.geometry.coordinates;
  const id = L.keys.id && p[L.keys.id];
  const address = L.keys.address && p[L.keys.address];
  const phones = [...splitList(pick(p, CONTACT_KEYS.phone)), ...splitList(pick(p, CONTACT_KEYS.mobile))];
  const email = pick(p, CONTACT_KEYS.email);
  const webs = safeUrls(pick(p, CONTACT_KEYS.web));
  const hoursRaw = pick(p, CONTACT_KEYS.hours);
  const hours = parseOpeningHours(hoursRaw);
  const sv = streetViewPoint(L, f);
  const attrs = Object.entries(p).filter(([k, v]) => !k.startsWith('_') && v !== null && String(v).trim() !== '');
  // One toggle translates every non-Latin value of this place (name, address, admin areas, …).
  const tr = useTranslate([p._name, address, ...attrs.map(([, v]) => v)].filter((v) => typeof v === 'string'));

  return (
    <>
      <div className="info-hero" style={{ '--c': p._cc }}>
        <button className="icon-btn close" onClick={onClose} title="Close (Esc)"><Icon name="x" /></button>
        <div className="kicker">{p._cat}</div>
        <h2><Tx tr={tr} value={p._name} /></h2>
        {address && <div className="local-name"><Tx tr={tr} value={address} /></div>}
        <div className="crumbs">
          {id && <span className="crumb"><span className="mono-chip" title="Place identifier">{id}</span></span>}
          <span className="crumb"><span>{L.displayName}</span></span>
          {p.status && <span className="crumb"><span className="status-chip">{p.status}</span></span>}
        </div>
        <div className="hero-actions"><TranslateToggle tr={tr} /><TransliterateToggle tr={tr} /></div>
      </div>

      <div className="info-sec">
        <div className="sv-card">
          <div className="sv-art"><Icon name="streetview" size={22} /></div>
          <div className="sv-text">
            <b>See this place at street level?</b>
            <span>Opens Google Street View at {sv[1].toFixed(5)}, {sv[0].toFixed(5)}</span>
          </div>
          <button className="btn-primary sm" onClick={() => onStreetView(sv)}>Open Street View</button>
        </div>
      </div>

      <div className="info-sec">
        <h3>Location</h3>
        <Row icon="pin" label="Coordinates"><span className="mono">{fmtCoord(lat, lon, 6)}</span></Row>
        {containers.length > 0 && (
          <Row icon="polygon" label="Inside boundary">
            {containers.map((c) => <div key={c}>{c}</div>)}
          </Row>
        )}
      </div>

      {(phones.length > 0 || email || webs.length > 0) && (
        <div className="info-sec">
          <h3>Contact</h3>
          {phones.length > 0 && (
            <Row icon="phone" label={phones.length > 1 ? 'Phone numbers' : 'Phone'}>
              {phones.map((n) => <div key={n}><a href={`tel:${n.replace(/[^\d+]/g, '')}`}>{n}</a></div>)}
            </Row>
          )}
          {email && <Row icon="mail" label="Email"><a href={`mailto:${email}`}>{email}</a></Row>}
          {webs.length > 0 && (
            <Row icon="link" label={webs.length > 1 ? 'Websites' : 'Website'}>
              {webs.map((u) => <div key={u}><a href={u} target="_blank" rel="noopener noreferrer">{u.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}</a></div>)}
            </Row>
          )}
        </div>
      )}

      {hoursRaw && (
        <div className="info-sec">
          <h3>Opening hours</h3>
          {hours ? (
            <table className="hours">
              <tbody>
                {hours.map((h, i) => (
                  <tr key={h.day} className={i === TODAY ? 'today' : ''}>
                    <td>{h.day}</td>
                    <td>{h.ranges ? h.ranges.join(', ') : <span className="muted">Not listed</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="pd-raw">{hoursRaw}</p>}
        </div>
      )}

      <details className="info-sec">
        <summary><h3>All attributes · {attrs.length}</h3><span className="chev"><Icon name="chevron" size={14} /></span></summary>
        <table className="kv">
          <tbody>
            {attrs.map(([k, v]) => <tr key={k}><td>{k}</td><td>{typeof v === 'string' ? <Tx tr={tr} value={v} /> : String(v)}</td></tr>)}
          </tbody>
        </table>
      </details>

      <div className="info-actions">
        <button className="btn-ghost" onClick={onZoom}><Icon name="target" size={14} />Zoom to</button>
        <button className="btn-ghost" onClick={onCopy}><Icon name="copy" size={14} />Copy lat/lon</button>
        <button className="btn-ghost" onClick={onExport}><Icon name="download" size={14} />GeoJSON</button>
      </div>
    </>
  );
}
