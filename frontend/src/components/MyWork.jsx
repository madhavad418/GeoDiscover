import { useCallback, useEffect, useState } from 'react';
import Icon from './Icon.jsx';
import Loading, { Spinner } from './Loading.jsx';
import { api, send } from '../lib/api.js';
import { fmtDate } from '../lib/platform.js';

const STATUS_LABEL = { assigned: 'Assigned', in_progress: 'In progress', on_hold: 'On hold' };

export default function MyWork({ onOpenTask }) {
  const [summary, setSummary] = useState(null);
  const [limit, setLimit] = useState(10);
  const [queues, setQueues] = useState([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);

  const load = useCallback(() => api('/tasks/summary').then((s) => { setSummary(s); setLimit((l) => l || s.batch_size); })
    .catch((e) => setNotice({ error: e.message })), []);
  useEffect(() => { load(); }, [load]);

  async function getTasks() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await send('/tasks/claim', 'POST', { limit, queues: queues.length ? queues : null });
      setNotice({ ok: r.claimed.length ? `${r.claimed.length} new task${r.claimed.length === 1 ? '' : 's'} assigned to you.`
        : r.kept_in_progress ? 'No new tasks: finish or release your current work, or check the queues.' : 'No eligible tasks are waiting right now.' });
      await load();
    } catch (e) {
      setNotice({ error: e.message });
    } finally {
      setBusy(false);
    }
  }

  if (!summary) return notice?.error ? <div className="ws-notice error">{notice.error}</div> : <Loading>Loading your work…</Loading>;
  return (
    <div className="platform-page">
      <div className="page-heading"><div><p className="eyebrow">MY WORK</p><h1>Hello, {summary.user.display_name}</h1>
        <p>{Object.values(summary.user.roles).join(' · ')} · {summary.user.aois.length ? summary.user.aois.join(', ') : 'All assigned areas'} · {summary.completed_today} completed today</p></div>
        <div className="get-tasks">
          <label>Batch<input type="number" min={1} max={50} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(50, +e.target.value || 1)))} /></label>
          <button className="ws-button primary" onClick={getTasks} disabled={busy}>{busy ? <Spinner size={14} /> : <Icon name="download" />}{busy ? 'Allocating…' : 'Get tasks'}</button>
          <button className="ws-button" onClick={load} title="Refresh"><Icon name="undo" />Refresh</button>
        </div></div>
      {notice?.error && <div className="ws-notice error" role="alert">{notice.error}</div>}
      {notice?.ok && <div className="ws-notice success" role="status">{notice.ok}</div>}
      <div className="section-title"><div><h2>Available work queues</h2><p>Select queues to limit Get tasks; leave all unselected to use every eligible queue (highest priority first).</p></div></div>
      <div className="queue-grid">{summary.queues.map((q) => (
        <label key={q.id} className={`queue-card ${queues.includes(q.id) ? 'active' : ''}`}>
          <input type="checkbox" checked={queues.includes(q.id)} onChange={() => setQueues((s) => (s.includes(q.id) ? s.filter((x) => x !== q.id) : [...s, q.id]))} />
          <strong>{q.open.toLocaleString()}</strong><span>{q.label}</span></label>))}</div>
      <div className="section-title"><div><h2>My assignments · {summary.assignments.length}</h2><p>In-progress tasks stay with you until you complete or release them (max {summary.max_open}).</p></div></div>
      {summary.assignments.length === 0 ? <div className="ws-empty compact"><p>No assigned tasks. Use Get tasks to pull work from your queues.</p></div> : (
        <div className="records-table-wrap"><table className="records-table"><thead><tr><th>Task</th><th>Queue</th><th>Status</th><th>AOI</th><th>Priority</th><th>Assigned</th><th>Note</th><th /></tr></thead>
          <tbody>{summary.assignments.map((t) => <tr key={t.id}><td>{t.ref}</td><td>{t.queue_label}</td><td>{STATUS_LABEL[t.status] || t.status}</td><td>{t.aoi}</td>
            <td>P{t.priority}</td><td>{fmtDate(t.assigned_at)}</td><td className="why">{t.note || '—'}</td>
            <td><button className="ws-button" onClick={() => onOpenTask(t.id)}>Open ↗</button></td></tr>)}</tbody></table></div>)}
    </div>
  );
}
