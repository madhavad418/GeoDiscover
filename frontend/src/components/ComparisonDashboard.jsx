import { useCallback, useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { api, send } from '../lib/api.js';
import { OUTCOMES, fmtDate, isSupervisor } from '../lib/platform.js';

function SourceImport({ aoi, types, onDone }) {
  const [form, setForm] = useState({ source_type: 'official_website', source_name: '', license_reference: '', permitted_use: '', collection_method: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const input = useRef(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const body = new FormData();
    Object.entries({ ...form, aoi }).forEach(([k, v]) => body.append(k, v));
    body.append('file', file);
    try {
      const saved = await api('/sources/batches', { method: 'POST', body });
      onDone(saved);
      setFile(null);
      if (input.current) input.current.value = '';
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="import-panel platform-form" onSubmit={submit} aria-busy={busy}>
      <div className="import-title"><span className="metric-icon"><Icon name="upload" size={20} /></span><div><h2>Import permitted source observations</h2>
        <p>CSV or Excel · needs a source record ID, name and coordinates · rows outside {aoi} are skipped</p></div></div>
      <div className="form-grid">
        <label>Source type<select value={form.source_type} onChange={set('source_type')}>{Object.entries(types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        <label>Source name<input required maxLength={200} value={form.source_name} onChange={set('source_name')} placeholder="e.g. Jollibee store locator" /></label>
        <label className="wide">Licence / permission reference<input required maxLength={2000} value={form.license_reference} onChange={set('license_reference')} placeholder="Agreement, terms URL or written permission" /></label>
        <label className="wide">Permitted use<input required maxLength={2000} value={form.permitted_use} onChange={set('permitted_use')} placeholder="e.g. storage, comparison and redistribution to HERE" /></label>
        <label>Collection method<input maxLength={200} value={form.collection_method} onChange={set('collection_method')} placeholder="Optional" /></label>
        <label>File<input ref={input} type="file" accept=".csv,.xlsx" required onChange={(e) => setFile(e.target.files[0] || null)} /></label>
      </div>
      {error && <div className="ws-notice error" role="alert">{error.message}{error.issues?.length > 0 && <ul>{error.issues.map((i, n) => <li key={n}>Row {i.row}: {i.message}</li>)}</ul>}</div>}
      <button className="ws-button primary" disabled={busy || !file}>{busy ? <Spinner size={14} /> : <Icon name="upload" />}{busy ? 'Validating…' : 'Import source'}</button>
    </form>
  );
}

function ResultDetail({ id, onClose }) {
  const [data, setData] = useState(null);
  useEffect(() => { api(`/comparison/results/${id}`).then(setData).catch(() => setData({ error: true })); }, [id]);
  const dialog = useRef(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const e = data?.explanation;
  return (
    <dialog className="record-dialog wide" ref={dialog} onClose={onClose}>
      <div className="records-heading"><div><p className="eyebrow">COMPARISON RESULT</p><h2>{data ? data.label : 'Loading…'}</h2></div>
        <button className="ws-button" onClick={() => dialog.current.close()} aria-label="Close"><Icon name="x" /></button></div>
      {!data ? <div className="table-loading"><Loading>Loading explanation…</Loading></div> : data.error ? <p className="ws-notice error">Could not load this result.</p> : (
        <div className="result-detail">
          <ul className="reason-list">{e.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <div className="two-col">
            <section><h3>HERE baseline</h3>{e.here ? <dl className="kv-list"><dt>Place ID</dt><dd>{e.here.place_id}</dd><dt>Name</dt><dd>{e.here.name}</dd>
              <dt>Category</dt><dd>{e.here.category_name || e.here.category_code}</dd><dt>Address</dt><dd>{e.here.address || '—'}</dd></dl> : <p className="muted">No HERE record matched.</p>}</section>
            <section><h3>GeoDiscover</h3>{e.master ? <dl className="kv-list"><dt>JSAN ID</dt><dd>{e.master.jsan_id}</dd><dt>Name</dt><dd>{e.master.name}</dd>
              <dt>Sources</dt><dd>{e.master.sources.join(', ')}</dd><dt>Status</dt><dd>{e.master.status}</dd></dl> : <p className="muted">No permitted source observed this POI.</p>}</section>
          </div>
          {e.match && <section><h3>Why this match</h3><Signals s={e.match} /></section>}
          {e.changed_fields.length > 0 && <section><h3>Differences</h3><table className="records-table compact"><thead><tr><th>Attribute</th><th>Kind</th><th>HERE</th><th>Discovered</th></tr></thead>
            <tbody>{e.changed_fields.map((d) => <tr key={d.field}><td>{d.field}</td><td>{d.kind.replace(/_/g, ' ')}</td><td>{fmt(d.here)}</td>
              <td>{d.observed.map((o) => `${fmt(o.value)} (${o.source})`).join('; ')}</td></tr>)}</tbody></table></section>}
          {e.candidates.length > 0 && <section><h3>Other possible HERE matches</h3><table className="records-table compact"><thead><tr><th>Place ID</th><th>Name</th><th>Level</th><th>Distance</th><th>Name sim.</th><th>Signals</th></tr></thead>
            <tbody>{e.candidates.map((c) => <tr key={c.place_id}><td>{c.place_id}</td><td>{c.here_name}</td><td>{c.level}{c.chain ? ' · chain' : ''}</td><td>{c.distance_m} m ({c.band})</td>
              <td>{c.name_similarity}</td><td>{['M1', 'M2', 'M3', 'M4', 'M5'].filter((m) => c[m]).join(' ') || '—'}</td></tr>)}</tbody></table></section>}
          {e.master?.conflicts?.length > 0 && <section><h3>Conflicting source values</h3><ul>{e.master.conflicts.map((c) => <li key={c.field}>{c.field}: {c.values.join(' · ')}</li>)}</ul></section>}
        </div>)}
    </dialog>
  );
}

const fmt = (v) => (v == null || v === '' ? '—' : Array.isArray(v) ? v.join(', ') : String(v));

export function Signals({ s }) {
  const items = [['M1', `Name ${s.name_similarity}`], ['M2', 'Category L2'], ['M3', 'Phone'], ['M4', 'Address'], ['M5', 'Website/social']];
  return (
    <div className="signal-row">
      <span className="signal neutral">{s.distance_m} m · {s.band}</span>
      {items.map(([k, label]) => <span key={k} className={`signal ${s[k] === true ? 'yes' : s[k] === false ? 'no' : 'neutral'}`} title={k}>{k} {label}</span>)}
      {s.chain && <span className="signal warn">Chain brand</span>}
      {s.reference_match && <span className="signal yes">Source cites HERE ID</span>}
    </div>
  );
}

export default function ComparisonDashboard({ datasets, user, onOpenMap }) {
  const supervisor = isSupervisor(user);
  const [datasetId, setDatasetId] = useState(datasets[0]?.id || '');
  const [types, setTypes] = useState(null);
  const [batches, setBatches] = useState(null);
  const [runs, setRuns] = useState(null);
  const [run, setRun] = useState(null);
  const [results, setResults] = useState(null);
  const [filter, setFilter] = useState({ outcome: '', q: '', page: 1 });
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState(null);
  const [detail, setDetail] = useState(null);
  const dataset = datasets.find((d) => d.id === datasetId);

  useEffect(() => { if (!datasetId && datasets[0]) setDatasetId(datasets[0].id); }, [datasets, datasetId]);
  useEffect(() => { api('/sources/types').then(setTypes).catch((e) => setNotice({ error: e.message })); }, []);
  const loadBatches = useCallback(() => {
    if (!dataset) return;
    setBatches(null);
    api(`/sources/batches?aoi=${encodeURIComponent(dataset.aoi)}`).then(setBatches).catch((e) => setNotice({ error: e.message }));
  }, [dataset]);
  useEffect(loadBatches, [loadBatches]);
  useEffect(() => {
    if (!datasetId) return;
    setRuns(null);
    setRun(null);
    api(`/comparison/runs?dataset_id=${datasetId}`).then((r) => { setRuns(r); setRun(r[0] || null); }).catch((e) => setNotice({ error: e.message }));
  }, [datasetId]);
  useEffect(() => {
    if (!run) { setResults(null); return; }
    const c = new AbortController();
    setResults(null);
    const t = setTimeout(() => {
      const params = new URLSearchParams({ page: filter.page, q: filter.q, ...(filter.outcome ? { outcome: filter.outcome } : {}) });
      api(`/comparison/runs/${run.id}/results?${params}`, { signal: c.signal }).then(setResults).catch((e) => { if (e.name !== 'AbortError') setNotice({ error: e.message }); });
    }, 200);
    return () => { clearTimeout(t); c.abort(); };
  }, [run, filter]);

  async function runComparison(force = false) {
    setBusy('run');
    setNotice(null);
    try {
      const r = await send('/comparison/runs', 'POST', { dataset_id: datasetId, force });
      setRun(r);
      setRuns((old) => [r, ...(old || []).filter((x) => x.id !== r.id)]);
      setNotice({ ok: r.reused ? 'Inputs are unchanged, so the previous comparison was reused.' : 'Comparison complete.' });
    } catch (e) {
      setNotice({ error: e.message });
    } finally {
      setBusy('');
    }
  }

  async function generateTasks(verification = false) {
    const count = run.stats.outcomes.verification_required || 0;
    if (verification && !window.confirm(`Create ${count.toLocaleString()} verification task${count === 1 ? '' : 's'} for HERE POIs that no permitted source observed?`)) return;
    setBusy(verification ? 'verify' : 'tasks');
    try {
      const r = await send(`/comparison/runs/${run.id}/tasks`, 'POST', verification ? { include: ['verification_required'] } : {});
      setNotice({ ok: `${r.created} ${verification ? 'verification' : 'review'} task${r.created === 1 ? '' : 's'} created · ${r.already_present} already existed · ${r.superseded} superseded.` });
    } catch (e) {
      setNotice({ error: e.message });
    } finally {
      setBusy('');
    }
  }

  if (!datasets.length) return <div className="ws-empty"><h3>Import a HERE baseline first</h3><p>Customer Data holds the baseline each comparison runs against.</p></div>;
  const s = run?.stats;
  return (
    <div className="platform-page">
      <div className="page-heading"><div><p className="eyebrow">DISCOVER · LINK · COMPARE</p><h1>Sources & comparison</h1>
        <p>Link permitted-source observations into one record per business and compare them with the HERE baseline.</p></div>
        <label className="inline-select">HERE baseline<select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.aoi} · {d.filename}</option>)}</select></label></div>
      {types && <div className="ws-notice policy"><Icon name="link" /> {types.policy}</div>}
      {notice?.error && <div className="ws-notice error" role="alert">{notice.error}</div>}
      {notice?.ok && <div className="ws-notice success" role="status">{notice.ok}</div>}

      <div className="section-title"><div><h2>Permitted sources · {dataset?.aoi}</h2><p>Every batch records its licence reference and permitted use.</p></div></div>
      {!batches ? <Loading>Loading sources…</Loading> : batches.length === 0 ? <div className="ws-empty compact"><p>No permitted sources imported for this AOI yet.</p></div> : (
        <div className="records-table-wrap short"><table className="records-table"><thead><tr><th>Source</th><th>Type</th><th>Licence / permission</th><th>Rows</th><th>Imported</th></tr></thead>
          <tbody>{batches.map((b) => <tr key={b.id}><td>{b.source_name}<small className="cell-sub">{b.filename}</small></td><td>{b.source_type_label}</td>
            <td title={b.permitted_use}>{b.license_reference}</td><td>{b.row_count.toLocaleString()}</td><td>{fmtDate(b.created_at)}</td></tr>)}</tbody></table></div>)}
      {supervisor && types && dataset && <SourceImport aoi={dataset.aoi} types={types.types} onDone={(b) => { setNotice({ ok: `${b.report.accepted} observations imported from ${b.source_name}${b.report.outside_aoi ? ` · ${b.report.outside_aoi} outside the AOI skipped` : ''}.` }); loadBatches(); }} />}

      <div className="section-title"><div><h2>HERE comparison</h2><p>{run ? `Run ${fmtDate(run.created_at)} · rules ${run.rules_version}` : 'No comparison run yet.'}</p></div>
        <div className="button-row">
          {supervisor && <button className="ws-button primary" onClick={() => runComparison(false)} disabled={busy || !batches?.length}>{busy === 'run' ? <Spinner size={14} /> : <Icon name="layers" />}{busy === 'run' ? 'Comparing…' : 'Run comparison'}</button>}
          {run && <button className="ws-button" onClick={() => onOpenMap(run.id)}><Icon name="map" />Map view</button>}
          {run && <a className="ws-button" href={`/api/comparison/runs/${run.id}/report.csv`}><Icon name="download" />Internal report</a>}
          {run && supervisor && <button className="ws-button" onClick={() => generateTasks(false)} disabled={!!busy}>{busy === 'tasks' ? <Spinner size={14} /> : <Icon name="copy" />}Generate review tasks</button>}
          {run && supervisor && <button className="ws-button" onClick={() => generateTasks(true)} disabled={!!busy || !s?.outcomes.verification_required}
            title="HERE POIs no permitted source observed">{busy === 'verify' ? <Spinner size={14} /> : <Icon name="target" />}Create verification tasks</button>}
        </div></div>
      {runs === null ? <Loading>Loading comparison…</Loading> : s && <>
        <div className="metrics-grid five">
          {[['HERE baseline', s.here_records], ['Source observations', s.observations], ['Unique POIs (masters)', s.masters],
            ['Duplicates removed', s.duplicates_removed], ['Seen in 2+ sources', s.multi_source_masters]].map(([label, value]) =>
            <div className="metric" key={label}><span>{label}</span><strong>{value.toLocaleString()}</strong></div>)}
        </div>
        <div className="outcome-grid">{Object.entries(OUTCOMES).map(([k, o]) =>
          <button key={k} className={`outcome-card ${filter.outcome === k ? 'active' : ''}`} style={{ '--o': o.color }}
            onClick={() => setFilter((f) => ({ ...f, outcome: f.outcome === k ? '' : k, page: 1 }))}>
            <strong>{(s.outcomes[k] || 0).toLocaleString()}</strong><span>{o.label}</span></button>)}</div>
        <div className="two-col">
          <section className="ops-panel"><h3>Source coverage & overlap</h3><table className="records-table compact"><thead><tr><th>Source</th><th>Observations</th><th>Matched HERE</th><th>Unmatched</th><th>Also in another source</th></tr></thead>
            <tbody>{Object.entries(s.by_source).map(([name, v]) => <tr key={name}><td>{name}</td><td>{v.observations}</td><td>{v.matched}</td><td>{v.unmatched}</td><td>{v.shared_with_other_sources}</td></tr>)}</tbody></table></section>
          <section className="ops-panel"><h3>HERE baseline by category (top 10)</h3><table className="records-table compact"><tbody>
            {(s.here_by_category || []).slice(0, 10).map(([name, n]) => <tr key={name}><td>{name}</td><td>{n.toLocaleString()}</td></tr>)}</tbody></table></section>
        </div>
        <section className="records-panel">
          <div className="records-filters"><label className="records-search"><Icon name="search" /><input placeholder="Search HERE place ID or discovered name…" value={filter.q}
            onChange={(e) => setFilter((f) => ({ ...f, q: e.target.value, page: 1 }))} /></label>
            {filter.outcome && <button className="ws-link" onClick={() => setFilter((f) => ({ ...f, outcome: '', page: 1 }))}>Clear “{OUTCOMES[filter.outcome].label}”</button>}</div>
          <div className="records-table-wrap">{!results ? <div className="table-loading"><Loading>Loading results…</Loading></div> :
            <table className="records-table"><thead><tr><th>Outcome</th><th>HERE</th><th>Discovered</th><th>Distance</th><th>Rule</th><th>Why</th><th /></tr></thead>
              <tbody>{results.results.map((r) => <tr key={r.id}>
                <td><span className="outcome-badge" style={{ '--o': OUTCOMES[r.outcome].color }}>{r.label}</span></td>
                <td>{r.here_name || '—'}<small className="cell-sub">{r.here_place_id}</small></td>
                <td>{r.master_name || '—'}<small className="cell-sub">{r.jsan_id}{r.sources.length ? ` · ${r.sources.join(', ')}` : ''}</small></td>
                <td>{r.distance_m != null ? `${r.distance_m} m · ${r.band}` : '—'}</td><td>{r.decision_rule || '—'}</td>
                <td className="why">{r.reasons[0]}{r.changed_fields.length > 0 && <small className="cell-sub">Changed: {r.changed_fields.join(', ')}</small>}</td>
                <td><button className="ws-link" onClick={() => setDetail(r.id)}>Explain ↗</button></td></tr>)}</tbody></table>}</div>
          {results && <div className="records-pagination"><span>{results.total.toLocaleString()} results · page {filter.page} of {Math.max(1, Math.ceil(results.total / results.page_size))}</span>
            <div><button className="ws-button" disabled={filter.page <= 1} onClick={() => setFilter((f) => ({ ...f, page: f.page - 1 }))}>Previous</button>
              <button className="ws-button" disabled={filter.page * results.page_size >= results.total} onClick={() => setFilter((f) => ({ ...f, page: f.page + 1 }))}>Next</button></div></div>}
        </section>
      </>}
      {detail && <ResultDetail id={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
