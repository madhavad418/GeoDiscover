import { Fragment, useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import ComparisonMap from './ComparisonMap.jsx';
import { api, send } from '../lib/api.js';
import './areaCollection.css';

export const KINDS = {
  new: { label: 'New', hint: 'In Google/Grab, not in HERE', color: '#5fd39a' },
  update: { label: 'Update', hint: 'Matched, attributes differ', color: '#e8c27a' },
  delete: { label: 'Delete', hint: 'Closed, or not found in Google/Grab', color: '#ff6b8b' },
  matched: { label: 'Matched · no change', hint: 'Same in HERE and providers', color: '#7d9db4' },
  review: { label: 'Needs review', hint: 'Identity unclear', color: '#b98cff' },
};
const HEADINGS = {
  name1: 'Name', primarycategorynm: 'Category', upaddress: 'Address', phone_numbers: 'Phone', webaddress: 'Website',
  sources: 'Found in', reason: 'Why', here_placeid: 'HERE place ID', changed_fields: 'Changed', distance_m: 'Distance (m)',
  delete_basis: 'Basis', match_level: 'Match', candidate_here_names: 'Possible HERE matches',
};
const PAGE = 50;
// Row details list the identifying and comparison fields first, then the remaining HERE columns.
const DETAIL_ORDER = ['name1', 'name2', 'primarycategorynm', 'primarycategory', 'here_placeid', 'placeid', 'changed_fields', 'delete_basis',
  'reason', 'sources', 'source_place_ids', 'distance_m', 'match_level', 'candidate_here_names', 'candidate_here_placeids', 'upaddress',
  'hno', 'streetname', 'postalcode', 'admin2', 'admin3', 'admin4', 'admin5', 'phone_numbers', 'mobile_numbers', 'webaddress',
  'opening_hours', 'status', 'chainid', 'chainname', 'food_id', 'food_name', 'displaylatitude', 'displaylongitude'];

async function download(url, fallbackName) {
  const res = await fetch(url, { credentials: 'same-origin' });
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Download failed');
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') || '')?.[1] || fallbackName;
  const href = URL.createObjectURL(await res.blob());
  const a = document.createElement('a');
  a.href = href; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}

function RowDetail({ base, kind, index, onClose }) {
  const [row, setRow] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    api(`${base}/rows/${kind}/${index}`).then(setRow).catch((e) => setError(e.message));
  }, [base, kind, index]);
  const changed = row?.changed_fields ? row.changed_fields.split(', ') : [];
  const rank = (k) => { const i = DETAIL_ORDER.indexOf(k); return i < 0 ? DETAIL_ORDER.length : i; };
  const entries = row ? Object.entries(row).filter(([k]) => !k.startsWith('_') && !/^(here|proposed)_(?!placeid)/.test(k))
    .sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b)) : [];
  return <div className="collection-overlay" onClick={onClose}><section className="collection-dialog provider-detail" role="dialog" aria-modal="true"
    aria-labelledby="row-title" onClick={(e) => e.stopPropagation()}>
    <header><div><small>{KINDS[kind].label.toUpperCase()}</small><h2 id="row-title">{row?.name1 || '…'}</h2><p>{row?.primarycategorynm}</p></div>
      <button className="btn-ghost" onClick={onClose}>Close</button></header>
    {error && <p className="collection-error" role="alert">{error}</p>}
    {changed.length > 0 && <table className="records-table compact"><thead><tr><th>Changed</th><th>HERE now</th><th>Google/Grab</th></tr></thead>
      <tbody>{changed.map((f) => <tr key={f}><td>{f}</td><td>{row[`here_${f}`] || '—'}</td><td>{row[`proposed_${f}`] || '—'}</td></tr>)}</tbody></table>}
    {!row && !error ? <Loading>Loading…</Loading> : <dl className="kv-list">{entries.map(([k, v]) => <Fragment key={k}><dt>{k}</dt><dd>{String(v)}</dd></Fragment>)}</dl>}
    {row && <a className="ws-button" target="_blank" rel="noreferrer"
      href={`https://www.google.com/maps/search/?api=1&query=${row._lat},${row._lon}`}><Icon name="map" />Open location in Google Maps</a>}
  </section></div>;
}

