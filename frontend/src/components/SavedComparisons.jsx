import { useCallback, useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { KINDS, ResultsBrowser } from './ProviderComparison.jsx';
import { api } from '../lib/api.js';
import { fmtDate, hasRole, isSupervisor } from '../lib/platform.js';

const n = (v) => (v || 0).toLocaleString();

/** Saved HERE vs Google/Grab comparisons: metrics across cities, then any city's lists in full. */
export default function SavedComparisons({ user }) {
  const [items, setItems] = useState(null);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api('/provider-comparison/saved');
      setItems(data.comparisons);
      setSelected((cur) => (data.comparisons.some((c) => c.id === cur) ? cur : data.comparisons[0]?.id || null));
    } catch (e) { setError(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function upload(e) {
    e.preventDefault();
    setUploading(true); setError(''); setNotice('');
    const body = new FormData();
    body.append('file', file);
    try {
      const saved = await api('/provider-comparison/saved', { method: 'POST', body });
      setNotice(`Saved ${saved.aoi}: ${n(saved.stats.counts.new)} new · ${n(saved.stats.counts.update)} update · ${n(saved.stats.counts.delete)} delete.`);
      setSelected(saved.id);
      e.target.reset(); setFile(null);
      await load();
    } catch (err) { setError(err.message); }
    finally { setUploading(false); }
  }
  async function remove(c) {
    if (!window.confirm(`Delete the saved ${c.aoi} comparison from ${fmtDate(c.created_at)}? Its rows are removed from the database.`)) return;
    try { await api(`/provider-comparison/saved/${c.id}`, { method: 'DELETE' }); await load(); }
    catch (err) { setError(err.message); }
  }

  // Latest saved comparison per AOI drives the overall totals.
  const latest = Object.values((items || []).reduce((acc, c) => ({ ...acc, [c.aoi]: acc[c.aoi] || c }), {}));
  const total = (k) => latest.reduce((sum, c) => sum + (c.stats.counts[k] || 0), 0);
  const current = items?.find((c) => c.id === selected);
  return <div className="platform-page">
    <div className="page-heading"><div><p className="eyebrow">NEW · UPDATE · DELETE</p><h1>Comparison results</h1>
      <p>Saved HERE vs Google/Grab comparisons for each city: what to add to HERE, update and delete.</p></div></div>
    {error && <div className="ws-notice error" role="alert">{error}</div>}
    {notice && <div className="ws-notice success" role="status">{notice}</div>}


    {!items ? <Loading>Loading saved comparisons…</Loading> : items.length === 0 ? <div className="ws-empty"><h3>No saved comparisons yet</h3>
      <p>Run one on HERE vs Google/Grab and choose “Save to database”, or upload a downloaded comparison workbook above.</p></div> : <>
      <div className="section-title"><div><h2>All cities</h2><p>{latest.length} {latest.length === 1 ? 'city' : 'cities'} · latest saved comparison for each</p></div></div>
      <div className="metrics-grid five">
        {Object.entries(KINDS).map(([k, o]) => <div className="metric" key={k} style={{ borderTop: `3px solid ${o.color}` }}><span>{o.label}</span><strong>{n(total(k))}</strong><small>{o.hint}</small></div>)}
      </div>
      <section className="ops-panel"><div className="records-table-wrap short"><table className="records-table results-table city-table">
        <thead><tr><th>City</th><th>HERE POIs</th><th>Google</th><th>Grab</th>{Object.values(KINDS).map((o) => <th key={o.label}>{o.label}</th>)}<th>Saved</th><th /></tr></thead>
        <tbody>{items.map((c) => <tr key={c.id} className={c.id === selected ? 'selected' : ''}>
          <td><button className="ws-link" onClick={() => setSelected(c.id)}>{c.aoi}</button><small className="cell-sub">{c.dataset}</small></td>
          <td>{n(c.stats.here_records)}</td><td>{n(c.stats.provider_records?.Google)}</td><td>{n(c.stats.provider_records?.Grab)}</td>
          {Object.keys(KINDS).map((k) => <td key={k}>{n(c.stats.counts[k])}</td>)}
          <td>{fmtDate(c.created_at)}</td>
          <td>{hasRole(user, 'ops_manager') && <button className="ws-link danger" onClick={() => remove(c)} title={`Delete the saved ${c.aoi} comparison`}><Icon name="trash" size={13} />Delete</button>}</td></tr>)}</tbody>
      </table></div></section>
      <p className="muted table-hint">Select a city to see its lists, map and Excel below.</p>
      {current && <ResultsBrowser key={current.id} base={`/provider-comparison/saved/${current.id}`} title={current.aoi} aoi={current.aoi} stats={current.stats} onError={setError} />}
    </>}
    {isSupervisor(user) && <details className="ops-panel provider-upload">
      <summary><Icon name="upload" size={14} />Add a comparison from an Excel workbook</summary>
      <form className="provider-form" onSubmit={upload}>
        <label>Comparison workbook (.xlsx, downloaded from HERE vs Google/Grab)<input type="file" accept=".xlsx" required onChange={(e) => setFile(e.target.files[0] || null)} disabled={uploading} /></label>
        <button className="ws-button primary" disabled={!file || uploading}>{uploading ? <Spinner size={14} /> : <Icon name="upload" />}{uploading ? 'Saving…' : 'Save to database'}</button>
      </form>
    </details>}
  </div>;
}
