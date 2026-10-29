import { useState } from 'react';
import { Spinner } from './Loading.jsx';
import { send } from '../lib/api.js';
import './login.css';

export default function Login({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const asset = (name) => `${import.meta.env.BASE_URL}${name}`;

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
    <main className="signin-page">
      <div className="signin-grid" aria-hidden="true" />
      <header className="signin-header">
        <div className="signin-brand"><img src={asset('jsan-mark.svg')} alt=""/><strong>JSAN</strong><span>Places intelligence</span></div>
        <span className="signin-header-note"><i/> YOUR WORLD. IN FOCUS.</span>
      </header>
      <div className="signin-content">
        <section className="signin-story" aria-labelledby="signin-story-title">
          <div className="signin-globe" aria-hidden="true">
            <div className="signin-orbit orbit-one"/><div className="signin-orbit orbit-two"/>
            <img src={asset('blue-globe.png')} alt="" fetchPriority="high"/>
            <span className="signin-coordinate">CONNECTED PLACES / SHARED PERSPECTIVE</span>
          </div>
          <div className="signin-story-copy"><p className="signin-eyebrow">LOCATION IS JUST THE BEGINNING</p><h1 id="signin-story-title">Every place.<br/><span>A world of possibility.</span></h1><p>Turn location data into a clearer picture.<br/>Discover, compare and verify the places that matter.</p></div>
          <div className="signin-chips" aria-label="Workspace capabilities"><span><i/> Discover</span><span><i/> Compare</span><span><i/> Verify</span></div>
        </section>
        <section className="signin-panel" aria-labelledby="signin-title">
          <div className="signin-panel-top"><span className="signin-small-mark"><img src={asset('jsan-mark.svg')} alt=""/></span><span>YOUR PLACES WORKSPACE</span></div>
          <h2 id="signin-title">Welcome back.</h2><p className="signin-subtitle">A clearer view starts here. Sign in to continue.</p>
          <form className="signin-form" onSubmit={submit} aria-busy={busy}>
            <label htmlFor="signin-username">Username</label>
            <input id="signin-username" name="username" autoComplete="username" placeholder="Enter your username" value={username} onChange={e=>setUsername(e.target.value)} required disabled={busy}/>
            <label htmlFor="signin-password">Password</label>
            <div className="signin-password"><input id="signin-password" name="password" type={showPassword ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={e=>setPassword(e.target.value)} required disabled={busy}/><button type="button" onClick={()=>setShowPassword(v=>!v)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} disabled={busy}>{showPassword ? 'Hide' : 'Show'}</button></div>
            {error && <div className="signin-error" role="alert">{error}</div>}
            <button type="submit" className="signin-submit" disabled={busy || !username || !password}>{busy ? <><Spinner size={16}/>Signing in...</> : <>Sign in to workspace <span aria-hidden="true">&#8599;</span></>}</button>
          </form>
          <div className="signin-account-note"><span aria-hidden="true">&#9432;</span><p>Need access?<br/><span>Contact your Operations Manager to create an account.</span></p></div>
          <div className="signin-panel-bottom"><span className="signin-lock" aria-hidden="true"><svg viewBox="0 0 20 20" fill="none"><rect x="4" y="9" width="12" height="8" rx="2"/><path d="M6 9V6a4 4 0 0 1 8 0v3M10 12v2"/></svg></span>One workspace. Access tailored to your role.</div>
        </section>
      </div>
      <footer className="signin-footer"><span>JSAN <span className="signin-footer-divider">/</span> PLACES INTELLIGENCE</span><span>Connecting data to real-world places.</span><span>DISCOVER <b>+</b> VERIFY <b>+</b> DELIVER</span></footer>
    </main>
  );
}