/** Cards, map, searchable table and row details for one comparison; `base` is its API path (in-memory run or saved). */
export function ResultsBrowser({ base, title, aoi = null, stats: s, actions = null, onError }) {
  const [kind, setKind] = useState('new');
  const [basis, setBasis] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState(null);
  const [showMap, setShowMap] = useState(false);
  const [detail, setDetail] = useState(null);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => { setKind('new'); setBasis(''); setQ(''); setPage(0); setShowMap(false); setDetail(null); }, [base]);
  useEffect(() => {
    const c = new AbortController();
    const params = new URLSearchParams({ kind, q, basis, offset: page * PAGE, limit: PAGE });
    const t = setTimeout(() => {
      setRows(null);
      api(`${base}/rows?${params}`, { signal: c.signal }).then(setRows)
        .catch((e) => { if (e.name !== 'AbortError') onError(e.message); });
    }, q ? 250 : 0);
    return () => { clearTimeout(t); c.abort(); };
  }, [base, kind, q, basis, page]);

  async function excel() {
    setDownloading(true);
    try { await download(`/api${base}/excel`, 'HERE_comparison.xlsx'); }
    catch (err) { onError(err.message); }
    finally { setDownloading(false); }
  }
  const choose = (k) => { setKind(k); setBasis(''); setPage(0); };
  return <>
    <div className="section-title"><div><h2>{title}</h2>
      <p>{s.here_records.toLocaleString()} HERE POIs · {Object.entries(s.provider_records).map(([p, n]) => `${n.toLocaleString()} ${p}`).join(' · ')}
        {' '}· {s.linked_businesses.toLocaleString()} provider businesses after removing Google/Grab duplicates</p>
      {s.name_matching && <p className="muted">Names compared as written and transliterated ({s.name_matching.transliteration}) ·
        translation to English: {s.name_matching.translation}</p>}</div>
      <div className="button-row">
        {actions}
        <button className="ws-button" onClick={() => setShowMap(true)}><Icon name="map" />Open map</button>
        <button className="ws-button primary" onClick={excel} disabled={downloading}>{downloading ? <Spinner size={14} /> : <Icon name="download" />}Download Excel</button>
      </div></div>
    <div className="outcome-grid five">{Object.entries(KINDS).map(([k, o]) =>
      <button key={k} className={`outcome-card ${kind === k ? 'active' : ''}`} style={{ '--o': o.color }} onClick={() => choose(k)}>
        <strong>{(s.counts[k] || 0).toLocaleString()}</strong><span>{o.label}</span><small className="cell-sub">{o.hint}</small></button>)}</div>
    {showMap && <ComparisonMap base={base} aoi={aoi || title} title={title} kinds={KINDS} onClose={() => setShowMap(false)} />}
    <section className="records-panel">
      <div className="records-filters"><label className="records-search"><Icon name="search" /><input placeholder="Search name, place ID, address…"
        value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} /></label>
        {kind === 'delete' && <label className="inline-select">Basis<select value={basis} onChange={(e) => { setBasis(e.target.value); setPage(0); }}>
          <option value="">All ({(s.counts.delete || 0).toLocaleString()})</option>
          {Object.entries(s.delete_breakdown || {}).map(([b, n]) => <option key={b} value={b}>{b} ({n.toLocaleString()})</option>)}</select></label>}</div>
      <div className="records-table-wrap">{!rows ? <div className="table-loading"><Loading>Loading {KINDS[kind].label.toLowerCase()}…</Loading></div> :
        rows.rows.length === 0 ? <div className="ws-empty compact"><p>No rows.</p></div> :
        <table className="records-table results-table"><thead><tr>{rows.columns.map((c) => <th key={c}>{HEADINGS[c] || c}</th>)}<th /></tr></thead>
          <tbody>{rows.rows.map((r) => <tr key={r._index}>{rows.columns.map((c) => <td key={c} className={c === 'reason' ? 'why' : ''}
            title={String(r[c] ?? '')}>{String(r[c] ?? '') || '—'}</td>)}
            <td><button className="ws-link" onClick={() => setDetail({ kind, index: r._index })}>Details ↗</button></td></tr>)}</tbody></table>}</div>
      {rows && <div className="records-pagination"><span>{rows.total.toLocaleString()} rows · page {page + 1} of {Math.max(1, Math.ceil(rows.total / PAGE))}</span>
        <div><button className="ws-button" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
          <button className="ws-button" disabled={(page + 1) * PAGE >= rows.total} onClick={() => setPage((p) => p + 1)}>Next</button></div></div>}
    </section>
    {detail && <RowDetail base={base} kind={detail.kind} index={detail.index} onClose={() => setDetail(null)} />}
  </>;
}

