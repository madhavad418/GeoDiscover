import { useCallback, useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { api, send } from '../lib/api.js';
import { fmtDate, hasRole } from '../lib/platform.js';

const KIND_LABEL = { new: 'NEW POIs (customer template)', update: 'UPDATED POIs (customer template)', delete: 'DELETED POIs (customer template)',
  manifest: 'Delivery manifest', qc_checklist: 'Supplier QC checklist', category_mapping: 'Category mapping', reconciliation: 'Reconciliation report',
  package: 'Customer package (.zip)' };

export default function Delivery({ datasets, user }) {
  const [datasetId, setDatasetId] = useState(datasets[0]?.id || '');
  const [report, setReport] = useState(null);
  const [snapshots, setSnapshots] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const canBuild = hasRole(user, 'ops_manager', 'qc_lead');

  const load = useCallback(() => {
    if (!datasetId) return;
    setReport(null);
    setSnapshots(null);
    api(`/delivery/datasets/${datasetId}/preflight`).then(setReport).catch((e) => setNotice({ error: e.message }));
    api(`/delivery/datasets/${datasetId}/snapshots`).then(setSnapshots).catch((e) => setNotice({ error: e.message }));
  }, [datasetId]);
  useEffect(load, [load]);

  async function build() {
    setBusy(true);
    setNotice(null);
    try {
      const s = await send(`/delivery/datasets/${datasetId}/snapshots`, 'POST');
      setNotice({ ok: `Package v${s.version} built: ${s.counts.new} new, ${s.counts.update} update, ${s.counts.delete} delete.` });
      load();
    } catch (e) {
      setNotice({ error: e.message, issues: e.issues });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="platform-page">
      <div className="page-heading"><div><p className="eyebrow">CUSTOMER DELIVERY</p><h1>Delivery & QC gate</h1>
        <p>Only independently QC-approved records that pass every Blocker check reach the HERE templates.</p></div>
        <label className="inline-select">HERE baseline<select value={datasetId} onChange={(e) => setDatasetId(e.target.value)}>
          {datasets.map((d) => <option key={d.id} value={d.id}>{d.aoi} · {d.filename}</option>)}</select></label></div>
      {notice?.error && <div className="ws-notice error" role="alert">{notice.error}{notice.issues?.length > 0 && <ul>{notice.issues.map((i) => <li key={i}>{i}</li>)}</ul>}</div>}
      {notice?.ok && <div className="ws-notice success" role="status">{notice.ok}</div>}
      {!report ? <Loading>Running delivery checks…</Loading> : <>
        <div className="metrics-grid five">
          {[['QC-approved decisions', report.approved_total], ['NEW ready', report.counts.new], ['UPDATE ready', report.counts.update],
            ['DELETE ready', report.counts.delete], ['Withheld (Blockers)', report.held_back.length]].map(([l, v]) => <div className="metric" key={l}><span>{l}</span><strong>{v}</strong></div>)}
        </div>
        {report.template_issues.length > 0 && <div className="ws-notice error">{report.template_issues.map((i) => <div key={i}>{i}</div>)}</div>}
        <div className="button-row">{canBuild && <button className="ws-button primary" disabled={busy || !report.can_build} onClick={build}>
          {busy ? <Spinner size={14} /> : <Icon name="download" />}{busy ? 'Building…' : 'Build delivery package'}</button>}
          {!report.can_build && <span className="muted">Nothing can be exported until records are QC-approved and pass the Blocker checks.</span>}</div>
        {report.held_back.length > 0 && <section className="ops-panel"><h3>Withheld records · {report.held_back.length}</h3>
          <table className="records-table compact"><thead><tr><th>Record</th><th>Action</th><th>Blockers</th></tr></thead>
            <tbody>{report.held_back.map((h, i) => <tr key={i}><td>{h.record}</td><td>{h.action}</td><td>{h.reason}</td></tr>)}</tbody></table></section>}
        {report.majors.length > 0 && <section className="ops-panel"><h3>Major issues to correct or disclose · {report.majors.length}</h3>
          <table className="records-table compact"><thead><tr><th>Record</th><th>Action</th><th>Issue</th></tr></thead>
            <tbody>{report.majors.map((m, i) => <tr key={i}><td>{m.record}</td><td>{m.action}</td><td>{m.issue}</td></tr>)}</tbody></table></section>}
        <details className="ops-panel"><summary>Template mapping assumptions (to confirm with HERE)</summary><ul>{report.assumptions.map((a) => <li key={a}>{a}</li>)}</ul></details>
      </>}
      <div className="section-title"><div><h2>Frozen delivery snapshots</h2><p>Every build is stored with checksums; files never change after they are built.</p></div></div>
      {!snapshots ? <Loading>Loading snapshots…</Loading> : snapshots.length === 0 ? <div className="ws-empty compact"><p>No packages built yet.</p></div> :
        snapshots.map((s) => <section className="ops-panel" key={s.id}><h3>v{s.version} · {fmtDate(s.created_at)} · {s.counts.new} new / {s.counts.update} update / {s.counts.delete} delete</h3>
          <table className="records-table compact"><thead><tr><th>File</th><th>Contents</th><th>Rows</th><th>Audience</th><th>SHA-256</th><th /></tr></thead>
            <tbody>{s.files.map((f) => <tr key={f.id}><td>{f.filename}</td><td>{KIND_LABEL[f.kind] || f.kind}</td><td>{f.row_count}</td>
              <td>{f.customer_facing ? 'Customer' : <b>Internal only</b>}</td><td className="mono small" title={f.sha256}>{f.sha256.slice(0, 12)}…</td>
              <td><a className="ws-link" href={`/api/delivery/files/${f.id}`}>Download</a></td></tr>)}</tbody></table></section>)}
    </div>
  );
}
