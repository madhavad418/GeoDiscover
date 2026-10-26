import { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import Loading from './Loading.jsx';
import { api } from '../lib/api.js';

const AOIS = ['Divisoria', 'Kampung Bali', 'Thanon Phaya Thai'];
const date = value => new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });

export default function CustomerData({ datasets, refresh, storageError, loading, selected, setSelected, onMap }) {
  const [aoi, setAoi] = useState(AOIS[0]);
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [issues, setIssues] = useState([]);
  const [data, setData] = useState(null);
  const [fetching, setFetching] = useState(false);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('');
  const [page, setPage] = useState(1);
  const [raw, setRaw] = useState(false);
  const [detail, setDetail] = useState(null);
  const input = useRef(null);
  const dialog = useRef(null);
  const active = datasets.find(d => d.id === selected) || datasets[0];
  useEffect(() => { setPage(1); setQ(''); setCategory(''); setData(null); setDetail(null); }, [active?.id]);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setFetching(true);
    const timer = setTimeout(async () => {
      try {
        const result = await api(`/customer-data/datasets/${active.id}/records?${new URLSearchParams({ page, q, category })}`, { signal: controller.signal });
        setData(result); setError('');
      } catch (e) { if (e.name !== 'AbortError') { setError(e.message); setData(null); } }
      finally { if (!controller.signal.aborted) setFetching(false); }
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [active?.id, page, q, category]);
  useEffect(() => { if (detail) dialog.current?.showModal(); }, [detail]);

  async function upload(event) {
    event.preventDefault();
    if (!file) return;
    setError(''); setMessage(''); setIssues([]);
    if (file.size > 25 * 1024 * 1024) { setError('Maximum file size is 25 MB.'); return; }
    setUploading(true);
    try {
      const body = new FormData(); body.append('file', file); body.append('aoi', aoi);
      const saved = await api('/customer-data/imports', { method: 'POST', body });
      await refresh(); setSelected(saved.id); setPage(1);
      setMessage(`${saved.row_count.toLocaleString()} POIs saved successfully for ${saved.aoi}.`);
      setFile(null); if (input.current) input.current.value = '';
    } catch (e) { setError(e.message); setIssues(e.issues || []); }
    finally { setUploading(false); }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">YOUR SOURCE OF TRUTH</p><h1>Customer Data</h1><p>Save, browse and explore the HERE baseline for each assigned area.</p></div><span className="ws-chip">HERE BASELINE</span></div>
    <form className="import-panel" onSubmit={upload} aria-busy={uploading}>
      <div className="import-title"><span className="metric-icon"><Icon name="upload" size={22}/></span><div><h2>Import a customer dataset</h2><p>CSV or Excel (.xlsx) · Up to 25 MB · Original columns preserved</p></div></div>
      <div className="import-fields"><label>Assigned area<select value={aoi} onChange={e => setAoi(e.target.value)} disabled={uploading}>{AOIS.map(a => <option key={a}>{a}</option>)}</select></label>
        <label className="file-label">Customer file<input ref={input} type="file" accept=".csv,.xlsx" required disabled={uploading} onChange={e => setFile(e.target.files[0] || null)} /></label>
        <button className="ws-button primary" disabled={uploading || !file} type="submit"><Icon name="upload" />{uploading ? 'Validating & saving…' : 'Save dataset'}</button></div>
      <p className="import-help">Requires a place ID, POI name and valid display coordinates. Each upload is saved as a separate dataset; identical files in the same AOI are detected.</p>
    </form>
    {message && <div className="ws-notice success" role="status">{message}</div>}
    {(error || storageError) && <div className="ws-notice error" role="alert">{error || storageError}{issues.length > 0 && <ul>{issues.map((issue, i) => <li key={i}>{issue.sheet}, row {issue.row}: {issue.message}</li>)}</ul>}{storageError && <button className="ws-link" onClick={refresh}>Retry connection</button>}</div>}
    <div className="section-title"><div><h2>Saved datasets <span className="ws-chip">{datasets.length}</span></h2><p>Persistent customer records, organised by area.</p></div><button className="ws-link" onClick={refresh} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button></div>
    {loading && !datasets.length ? <div className="ws-empty" role="status">Loading customer datasets…</div> : !datasets.length ? <div className="ws-empty"><Icon name="layers" size={32}/><h3>{storageError ? 'Customer storage is unavailable' : 'Your baseline belongs here'}</h3><p>{storageError ? 'Restore the database connection to browse and save records.' : 'Select an assigned area and upload the first HERE file to get started.'}</p></div> : <>
      <div className="dataset-list">{datasets.map(d => <button key={d.id} className={`dataset-card ${d.id === active?.id ? 'selected' : ''}`} onClick={() => { setSelected(d.id); setPage(1); }}><span className="dataset-top"><Icon name="copy"/><span>{d.country}</span></span><strong>{d.aoi}</strong><span className="dataset-filename" title={d.filename}>{d.filename}</span><span className="dataset-meta">{d.row_count.toLocaleString()} POIs <small>{date(d.created_at)}</small></span></button>)}</div>
      {active && <section className="records-panel">
        <div className="records-heading"><div><h2>{active.aoi}</h2><p>{active.filename} · {active.columns.length} source columns</p></div><button className="ws-button" onClick={() => onMap(active.id)}><Icon name="map"/>View in AOI Viewer</button></div>
        <div className="records-filters"><label className="records-search"><Icon name="search"/><input aria-label="Search customer records" placeholder="Search name, place ID or address…" value={q} onChange={e => { setQ(e.target.value); setPage(1); }} /></label><select aria-label="Filter category" value={category} onChange={e => { setCategory(e.target.value); setPage(1); }}><option value="">All categories</option>{data?.categories.map(c => <option key={c}>{c}</option>)}</select><label className="column-toggle"><input type="checkbox" checked={raw} onChange={e => setRaw(e.target.checked)} />All source columns</label></div>
        <div className="records-table-wrap" aria-busy={fetching}>{fetching ? <div className="table-loading" role="status">Loading records…</div> : data && <table className="records-table"><thead><tr><th>Inspect</th>{(raw ? active.columns : ['Place ID', 'POI name', 'Category', 'Address', 'Latitude', 'Longitude']).map(c => <th key={c}>{c}</th>)}</tr></thead><tbody>{data.records.map(row => <tr key={row.id}><td><button className="ws-link" onClick={() => setDetail(row)} aria-label={`Inspect ${row.name}`}>Details ↗</button></td>{(raw ? active.columns.map(c => row.raw[c]) : [row.place_id, row.name, row.category_name || row.category_code, row.address, row.latitude, row.longitude]).map((v, i) => <td key={i} title={String(v ?? '')}>{v ?? '—'}</td>)}</tr>)}</tbody></table>}{!fetching && data?.records.length === 0 && <div className="ws-empty">No POIs match your filters.</div>}</div>
        <div className="records-pagination"><span>{fetching ? 'Updating results?' : data ? `${data.total.toLocaleString()} matching records` : 'No records loaded'}{data && ` · Page ${page} of ${Math.max(1, Math.ceil(data.total / 50))}`}</span><div><button className="ws-button" disabled={page <= 1 || fetching} onClick={() => setPage(p => p - 1)}>Previous</button><button className="ws-button" disabled={!data || page * 50 >= data.total || fetching} onClick={() => setPage(p => p + 1)}>Next</button></div></div>
      </section>}
    </>}
    <dialog className="record-dialog" ref={dialog} onClose={() => setDetail(null)}><div className="records-heading"><div><p className="eyebrow">CUSTOMER RECORD</p><h2>{detail?.name}</h2></div><button className="ws-button" onClick={() => dialog.current.close()} aria-label="Close record details"><Icon name="x" /></button></div><dl>{detail && Object.entries(detail.raw).map(([k,v]) => <div key={k}><dt>{k}</dt><dd>{v || '—'}</dd></div>)}</dl></dialog>
  </>;
}
