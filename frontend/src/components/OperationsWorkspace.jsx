import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import Loading from './Loading.jsx';
import './operations.css';

export default function OperationsWorkspace({ datasets }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [tab, setTab] = useState('Readiness'), [dataset, setDataset] = useState('');
  const [runs, setRuns] = useState([]), [busy, setBusy] = useState(false), [historyBusy, setHistoryBusy] = useState(false);
  const [runError, setRunError] = useState(''), [aoi, setAoi] = useState('Divisoria');
  const [probes, setProbes] = useState({}), [probing, setProbing] = useState({});
  useEffect(() => { const c = new AbortController(); api('/poc/assessment', { signal: c.signal }).then(setData).catch(e => { if(e.name !== 'AbortError') setError(e.message); }); return () => c.abort(); }, []);
  useEffect(() => { if (!dataset && datasets.length) setDataset(datasets[0].id); }, [datasets, dataset]);
  useEffect(() => {
    if (!dataset) return;
    const c = new AbortController(); setHistoryBusy(true); setRuns([]); setRunError('');
    api(`/poc/datasets/${dataset}/preflights`, { signal: c.signal }).then(setRuns).catch(e => { if(e.name !== 'AbortError') setRunError(e.message); }).finally(() => { if (!c.signal.aborted) setHistoryBusy(false); });
    return () => c.abort();
  }, [dataset]);
  async function preflight() {
    setBusy(true); setRunError('');
    try { const r = await api(`/poc/datasets/${dataset}/preflight`, { method: 'POST' }); setRuns(old => [r, ...old].slice(0,10)); }
    catch(e) { setRunError(e.message); } finally { setBusy(false); }
  }
  async function probe(id) {
    setProbing(old => ({...old, [id]: true})); setProbes(old => ({...old, [id]: null}));
    try { const r = await api(`/poc/providers/${id}/diagnose`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({aoi})}); setProbes(old => ({...old, [id]: { ...r, aoi }})); }
    catch(e) { setProbes(old => ({...old, [id]: {error:e.message}})); }
    finally { setProbing(old => ({...old, [id]: false})); }
  }
  function downloadReport() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(runs[0],null,2)], {type:'application/json'}));
    const a = document.createElement('a'); a.href=url; a.download=`JSAN_internal_preflight_${runs[0].id}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  if(error) return <div className="ws-notice" role="alert">{error}<button onClick={() => location.reload()}>Retry</button></div>;
  if(!data) return <Loading>Loading POC assessment…</Loading>;
  const {audit} = data;
  return <div className="poc-operations">
    <div className="page-heading"><div><p className="eyebrow">JSAN × HERE · THREE ASSIGNED AREAS</p><h1>POC Operations</h1><p>Baseline readiness, provider connections and the path to delivery.</p></div><a className="ws-button" href="/api/poc/assessment.md" download>Download assessment</a></div>
    <p className="ws-notice">{data.scope}</p>
    <nav className="ops-tabs" aria-label="POC sections">{['Readiness','API connections','Processing checklist'].map(t => <button key={t} className={`ws-button ${tab===t?'primary':''}`} aria-pressed={tab===t} onClick={() => setTab(t)}>{t}</button>)}</nav>
    {tab==='Readiness' && <>
      <div className="metrics-grid">{[['Package files',audit.files.length],['Baseline records',audit.aois.reduce((n,a)=>n+a.rows,0).toLocaleString()],['Category reference gaps',audit.aois.reduce((n,a)=>n+a.unknown_category_records,0)]].map(([label,value]) => <div className="metric" key={label}><span>{label}</span><strong>{value}</strong><small>Package audit · {audit.reviewed_on}</small></div>)}</div>
      <section className="ops-panel"><h2>Supplied baseline</h2><div className="ops-table-wrap"><table><thead><tr><th>Assigned area</th><th>Records</th><th>Outside AOI</th><th>Unmapped categories (records)</th></tr></thead><tbody>{audit.aois.map(a => <tr key={a.name}><td>{a.name}</td><td>{a.rows.toLocaleString()}</td><td>{a.outside_boundary}</td><td>{a.unknown_category_records}</td></tr>)}</tbody></table></div><p>All baseline IDs are unique. Category gaps need reference alignment; they do not establish that a POI is incorrect. No explicit last-verification date field was supplied.</p><p>The category workbook contains 412 #REF! cells. Resolve these before using it as an authoritative crosswalk.</p></section>
      <section className="ops-panel"><h2>Check the stored customer data</h2><p>Run spatial and structural checks against the actual PostGIS dataset. Reports are saved for traceability.</p><div className="ops-controls"><label>Dataset<select value={dataset} disabled={busy || historyBusy} onChange={e=>setDataset(e.target.value)}><option value="">Select a dataset</option>{datasets.map(d=><option key={d.id} value={d.id}>{d.aoi} — {d.filename}</option>)}</select></label><button className="ws-button primary" disabled={!dataset || busy || historyBusy} onClick={preflight}>{busy?<Loading>Checking baseline…</Loading>:'Run baseline checks'}</button></div>
        {runError && <p role="alert" className="ws-notice">{runError}</p>}{historyBusy && <Loading>Loading saved checks…</Loading>}
        {!historyBusy && runs[0] && <><p>Latest run: {new Date(runs[0].checked_at).toLocaleString()} · {runs[0].rows.toLocaleString()} records</p><table><thead><tr><th>Check</th><th>Status</th><th>Affected</th></tr></thead><tbody>{runs[0].checks.map(c=><tr key={c.id}><td>{c.name}</td><td>{c.status.replaceAll('_',' ')}</td><td>{c.affected.toLocaleString()}</td></tr>)}</tbody></table><p>Internal preflight only. These checks do not approve delivery.</p><button className="ws-button" onClick={downloadReport}>Download internal report</button><details><summary>Saved runs ({runs.length}, latest 10)</summary>{runs.map(r=><p key={r.id}>{new Date(r.checked_at).toLocaleString()} · {r.id}</p>)}</details></>}
      </section>
      <section className="ops-panel"><h2>Exact delivery templates</h2>{audit.templates.map(t=><details key={t.file}><summary>{t.file} · {t.sheets[0].columns.length} columns</summary><p>Sheet: {t.sheets[0].name}. Preserve header spelling and order.</p><ol>{t.sheets[0].columns.map((c,i)=><li key={i}>{c}</li>)}</ol></details>)}<p>Export generation and independent QC gates are still to be implemented.</p></section>
      <details className="ops-panel"><summary>Full package inventory and audit</summary><pre>{JSON.stringify({files:audit.files,documents:audit.documents,workbooks:audit.workbooks,qgis_metadata:audit.qgis_metadata},null,2)}</pre></details>
    </>}
    {tab==='API connections' && <><section className="ops-panel"><h2>Test configured providers</h2><p>Each test makes one bounded API request and may incur a provider charge. It retains no provider POI records and does not measure coverage. Tests are available from the local operator workspace.</p><label>Test area<select value={aoi} onChange={e=>setAoi(e.target.value)}>{audit.aois.map(a=><option key={a.name}>{a.name}</option>)}</select></label></section><div className="ops-provider-grid">{data.providers.map(p=><section className="ops-panel" key={p.id}><h2>{p.name}</h2><span className="ops-status">{p.configured?'Credentials configured':'Not configured'}</span><p>{p.api}</p><p>{p.mode}</p><p>{p.permission}</p><a href={p.documentation} target="_blank" rel="noreferrer">Provider documentation</a><p><button className="ws-button primary" disabled={!p.configured || p.id==='apple' || probing[p.id]} onClick={()=>probe(p.id)}>{probing[p.id]?<Loading>Testing connection…</Loading>:'Test connection'}</button></p>{probes[p.id] && <div role="status">{probes[p.id].error || <><strong>Connected</strong><p>{probes[p.id].aoi} · {probes[p.id].sample_result_count} sample result(s). No records retained.</p></>}</div>}</section>)}</div></>}
    {tab==='Processing checklist' && <><section className="ops-panel"><h2>Required processing stages</h2><p>Target submission: {data.submission_date}. Availability describes implemented behavior, not completion of the POC.</p>{data.stages.map(s=><article className="ops-stage" key={s.id}><h3>{s.id} · {s.name}</h3><span className="ops-status">{s.availability}</span><p>{s.required}</p><small>{s.source}</small></article>)}</section><section className="ops-panel"><h2>Items needing alignment</h2><ul>{data.clarifications.map(c=><li key={c}>{c}</li>)}</ul></section></>}
  </div>;
}
