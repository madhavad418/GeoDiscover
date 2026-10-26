import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Icon from './components/Icon.jsx';
import Loading from './components/Loading.jsx';
import CustomerData from './components/CustomerData.jsx';
import { api } from './lib/api.js';
import './workspace.css';

const AoiViewer = lazy(() => import('./AoiViewer.jsx'));
const AREAS = [
  { name: 'Divisoria', country: 'Philippines', code: 'PHL', city: 'Metro Manila', color: '#61b8ff' },
  { name: 'Kampung Bali', country: 'Indonesia', code: 'IDN', city: 'Jakarta', color: '#379fdf' },
  { name: 'Thanon Phaya Thai', country: 'Thailand', code: 'THA', city: 'Bangkok', color: '#a3d6ff' },
];
const route = () => location.pathname === '/aoi-viewer' ? 'viewer' : location.pathname === '/customer-data' ? 'data' : 'overview';

export default function App() {
  const [page, setPage] = useState(route);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDataset, setSelectedDataset] = useState(null);
  const mainRef = useRef(null);
  const [mapDataset, setMapDataset] = useState(() => new URLSearchParams(location.search).get('dataset'));
  const refresh = useCallback(async () => {
    setLoading(true);
    try { const data = await api('/customer-data/datasets'); setDatasets(data.datasets); setError(''); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { if (mainRef.current) mainRef.current.scrollTop = 0; }, [page]);
  useEffect(() => {
    const pop = () => { setPage(route()); setMapDataset(new URLSearchParams(location.search).get('dataset')); };
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);
  const navigate = (next, dataset = null) => {
    if (next === 'viewer') setMapDataset(dataset);
    const path = next === 'viewer' ? '/aoi-viewer' : next === 'data' ? '/customer-data' : '/';
    history.pushState({}, '', path + (next === 'viewer' && dataset ? `?dataset=${encodeURIComponent(dataset)}` : ''));
    setPage(next);
  };
  const total = datasets.reduce((n, d) => n + d.row_count, 0);
  return <>
    <header className="workspace-nav">
      <a className="workspace-brand" href="/" onClick={e => { e.preventDefault(); navigate('overview'); }}>
        <img src="/jsan-mark.svg" alt="" /><strong>JSAN</strong><span>Places intelligence</span>
      </a>
      <nav aria-label="Main navigation">
        <button className={page !== 'viewer' ? 'active' : ''} onClick={() => navigate('overview')}>POI workspace</button>
        <button className={page === 'viewer' ? 'active' : ''} onClick={() => navigate('viewer')}><Icon name="map" />AOI Viewer</button>
      </nav>
      <span className="project-tag">SEA PLACES POC</span><span className="workspace-avatar" title="JSAN workspace">J</span>
    </header>
    {page === 'viewer' ? <div className="viewer-shell"><Suspense fallback={<div className="map-loading">Opening AOI Viewer…</div>}><AoiViewer datasetId={mapDataset} /></Suspense></div> :
      <div className="workspace-layout">
        <aside className="workspace-sidebar">
          <div className="project-switch"><span className="project-symbol"><Icon name="globe" size={22} /></span><div><strong>SEA Places POC</strong><small>JSAN × HERE</small></div></div>
          <p className="nav-caption">WORKSPACE</p>
          <nav aria-label="Workspace navigation">
            <button className={page === 'overview' ? 'active' : ''} onClick={() => navigate('overview')}><Icon name="layers" />Overview</button>
            <button className={page === 'data' ? 'active' : ''} onClick={() => navigate('data')}><Icon name="copy" />Customer Data<span className="nav-count">{datasets.length}</span></button>
          </nav>
          <div className="scope-note"><span className="tiny-dot" /> THREE ASSIGNED AREAS<p>One workspace for your customer baseline and POI verification journey.</p></div>
          <div className="sidebar-footer"><span className={`tiny-dot ${error ? 'offline' : ''}`} />{loading ? 'Checking storage…' : error ? 'Storage needs attention' : 'Customer storage connected'}<small>JSAN · Southeast Asia</small></div>
        </aside>
        <main className="workspace-main" ref={mainRef}>
          {page === 'data' ? <CustomerData datasets={datasets} refresh={refresh} storageError={error} loading={loading}
            selected={selectedDataset} setSelected={setSelectedDataset} onMap={id => navigate('viewer', id)} /> : <>
            <div className="page-heading"><div><p className="eyebrow">YOUR DATA. A CLEARER PICTURE.</p><h1>Places start here.</h1><p>Build a trusted POI baseline across Southeast Asia.</p></div><button className="ws-button primary" onClick={() => navigate('data')}><Icon name="upload" />Import customer data</button></div>
            <section className="workspace-hero">
              <div className="hero-copy"><span className="hero-label"><span className="tiny-dot" /> SEA PLACES DATA PARTNERSHIP</span><h2>From local places<br />to reliable intelligence.</h2><p>Bring HERE’s baseline into one place. Explore the assigned areas and prepare the foundation for evidence-backed POI improvements.</p><button className="ws-button" onClick={() => navigate('viewer')}>Explore AOI Viewer <span aria-hidden="true">↗</span></button></div>
              <div className="hero-map" aria-hidden="true"><svg viewBox="0 0 460 300"><defs><pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0H0V30" fill="none" stroke="#294c6b" strokeWidth=".5" /></pattern></defs><rect width="460" height="300" fill="url(#grid)" /><path d="M30 65 100 42 143 76 180 55 202 98 179 138 208 170 252 185 270 215 225 240 186 211 152 190 132 143 95 124 53 130Z M300 66 321 87 315 112 339 133 326 156 312 135 300 104Z M352 145 373 170 360 195 342 180Z M197 244 260 257 303 267 295 281 241 273 200 259Z" fill="#12416a" stroke="#3686b8" /><path d="M181 95 323 123 242 257Z" fill="none" stroke="#71bfff" strokeDasharray="5 7" opacity=".6" />{[[181,95],[323,123],[242,257]].map(([x,y]) => <g key={x}><circle cx={x} cy={y} r="13" fill="#71bfff" opacity=".12"/><circle cx={x} cy={y} r="4" fill="#b4e0ff"/></g>)}<text x="90" y="85">BANGKOK</text><text x="335" y="115">MANILA</text><text x="267" y="246">JAKARTA</text></svg><span className="map-caption">THREE MARKETS. ONE SHARED STANDARD.</span></div>
            </section>
            <div className="metrics-grid">
              {[['Assigned AOIs', '03', 'Across three countries', 'globe'], ['Saved datasets', loading || error ? '—' : datasets.length.toLocaleString(), 'Customer baseline imports', 'layers'], ['Stored POI records', loading || error ? '—' : total.toLocaleString(), 'Across saved dataset versions', 'pin']].map(([label,value,sub,icon]) => <div className="metric" key={label}><span className="metric-icon"><Icon name={icon} size={20}/></span><span>{label}</span><strong>{loading && label !== 'Assigned AOIs' ? <Loading size={24}>Loading?</Loading> : value}</strong><small>{sub}</small></div>)}
            </div>
            {error && <div className="ws-notice" role="status">Customer storage needs attention. {error}<button className="ws-link" onClick={refresh}>Retry connection</button></div>}
            <div className="section-title"><div><h2>Your areas of interest</h2><p>The three markets in your HERE baseline package.</p></div><button className="ws-link" onClick={() => navigate('viewer')}>Open AOI Viewer ↗</button></div>
            <div className="area-grid">{AREAS.map((area, i) => {
              const saved = datasets.filter(d => d.aoi === area.name);
              return <button className="area-card" key={area.code} onClick={() => { setSelectedDataset(saved[0]?.id || null); navigate('data'); }}>
                <div className="area-card-top"><span style={{color:area.color}}>{area.code}</span><span>0{i + 1} ↗</span></div><h3>{area.name}</h3><p>{area.city} · {area.country}</p><div className="area-card-bottom"><span className="tiny-dot" style={{background:area.color}}/>{loading ? <Loading size={12}>Checking datasets?</Loading> : saved.length ? `${saved.length} saved dataset${saved.length === 1 ? '' : 's'}` : 'Awaiting baseline import'}</div>
              </button>;
            })}</div>
            <section className="workflow-strip"><div><p className="eyebrow">THE POC JOURNEY</p><h2>A foundation for every decision.</h2></div><ol><li className="current"><b>01</b><span>Import baseline<small>Available now</small></span></li><li><b>02</b><span>Collect & compare<small>Next phase</small></span></li><li><b>03</b><span>Verify & deliver<small>Next phase</small></span></li></ol></section>
          </>}
          <footer className="workspace-bottom">JSAN Places Intelligence<span>SEA Places POC · Customer baseline workspace</span></footer>
        </main>
      </div>}
  </>;
}
