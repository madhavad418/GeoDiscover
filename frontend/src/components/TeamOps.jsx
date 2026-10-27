import { useCallback, useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { api, send } from '../lib/api.js';
import { fmtDate, hasRole } from '../lib/platform.js';

function Metrics() {
  const [m, setM] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { api('/tasks/metrics/overview').then(setM).catch((e) => setError(e.message)); }, []);
  if (error) return <div className="ws-notice error">{error}</div>;
  if (!m) return <Loading>Loading operations metrics…</Loading>;
  const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`);
  return <>
    <div className="metrics-grid five">
      {[['Open', m.tasks_by_status.open || 0], ['Assigned / in progress', (m.tasks_by_status.assigned || 0) + (m.tasks_by_status.in_progress || 0)],
        ['Completed', m.tasks_by_status.completed || 0], ['QC rejection rate', pct(m.qc_rejection_rate)], ['QC rework rate', pct(m.qc_rework_rate)]]
        .map(([l, v]) => <div className="metric" key={l}><span>{l}</span><strong>{v}</strong></div>)}
    </div>
    <div className="two-col">
      <section className="ops-panel"><h3>Average handling time</h3><table className="records-table compact"><thead><tr><th>Activity</th><th>Completed</th><th>Avg minutes</th></tr></thead>
        <tbody>{Object.entries(m.handling_time).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v.completed}</td><td>{v.avg_minutes ?? '—'}</td></tr>)}</tbody></table>
        <p className="muted small">{m.note}</p></section>
      <section className="ops-panel"><h3>Ready for delivery (QC-approved)</h3><table className="records-table compact"><tbody>
        {Object.entries(m.approved_for_delivery).map(([k, v]) => <tr key={k}><td>{k}</td><td>{v}</td></tr>)}</tbody></table>
        <p className="muted small">Open field tasks: {m.field_tasks_open}</p></section>
    </div>
    <section className="ops-panel"><h3>Productivity</h3><table className="records-table compact"><thead><tr><th>User</th><th>Completed as</th><th>Count</th></tr></thead>
      <tbody>{m.productivity.map((p, i) => <tr key={i}><td>{p.user || '—'}</td><td>{p.event.replace(/_/g, ' ')}</td><td>{p.count}</td></tr>)}</tbody></table></section>
  </>;
}

function TaskBoard({ users, onOpenTask }) {
  const [filter, setFilter] = useState({ queue: '', status: 'open' });
  const [data, setData] = useState(null);
  const [assign, setAssign] = useState({});
  const [notice, setNotice] = useState(null);
  const load = useCallback(() => {
    const params = new URLSearchParams(Object.entries(filter).filter(([, v]) => v));
    api(`/tasks?${params}`).then(setData).catch((e) => setNotice({ error: e.message }));
  }, [filter]);
  useEffect(load, [load]);

  async function reassign(task) {
    const choice = assign[task.id];
    if (!choice?.user_id) return;
    try {
      await send(`/tasks/${task.id}/assign`, 'POST', { user_id: choice.user_id, reason: choice.reason || 'Supervisor reassignment' });
      setNotice({ ok: `${task.ref} reassigned.` });
      load();
    } catch (e) {
      setNotice({ error: e.message });
    }
  }

  return <section className="ops-panel">
    <h3>Task board</h3>
    <div className="records-filters">
      <select value={filter.status} onChange={(e) => setFilter((f) => ({ ...f, status: e.target.value }))}>
        {['', 'open', 'assigned', 'in_progress', 'on_hold', 'completed', 'superseded'].map((s) => <option key={s} value={s}>{s ? s.replace('_', ' ') : 'Any status'}</option>)}</select>
      <input placeholder="Queue id, e.g. qc_delete" value={filter.queue} onChange={(e) => setFilter((f) => ({ ...f, queue: e.target.value }))} /></div>
    {notice?.error && <div className="ws-notice error">{notice.error}</div>}{notice?.ok && <div className="ws-notice success">{notice.ok}</div>}
    {!data ? <Loading>Loading tasks…</Loading> : <div className="records-table-wrap"><table className="records-table compact">
      <thead><tr><th>Task</th><th>Queue</th><th>Status</th><th>AOI</th><th>Assignee</th><th>Created</th><th>Reassign to</th><th /></tr></thead>
      <tbody>{data.tasks.map((t) => <tr key={t.id}><td><button className="ws-link" onClick={() => onOpenTask(t.id)}>{t.ref}</button></td><td>{t.queue_label}</td>
        <td>{t.status}</td><td>{t.aoi}</td><td>{t.assignee || '—'}</td><td>{fmtDate(t.created_at)}</td>
        <td>{!['completed', 'superseded', 'cancelled'].includes(t.status) && <span className="reassign">
          <select value={assign[t.id]?.user_id || ''} onChange={(e) => setAssign((a) => ({ ...a, [t.id]: { ...a[t.id], user_id: e.target.value } }))}>
            <option value="">Choose user…</option>{users.filter((u) => u.active).map((u) => <option key={u.id} value={u.id}>{u.display_name}</option>)}</select>
          <input placeholder="Reason" value={assign[t.id]?.reason || ''} onChange={(e) => setAssign((a) => ({ ...a, [t.id]: { ...a[t.id], reason: e.target.value } }))} /></span>}</td>
        <td>{assign[t.id]?.user_id && <button className="ws-button" onClick={() => reassign(t)}>Assign</button>}</td></tr>)}</tbody></table>
      <p className="muted small">{data.total.toLocaleString()} tasks</p></div>}
  </section>;
}

function Users({ users, roles, aois, reload }) {
  const [form, setForm] = useState({ username: '', display_name: '', password: '', roles: [], aois: [] });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const toggle = (key, value) => setForm((f) => ({ ...f, [key]: f[key].includes(value) ? f[key].filter((x) => x !== value) : [...f[key], value] }));

  async function create(e) {
    e.preventDefault();
    setBusy(true);
    setNotice(null);
    try {
      await send('/users', 'POST', form);
      setNotice({ ok: `${form.display_name} can now sign in.` });
      setForm({ username: '', display_name: '', password: '', roles: [], aois: [] });
      reload();
    } catch (err) {
      setNotice({ error: err.message });
    } finally {
      setBusy(false);
    }
  }
  async function setActive(u, active) {
    try { await send(`/users/${u.id}`, 'PATCH', { active }); reload(); } catch (err) { setNotice({ error: err.message }); }
  }

  return <section className="ops-panel">
    <h3>Team & roles</h3>
    <table className="records-table compact"><thead><tr><th>User</th><th>Roles</th><th>AOIs</th><th>Status</th><th /></tr></thead>
      <tbody>{users.map((u) => <tr key={u.id}><td>{u.display_name}<small className="cell-sub">{u.username}</small></td><td>{u.roles.map((r) => roles[r]).join(', ')}</td>
        <td>{u.aois.length ? u.aois.join(', ') : 'All'}</td><td>{u.active ? 'Active' : 'Disabled'}</td>
        <td><button className="ws-link" onClick={() => setActive(u, !u.active)}>{u.active ? 'Disable' : 'Enable'}</button></td></tr>)}</tbody></table>
    <form className="platform-form" onSubmit={create}>
      <h4>Add a user</h4>
      <div className="form-grid">
        <label>Username<input required autoComplete="off" pattern="[a-zA-Z0-9._@+-]{3,80}" value={form.username} onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))} /></label>
        <label>Display name<input required value={form.display_name} onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))} /></label>
        <label>Initial password (10+ characters)<input required type="password" minLength={10} autoComplete="new-password" value={form.password} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))} /></label>
      </div>
      <div className="field-chips">{Object.entries(roles).map(([k, v]) => <label key={k}><input type="checkbox" checked={form.roles.includes(k)} onChange={() => toggle('roles', k)} />{v}</label>)}</div>
      <div className="field-chips">{aois.map((a) => <label key={a}><input type="checkbox" checked={form.aois.includes(a)} onChange={() => toggle('aois', a)} />{a}</label>)}
        <span className="muted small">No AOI selected = all areas</span></div>
      {notice?.error && <div className="ws-notice error">{notice.error}</div>}{notice?.ok && <div className="ws-notice success">{notice.ok}</div>}
      <button className="ws-button primary" disabled={busy || !form.roles.length}>{busy && <Spinner size={14} />}<Icon name="upload" />Create user</button>
    </form>
  </section>;
}

export default function TeamOps({ user, onOpenTask }) {
  const [users, setUsers] = useState(null);
  const [meta, setMeta] = useState(null);
  const reload = useCallback(() => api('/users').then(setUsers).catch(() => setUsers([])), []);
  useEffect(() => { reload(); api('/auth/roles').then(setMeta); }, [reload]);
  return (
    <div className="platform-page">
      <div className="page-heading"><div><p className="eyebrow">OPERATIONS</p><h1>Operations dashboard</h1>
        <p>Queue health, handling time, QC quality and team allocation.</p></div></div>
      <Metrics />
      {users && <TaskBoard users={users} onOpenTask={onOpenTask} />}
      {hasRole(user, 'ops_manager') && users && meta && <Users users={users} roles={meta.roles} aois={meta.aois} reload={reload} />}
    </div>
  );
}
