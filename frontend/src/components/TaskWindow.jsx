import { useCallback, useEffect, useMemo, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { Signals } from './ComparisonDashboard.jsx';
import { api, send } from '../lib/api.js';
import { DECISIONS, OUTCOMES, fmtDate, today } from '../lib/platform.js';

const CORE = ['name', 'transliteration', 'category_code', 'poi_status', 'latitude', 'longitude', 'routing_latitude', 'routing_longitude',
  'address', 'street_name', 'house_number', 'unit', 'postal_code', 'phone', 'website', 'opening_hours'];
const SCORES = [[1, 'Full (1.0)'], [0.8, 'Strong (0.8)'], [0.5, 'Partial (0.5)'], [0, 'Absent (0)']];
const SUPPORTS = { existence: 'Business exists', attribute: 'Supports attribute change', closure: 'Closure / non-existence', liveness: 'Business is active' };
const SOURCE_TO_EVIDENCE = { official_website: 'official_website', store_locator: 'official_website', official_social: 'official_social',
  field_observation: 'field_observation', licensed_directory: 'competitor_map_link', licensed_vendor: 'competitor_map_link', other_permitted: 'competitor_map_link' };
/** Evidence item pre-filled from a linked source observation. */
const evidenceFrom = (o) => ({ type: SOURCE_TO_EVIDENCE[o.source.source_type] || 'competitor_map_link', supports: 'existence', score: 1,
  url: o.source_url || o.website || '', observed_on: o.observed_on || '', source_observation_id: o.id, description: `${o.source.source_name}: ${o.name}` });
const show = (v) => (v == null || v === '' ? '—' : Array.isArray(v) ? v.join(', ') : String(v));
const same = (a, b) => String(a ?? '').trim() === String(b ?? '').trim();

function Panel({ title, children, actions }) {
  return <section className="task-panel"><header><h3>{title}</h3>{actions}</header>{children}</section>;
}

function HerePanel({ ctx }) {
  const h = ctx.here;
  if (!h) return <Panel title="HERE existing"><p className="muted">No HERE record is linked. Check the nearby POIs before calling this NEW.</p><Nearby ctx={ctx} /></Panel>;
  const raw = h.raw || {};
  return (
    <Panel title="HERE existing">
      <dl className="kv-list">
        <dt>Place ID</dt><dd>{h.place_id}</dd><dt>Name</dt><dd>{h.name}{raw.name2 ? <small className="cell-sub">{raw.name2}</small> : null}</dd>
        <dt>Category</dt><dd>{h.category_name} <small className="cell-sub">{h.category_code}</small></dd><dt>Address</dt><dd>{show(h.address)}</dd>
        <dt>Display</dt><dd>{h.latitude.toFixed(6)}, {h.longitude.toFixed(6)}</dd><dt>Routing</dt><dd>{h.routing_latitude ? `${h.routing_latitude}, ${h.routing_longitude}` : '—'}</dd>
        <dt>Phone</dt><dd>{show(raw.phone_numbers)}</dd><dt>Website</dt><dd>{show(raw.webaddress)}</dd><dt>Hours</dt><dd className="small">{show(raw.opening_hours)}</dd>
        <dt>Chain</dt><dd>{show(raw.chainname)}</dd><dt>Status</dt><dd>{show(raw.status)}</dd>
      </dl>
      <Nearby ctx={ctx} />
    </Panel>
  );
}

function Nearby({ ctx }) {
  if (!ctx.nearby_here.length) return null;
  return (<details className="nearby"><summary>Nearby HERE POIs within 120 m · {ctx.nearby_here.length}</summary>
    <ul>{ctx.nearby_here.map((n) => <li key={n.place_id}><b>{n.name}</b> · {n.category_name} · {n.distance_m} m <small>{n.place_id}</small></li>)}</ul></details>);
}

function SourcePanel({ ctx, onUse }) {
  const e = ctx.explanation;
  return (
    <Panel title="GeoDiscover">
      {ctx.master && <p className="master-line"><b>{ctx.master.jsan_id}</b> · {ctx.master.name} · {ctx.observations.length} linked source record{ctx.observations.length === 1 ? '' : 's'}</p>}
      {ctx.observations.length === 0 && <p className="muted">No permitted source observed this POI.</p>}
      {ctx.observations.map((o) => (
        <article className="obs-card" key={o.id}>
          <header><b>{o.source.source_name}</b><span>{o.source.source_type_label}</span></header>
          <dl className="kv-list small">
            <dt>Record</dt><dd>{o.source_record_id}</dd><dt>Name</dt><dd>{o.name}{o.alt_names?.length ? <small className="cell-sub">{o.alt_names.join(' · ')}</small> : null}</dd>
            <dt>Category</dt><dd>{show(o.category_name || o.category_code)}</dd><dt>Address</dt><dd>{show(o.address)}</dd>
            <dt>Position</dt><dd>{o.latitude.toFixed(6)}, {o.longitude.toFixed(6)}</dd><dt>Phone</dt><dd>{show(o.phones)}</dd>
            <dt>Website</dt><dd>{o.website ? <a href={o.website} target="_blank" rel="noopener noreferrer">{o.website}</a> : '—'}</dd>
            <dt>Status</dt><dd>{o.business_status}</dd><dt>Observed</dt><dd>{show(o.observed_on)} · retrieved {show(o.retrieved_on)}</dd>
            <dt>Licence</dt><dd className="small">{o.source.license_reference}</dd>
          </dl>
          <div className="button-row">{o.source_url && <a className="ws-link" href={o.source_url} target="_blank" rel="noopener noreferrer">Source page ↗</a>}
            {onUse && <button className="ws-link" onClick={() => onUse(o)}>Add as evidence</button>}</div>
        </article>))}
      {e.match && <><h4>Match signals</h4><Signals s={e.match} /></>}
      {e.candidates?.length > 1 && <details className="nearby"><summary>Possible HERE matches · {e.candidates.length}</summary>
        <ul>{e.candidates.map((c) => <li key={c.place_id}><b>{c.here_name}</b> · {c.place_id} · {c.level}<Signals s={c} /></li>)}</ul></details>}
      {e.master?.conflicts?.length > 0 && <div className="ws-notice">Sources disagree: {e.master.conflicts.map((c) => `${c.field} (${c.values.join(' / ')})`).join('; ')}</div>}
    </Panel>
  );
}

function ReferencePanel({ ctx }) {
  return (
    <Panel title="Source & evidence references">
      <p className="muted small">Map providers open in their own viewers. Nothing is copied from them into HERE deliverables.</p>
      <ul className="link-list">{ctx.reference_links.map((l) => <li key={l.url}><a href={l.url} target="_blank" rel="noopener noreferrer"><Icon name="external" size={13} />{l.label}</a></li>)}</ul>
      {ctx.field.length > 0 && <><h4>Field observations</h4>{ctx.field.map((f) => <div key={f.id} className="obs-card"><header><b>{f.status.replace(/_/g, ' ')}</b><span>{f.verifier} · {fmtDate(f.observed_at)}</span></header>
        <dl className="kv-list small"><dt>Signage</dt><dd>{show(f.data.signage_name)}</dd><dt>GPS</dt><dd>{f.data.gps_latitude}, {f.data.gps_longitude} (±{f.data.gps_accuracy_m} m)</dd>
          <dt>Unit</dt><dd>{show(f.data.unit)}</dd><dt>Unresolved</dt><dd>{show(f.data.unresolved)}</dd><dt>Remarks</dt><dd>{show(f.data.remarks)}</dd>
          <dt>Photos</dt><dd>{f.data.photos?.map((p) => <a key={p} href={p} target="_blank" rel="noopener noreferrer">photo ↗ </a>)}</dd></dl></div>)}</>}
    </Panel>
  );
}

function EvidenceEditor({ evidence, setEvidence, options, attributeChoices }) {
  const update = (i, patch) => setEvidence((list) => list.map((e, n) => (n === i ? { ...e, ...patch } : e)));
  return (
    <div className="evidence-editor">
      {evidence.map((e, i) => (
        <div className="evidence-row" key={i}>
          <select value={e.type} onChange={(ev) => update(i, { type: ev.target.value })}>{Object.entries(options.evidence_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select value={e.supports} onChange={(ev) => update(i, { supports: ev.target.value })}>{Object.entries(SUPPORTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
          <input placeholder="URL (or describe below)" value={e.url || ''} onChange={(ev) => update(i, { url: ev.target.value })} />
          <input type="date" value={e.observed_on || ''} max={today()} onChange={(ev) => update(i, { observed_on: ev.target.value })} title="Observed / published date" />
          <select value={e.score ?? 1} onChange={(ev) => update(i, { score: +ev.target.value })} title="Rubric score">{SCORES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          <button className="icon-btn" onClick={() => setEvidence((list) => list.filter((_, n) => n !== i))} aria-label="Remove evidence"><Icon name="trash" /></button>
          <input className="wide" placeholder="Description (what this shows)" value={e.description || ''} onChange={(ev) => update(i, { description: ev.target.value })} />
          {e.supports === 'attribute' && <div className="field-chips">{attributeChoices.map((f) => (
            <label key={f}><input type="checkbox" checked={(e.fields || []).includes(f)}
              onChange={() => update(i, { fields: (e.fields || []).includes(f) ? e.fields.filter((x) => x !== f) : [...(e.fields || []), f] })} />{options.attributes[f]}</label>))}
            {attributeChoices.length === 0 && <span className="muted small">Mark attributes as corrected first.</span>}</div>}
          {e.type === 'pos_confirmation' && e.supports === 'closure' && <div className="field-chips">
            <label>Inactive months<input type="number" min={0} value={e.pos_inactive_months || ''} onChange={(ev) => update(i, { pos_inactive_months: +ev.target.value })} /></label>
            <label>Prior active months<input type="number" min={0} value={e.pos_prior_active_months || ''} onChange={(ev) => update(i, { pos_prior_active_months: +ev.target.value })} /></label></div>}
        </div>))}
      <button className="ws-button" onClick={() => setEvidence((list) => [...list, { type: 'official_website', supports: 'existence', score: 1, observed_on: today() }])}><Icon name="link" />Add evidence</button>
    </div>
  );
}

// Comparison difference -> review attribute(s) it proposes to change.
const DIFF_FIELDS = { name: ['name'], category: ['category_code'], phone: ['phone'], website: ['website'], opening_hours: ['opening_hours'],
  address: ['address'], location: ['latitude', 'longitude'] };

function initialAttributes(ctx, previous) {
  const out = {};
  Object.entries(ctx.attributes).forEach(([field, a]) => {
    const prior = previous?.attributes?.[field];
    const final = prior ? prior.final : a.default;
    out[field] = prior ? { ...prior } : { final: final ?? '', status: final == null || final === '' ? 'unavailable' : a.here != null && a.here !== '' && same(final, a.here) ? 'confirmed' : 'corrected', auto: true };
  });
  if (!previous) {
    // Pre-fill the corrections the comparison proposed; the reviewer confirms or changes them.
    for (const diff of ctx.explanation.changed_fields || []) {
      for (const field of DIFF_FIELDS[diff.field] || []) {
        const value = field === 'latitude' ? ctx.master?.latitude : field === 'longitude' ? ctx.master?.longitude : ctx.attributes[field]?.observed[0]?.value;
        if (value != null && value !== '') out[field] = { final: String(value), status: 'corrected', auto: true, proposed: true };
      }
    }
  }
  return out;
}

function ReviewForm({ ctx, onDone, evidence, setEvidence }) {
  const previous = ctx.reviews[ctx.reviews.length - 1];
  const reclass = /Reclassify to (\w[\w ]*):/.exec(ctx.task.note || '')?.[1]?.toLowerCase().replace(' ', '_');
  const [decision, setDecision] = useState(reclass || previous?.decision || ({ potential_new: 'new', potential_update: 'update', potential_delete: 'delete', verification_required: 'no_change' }[ctx.outcome] || ''));
  const [attrs, setAttrs] = useState(() => initialAttributes(ctx, previous));
  const [form, setForm] = useState({ verification_date: previous?.verification_date || today(), delete_reason: previous?.delete_reason || '',
    duplicate_of: previous?.duplicate_of || '', field_issue: '', remarks: '', here_place_id: previous?.here_place_id || ctx.here?.place_id || '' });
  const [showAll, setShowAll] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const setAttr = (field, patch) => setAttrs((a) => {
    const next = { ...a[field], ...patch };
    if ('final' in patch && next.auto !== false && !('status' in patch)) {
      const here = ctx.attributes[field].here;
      next.status = patch.final === '' ? 'unavailable' : here != null && same(patch.final, here) ? 'confirmed' : 'corrected';
    }
    if ('status' in patch) next.auto = false;
    return { ...a, [field]: next };
  });
  const corrected = Object.entries(attrs).filter(([, v]) => v.status === 'corrected').map(([f]) => f);
  const fields = showAll ? Object.keys(ctx.attributes) : CORE;
  const targets = [...new Map([...(ctx.here ? [[ctx.here.place_id, ctx.here.name]] : []), ...(ctx.explanation.candidates || []).map((c) => [c.place_id, c.here_name])]).entries()];

  async function submit() {
    setBusy(true);
    setProblem(null);
    const attributes = Object.fromEntries(Object.entries(attrs).filter(([, v]) => v.status !== 'unavailable' || v.final)
      .map(([f, v]) => [f, { final: ['latitude', 'longitude', 'routing_latitude', 'routing_longitude'].includes(f) && v.final !== '' ? +v.final : v.final, status: v.status }]));
    try {
      await send(`/tasks/${ctx.task.id}/review`, 'POST', { decision, attributes, evidence, ...form,
        delete_reason: form.delete_reason || null, duplicate_of: form.duplicate_of || null, here_place_id: form.here_place_id || null,
        field_issue: form.field_issue || null, verification_date: form.verification_date || null });
      onDone('Decision submitted for independent QC.');
    } catch (e) {
      setProblem(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="task-action">
      <h3>Review decision</h3>
      {ctx.task.note && <div className="ws-notice">QC note: {ctx.task.note}</div>}
      <div className="decision-row">{Object.entries(DECISIONS).map(([k, v]) => (
        <label key={k} className={`decision ${decision === k ? 'active' : ''}`}><input type="radio" name="decision" checked={decision === k} onChange={() => setDecision(k)} />{v}</label>))}</div>
      {['update', 'delete'].includes(decision) && targets.length > 1 && <label className="inline-select">HERE record this applies to<select value={form.here_place_id} onChange={set('here_place_id')}>
        <option value="">Choose…</option>{targets.map(([id, name]) => <option key={id} value={id}>{name} · {id}</option>)}</select></label>}
      {['new', 'update', 'no_change'].includes(decision) && <>
        <table className="records-table attr-table"><thead><tr><th>Attribute</th><th>HERE</th><th>Discovered (source)</th><th>Final value</th><th>Status</th></tr></thead>
          <tbody>{fields.map((f) => { const a = ctx.attributes[f]; const v = attrs[f]; return (
            <tr key={f} className={v.status}><td>{a.label}{v.proposed && <small className="cell-sub">proposed by comparison</small>}</td><td className="small">{show(a.here)}</td>
              <td className="small">{a.observed.map((o) => <button key={o.observation_id} className="chip-btn" title="Use this value" onClick={() => setAttr(f, { final: String(o.value) })}>{show(o.value)} · {o.source}</button>)}</td>
              <td><input value={v.final ?? ''} onChange={(e) => setAttr(f, { final: e.target.value })} /></td>
              <td><select value={v.status} onChange={(e) => setAttr(f, { status: e.target.value })}>{['confirmed', 'corrected', 'conflict', 'unavailable'].map((s) => <option key={s}>{s}</option>)}</select></td></tr>); })}</tbody></table>
        <button className="ws-link" onClick={() => setShowAll((s) => !s)}>{showAll ? 'Show core attributes' : 'Show all attributes (admin levels, RT/RW, contact…)'}</button></>}
      {decision === 'delete' && <div className="form-grid">
        <label>Delete reason<select value={form.delete_reason} onChange={set('delete_reason')}><option value="">Choose…</option>
          {Object.entries(ctx.options.delete_reasons).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        {form.delete_reason === 'duplicate' && <label>HERE place ID that stays<input value={form.duplicate_of} onChange={set('duplicate_of')} /></label>}
        <p className="muted small wide">Deletion needs positive closure evidence: E1 (imagery ≤ 12 months or POS inactivity), or ≥ 70 points from two of official website (60), social (35), competitor map (10). Absence never counts; any active-business evidence blocks it.</p></div>}
      {decision === 'field_review' && <label className="wide-label">What exactly must the field verifier check?<textarea rows={2} value={form.field_issue} onChange={set('field_issue')} /></label>}
      {['new', 'update', 'delete', 'no_change'].includes(decision) && <>
        <h4>Evidence</h4>
        <EvidenceEditor evidence={evidence} setEvidence={setEvidence} options={ctx.options} attributeChoices={corrected} />
        <label className="inline-select">Verification date<input type="date" max={today()} value={form.verification_date} onChange={set('verification_date')} /></label></>}
      <label className="wide-label">Remarks{decision === 'hold' ? ' (required)' : ''}<textarea rows={2} value={form.remarks} onChange={set('remarks')} /></label>
      {problem && <div className="ws-notice error" role="alert">{problem.message}{problem.issues?.length > 0 && <ul>{problem.issues.map((i) => <li key={i}>{i}</li>)}</ul>}</div>}
      <div className="button-row"><button className="ws-button primary" disabled={busy || !decision} onClick={submit}>{busy && <Spinner size={14} />}{busy ? 'Checking…' : 'Submit decision'}</button></div>
    </section>
  );
}

function QcPanel({ ctx, onDone }) {
  const review = ctx.reviews[ctx.reviews.length - 1];
  const [action, setAction] = useState('approve');
  const [reclassify, setReclassify] = useState('');
  const [remarks, setRemarks] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(null);
  if (!review) return <p className="ws-notice">No review is attached to this QC task.</p>;
  const changes = Object.entries(review.attributes || {}).filter(([, v]) => v.status !== 'confirmed');

  async function submit() {
    setBusy(true);
    setProblem(null);
    try {
      await send(`/tasks/${ctx.task.id}/qc`, 'POST', { action, remarks, reclassified_to: action === 'reclassify' ? reclassify : null });
      onDone(`QC decision recorded: ${action}.`);
    } catch (e) {
      setProblem(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="task-action">
      <h3>Independent QC</h3>
      {!ctx.independent && <div className="ws-notice error">You reviewed or field-verified this record, so you can't QC it.</div>}
      <dl className="kv-list"><dt>Reviewer decision</dt><dd><b>{DECISIONS[review.decision]}</b> by {review.reviewer} · {fmtDate(review.at)}</dd>
        <dt>HERE record</dt><dd>{show(review.here_place_id)}</dd><dt>Verification date</dt><dd>{show(review.verification_date)}</dd>
        <dt>Confidence</dt><dd>{review.rule_check?.confidence ? `${review.rule_check.confidence.score}/10 (${review.rule_check.confidence.band}, raw ${review.rule_check.confidence.raw}) — advisory` : '—'}</dd>
        {review.rule_check?.closure && <><dt>Closure check</dt><dd>Rule {review.rule_check.closure.rule} · tiers {review.rule_check.closure.tiers.join(', ') || 'none'} · weighted {review.rule_check.closure.weighted_score}</dd></>}
        {review.delete_reason && <><dt>Delete reason</dt><dd>{ctx.options.delete_reasons[review.delete_reason]} {review.duplicate_of ? `(keeps ${review.duplicate_of})` : ''}</dd></>}
        {review.field_issue && <><dt>Field issue</dt><dd>{review.field_issue}</dd></>}
        <dt>Remarks</dt><dd>{show(review.remarks)}</dd></dl>
      {changes.length > 0 && <table className="records-table compact"><thead><tr><th>Attribute</th><th>HERE</th><th>Final</th><th>Status</th></tr></thead>
        <tbody>{changes.map(([f, v]) => <tr key={f} className={v.status}><td>{ctx.options.attributes[f]}</td><td>{show(ctx.attributes[f]?.here)}</td><td>{show(v.final)}</td><td>{v.status}</td></tr>)}</tbody></table>}
      <h4>Evidence considered · {review.evidence.length}</h4>
      <ul className="evidence-list">{review.evidence.map((e, i) => <li key={i}><b>{ctx.options.evidence_types[e.type]}</b> · {SUPPORTS[e.supports]}{e.fields?.length ? ` (${e.fields.join(', ')})` : ''} · score {e.score ?? '—'} · {show(e.observed_on)}
        {e.url && <> · <a href={e.url} target="_blank" rel="noopener noreferrer">open ↗</a></>}{e.description && <small className="cell-sub">{e.description}</small>}</li>)}</ul>
      <div className="decision-row">{[['approve', 'Approve'], ['reject', 'Reject'], ['return', 'Return for rework'], ['reclassify', 'Reclassify'], ['field', 'Request field verification'], ['hold', 'Hold / escalate']].map(([k, v]) => (
        <label key={k} className={`decision ${action === k ? 'active' : ''}`}><input type="radio" name="qc" checked={action === k} onChange={() => setAction(k)} />{v}</label>))}</div>
      {action === 'reclassify' && <label className="inline-select">Reclassify to<select value={reclassify} onChange={(e) => setReclassify(e.target.value)}><option value="">Choose…</option>
        {['new', 'update', 'delete', 'no_change'].filter((d) => d !== review.decision).map((d) => <option key={d} value={d}>{DECISIONS[d]}</option>)}</select></label>}
      <label className="wide-label">QC remarks{action !== 'approve' ? ' (required)' : ''}<textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} /></label>
      {problem && <div className="ws-notice error" role="alert">{problem.message}{problem.issues?.length > 0 && <ul>{problem.issues.map((i) => <li key={i}>{i}</li>)}</ul>}</div>}
      <div className="button-row"><button className="ws-button primary" disabled={busy || !ctx.independent} onClick={submit}>{busy && <Spinner size={14} />}Record QC decision</button></div>
    </section>
  );
}

function FieldForm({ ctx, onDone }) {
  const [f, setF] = useState({ status: 'existing', observed_at: new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16),
    gps_latitude: '', gps_longitude: '', gps_accuracy_m: '', display_latitude: '', display_longitude: '', routing_latitude: '', routing_longitude: '',
    signage_name: '', category: '', address: '', unit: '', parent: '', phone: '', opening_hours: '', photos: '', remarks: '' });
  const [unresolved, setUnresolved] = useState([]);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState(null);
  const set = (k) => (e) => setF((s) => ({ ...s, [k]: e.target.value }));
  const num = (v) => (v === '' ? null : +v);

  function locate() {
    navigator.geolocation?.getCurrentPosition((p) => setF((s) => ({ ...s, gps_latitude: p.coords.latitude.toFixed(7), gps_longitude: p.coords.longitude.toFixed(7),
      gps_accuracy_m: Math.round(p.coords.accuracy) })), (err) => setProblem({ message: `Location unavailable: ${err.message}` }), { enableHighAccuracy: true, timeout: 15000 });
  }

  async function submit() {
    setBusy(true);
    setProblem(null);
    try {
      await send(`/tasks/${ctx.task.id}/field`, 'POST', { ...f, observed_at: new Date(f.observed_at).toISOString(),
        ...Object.fromEntries(['gps_latitude', 'gps_longitude', 'gps_accuracy_m', 'display_latitude', 'display_longitude', 'routing_latitude', 'routing_longitude'].map((k) => [k, num(f[k])])),
        photos: f.photos.split(/\s+/).filter(Boolean), unresolved });
      onDone('Field observation saved and returned to independent QC.');
    } catch (e) {
      setProblem(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="task-action">
      <h3>Field verification</h3>
      <div className="ws-notice">Check: {ctx.task.note || 'see the reviewer notes'}</div>
      <div className="form-grid">
        <label>Status<select value={f.status} onChange={set('status')}>{ctx.options.field_statuses.map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}</select></label>
        <label>Observed at<input type="datetime-local" value={f.observed_at} onChange={set('observed_at')} /></label>
        <label>GPS latitude<input value={f.gps_latitude} onChange={set('gps_latitude')} /></label>
        <label>GPS longitude<input value={f.gps_longitude} onChange={set('gps_longitude')} /></label>
        <label>GPS accuracy (m)<input value={f.gps_accuracy_m} onChange={set('gps_accuracy_m')} /></label>
        <button className="ws-button" type="button" onClick={locate}><Icon name="pin" />Use my location</button>
        <label>Display point lat<input value={f.display_latitude} onChange={set('display_latitude')} /></label>
        <label>Display point lon<input value={f.display_longitude} onChange={set('display_longitude')} /></label>
        <label>Entrance / routing lat<input value={f.routing_latitude} onChange={set('routing_latitude')} /></label>
        <label>Entrance / routing lon<input value={f.routing_longitude} onChange={set('routing_longitude')} /></label>
        <label>Visible signage name<input value={f.signage_name} onChange={set('signage_name')} /></label>
        <label>Category / identity<input value={f.category} onChange={set('category')} /></label>
        <label className="wide">Address<input value={f.address} onChange={set('address')} /></label>
        <label>Shop / stall number<input value={f.unit} onChange={set('unit')} /></label>
        <label>Parent market / building<input value={f.parent} onChange={set('parent')} /></label>
        <label>Phone<input value={f.phone} onChange={set('phone')} /></label>
        <label>Opening hours<input value={f.opening_hours} onChange={set('opening_hours')} /></label>
        <label className="wide">Geotagged photo URLs (one per line, where permitted)<textarea rows={2} value={f.photos} onChange={set('photos')} /></label>
      </div>
      <p className="small">Could not be established (record it rather than guessing):</p>
      <div className="field-chips">{['name', 'category', 'address', 'phone', 'opening_hours', 'display_point', 'routing_point'].map((u) => (
        <label key={u}><input type="checkbox" checked={unresolved.includes(u)} onChange={() => setUnresolved((s) => (s.includes(u) ? s.filter((x) => x !== u) : [...s, u]))} />{u.replace('_', ' ')}</label>))}</div>
      <label className="wide-label">Remarks<textarea rows={2} value={f.remarks} onChange={set('remarks')} /></label>
      {problem && <div className="ws-notice error" role="alert">{problem.message}</div>}
      <div className="button-row"><button className="ws-button primary" disabled={busy} onClick={submit}>{busy && <Spinner size={14} />}Submit field observation</button></div>
    </section>
  );
}

export default function TaskWindow({ taskId, user, onBack }) {
  const [ctx, setCtx] = useState(null);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const [busy, setBusy] = useState(false);
  const [evidence, setEvidence] = useState([]);
  const load = useCallback(() => api(`/tasks/${taskId}`).then((c) => {
    setCtx(c);
    setEvidence((current) => (current.length ? current : c.reviews[c.reviews.length - 1]?.evidence || []));
  }).catch((e) => setError(e.message)), [taskId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (ctx && ctx.task.assigned_to === user.id && ctx.task.status === 'assigned') send(`/tasks/${taskId}/start`, 'POST').then(load).catch(() => {});
  }, [ctx, taskId, user.id, load]);
  const mine = ctx && ctx.task.assigned_to === user.id && ['assigned', 'in_progress'].includes(ctx.task.status);
  const outcome = useMemo(() => ctx && OUTCOMES[ctx.outcome], [ctx]);

  async function release() {
    setBusy(true);
    try { await send(`/tasks/${taskId}/release`, 'POST'); onBack(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  async function resume() {
    setBusy(true);
    try { await send(`/tasks/${taskId}/resume`, 'POST'); await load(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  if (error) return <div className="ws-notice error" role="alert">{error}<button className="ws-link" onClick={onBack}>Back</button></div>;
  if (!ctx) return <Loading>Loading task…</Loading>;
  return (
    <div className="platform-page task-window">
      <div className="page-heading"><div><p className="eyebrow">{ctx.task.ref} · {ctx.task.queue_label}</p>
        <h1>{ctx.master?.name || ctx.here?.name}</h1>
        <p><span className="outcome-badge" style={{ '--o': outcome.color }}>{ctx.outcome_label}</span> {ctx.task.aoi} · status {ctx.task.status.replace('_', ' ')} · assigned to {ctx.task.assignee || 'nobody'}</p></div>
        <div className="button-row">{mine && <button className="ws-button" onClick={release} disabled={busy}>Release to queue</button>}
          {ctx.task.status === 'on_hold' && ctx.task.assigned_to === user.id && <button className="ws-button" onClick={resume} disabled={busy}>Resume</button>}
          <button className="ws-button" onClick={onBack}><Icon name="x" />Back to my work</button></div></div>
      {done && <div className="ws-notice success" role="status">{done} <button className="ws-link" onClick={onBack}>Back to my work</button></div>}
      <ul className="reason-list">{ctx.explanation.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      <div className="task-grid">
        <HerePanel ctx={ctx} />
        <SourcePanel ctx={ctx} onUse={mine && ctx.task.kind === 'review' ? (o) => setEvidence((list) => [...list, evidenceFrom(o)]) : null} />
        <ReferencePanel ctx={ctx} />
      </div>
      {!done && mine && ctx.task.kind === 'review' && <ReviewForm ctx={ctx} evidence={evidence} setEvidence={setEvidence} onDone={(m) => { setDone(m); load(); }} />}
      {!done && mine && ctx.task.kind === 'qc' && <QcPanel ctx={ctx} onDone={(m) => { setDone(m); load(); }} />}
      {!done && mine && ctx.task.kind === 'field' && <FieldForm ctx={ctx} onDone={(m) => { setDone(m); load(); }} />}
      {!mine && !done && <p className="ws-notice">Read-only: {ctx.task.status === 'completed' ? 'this task is complete.' : 'this task is not assigned to you.'}</p>}
      <details className="ops-panel"><summary>Full history · {ctx.history.length} events</summary>
        <table className="records-table compact"><thead><tr><th>When</th><th>Task</th><th>Event</th><th>Status</th><th>By</th><th>Details</th></tr></thead>
          <tbody>{ctx.history.map((h, i) => <tr key={i}><td>{fmtDate(h.at)}</td><td>T-{String(h.task_id).padStart(6, '0')}</td><td>{h.event}</td>
            <td>{h.from} → {h.to}</td><td>{h.actor || 'system'}</td><td className="small">{Object.entries(h.details || {}).map(([k, v]) => `${k}: ${v}`).join(' · ')}</td></tr>)}</tbody></table></details>
    </div>
  );
}
