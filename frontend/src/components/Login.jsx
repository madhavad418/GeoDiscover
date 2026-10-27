import { useState } from 'react';
import { Spinner } from './Loading.jsx';
import { send } from '../lib/api.js';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onLogin(await send('/auth/login', 'POST', { username, password }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={submit} aria-busy={busy}>
        <div className="login-brand"><img src="/jsan-mark.svg" alt="" /><div><strong>JSAN</strong><span>Places intelligence</span></div></div>
        <h1>Sign in</h1>
        <p>SEA Places POC workspace. Your role decides which work queues you see.</p>
        <label>Username<input autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus /></label>
        <label>Password<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        {error && <div className="ws-notice error" role="alert">{error}</div>}
        <button className="ws-button primary" disabled={busy || !username || !password}>{busy && <Spinner size={14} />}{busy ? 'Signing in…' : 'Sign in'}</button>
        <small>Accounts are created by an Operations Manager.</small>
      </form>
    </div>
  );
}