export default function ProviderComparison({ datasets, onSaved }) {
  const [datasetId, setDatasetId] = useState(datasets[0]?.id || '');
  const [file, setFile] = useState(null);
  const [run, setRun] = useState(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);

  useEffect(() => { if (!datasetId && datasets[0]) setDatasetId(datasets[0].id); }, [datasets, datasetId]);
  useEffect(() => {
    if (run?.state !== 'running') return undefined;
    const t = setTimeout(() => api(`/provider-comparison/runs/${run.id}`).then(setRun).catch((e) => setError(e.message)), 2000);
    return () => clearTimeout(t);
  }, [run]);

  async function start(e) {
    e.preventDefault();
    setStarting(true); setError(''); setSaved(null);
    const body = new FormData();
    body.append('dataset_id', datasetId);
    body.append('file', file);
    try { setRun(await api('/provider-comparison/runs', { method: 'POST', body })); }
    catch (err) { setError(err.message); }
    finally { setStarting(false); }
  }
  async function save() {
    setSaving(true); setError('');
    try { setSaved(await send(`/provider-comparison/runs/${run.id}/save`, 'POST')); }
    catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  if (!datasets.length) return <div className="ws-empty"><h3>Import a HERE baseline first</h3><p>Customer Data holds the baseline the comparison runs against.</p></div>;
  return <div className="platform-page">
    <div className="page-heading"><div><p className="eyebrow">HERE · GOOGLE · GRAB</p><h1>HERE vs Google/Grab</h1>
      <p>Compare a provider extract from “Collect POIs (APIs)” with the stored HERE baseline: what to add, update and delete.</p></div></div>
    <div className="ws-notice policy"><Icon name="link" /> A run is held in memory for 6 hours; use “Save to database” to keep it under Comparison results.
      “Not found in Google or Grab” is not proof of closure: verify before deleting.</div>
    {error && <div className="ws-notice error" role="alert">{error}</div>}
    {saved && <div className="ws-notice success" role="status">Saved {saved.aoi} to the database.
      {onSaved && <button className="ws-link" onClick={onSaved}>Open Comparison results ↗</button>}</div>}

    <form className="ops-panel provider-form" onSubmit={start}>
      <label>HERE baseline<select value={datasetId} onChange={(e) => setDatasetId(e.target.value)} disabled={starting || run?.state === 'running'}>
        {datasets.map((d) => <option key={d.id} value={d.id}>{d.aoi} · {d.filename} · {d.row_count.toLocaleString()} POIs</option>)}</select></label>
      <label>Provider extract (.xlsx)<input type="file" accept=".xlsx" required onChange={(e) => setFile(e.target.files[0] || null)}
        disabled={starting || run?.state === 'running'} /></label>
      <button className="ws-button primary" disabled={!file || !datasetId || starting || run?.state === 'running'}>
        {starting || run?.state === 'running' ? <Spinner size={14} /> : <Icon name="layers" />}
        {starting ? 'Uploading…' : run?.state === 'running' ? 'Comparing…' : 'Compare with HERE'}</button>
    </form>

    {run?.state === 'running' && <div className="table-loading"><Loading>Comparing {run.extract} with {run.aoi}… this takes 1–3 minutes.</Loading></div>}
    {run?.state === 'failed' && <div className="ws-notice error" role="alert">{run.error}</div>}
    {run?.state === 'finished' && run.stats && <ResultsBrowser base={`/provider-comparison/runs/${run.id}`} title={run.aoi} stats={run.stats} onError={setError}
      actions={<button className="ws-button" onClick={save} disabled={saving || !!saved}>{saving ? <Spinner size={14} /> : <Icon name="upload" />}{saved ? 'Saved' : 'Save to database'}</button>} />}
  </div>;
}
