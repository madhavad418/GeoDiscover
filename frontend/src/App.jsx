import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Icon from './components/Icon.jsx';
import Loading, { Spinner } from './components/Loading.jsx';
import CustomerData from './components/CustomerData.jsx';
import Login from './components/Login.jsx';
import Overview from './components/Overview.jsx';
import { api, send, UNAUTHORIZED_EVENT } from './lib/api.js';
import { hasRole, isSupervisor } from './lib/platform.js';
import './workspace.css';
import './platform.css';
import './light-theme.css';

const OperationsWorkspace = lazy(() => import('./components/OperationsWorkspace.jsx'));
const AoiViewer = lazy(() => import('./AoiViewer.jsx'));
const ComparisonDashboard = lazy(() => import('./components/ComparisonDashboard.jsx'));
const ResultsMap = lazy(() => import('./components/ResultsMap.jsx'));
const MyWork = lazy(() => import('./components/MyWork.jsx'));
const TaskWindow = lazy(() => import('./components/TaskWindow.jsx'));
const Delivery = lazy(() => import('./components/Delivery.jsx'));
const TeamOps = lazy(() => import('./components/TeamOps.jsx'));
const ProviderComparison = lazy(() => import('./components/ProviderComparison.jsx'));
const SavedComparisons = lazy(() => import('./components/SavedComparisons.jsx'));
const PATHS = {
  overview: '/', data: '/customer-data', viewer: '/aoi-viewer', operations: '/poc-operations', sources: '/sources',
  map: '/compare', providers: '/here-vs-providers', results: '/comparison-results', work: '/my-work', delivery: '/delivery', ops: '/operations-dashboard',
};

/** Current page and its argument (dataset, run or task id) from the URL. */
function route() {
  const task = /^\/tasks\/(\d+)$/.exec(location.pathname);
  if (task) return { page: 'task', arg: +task[1] };
  const page = Object.entries(PATHS).find(([, p]) => p === location.pathname)?.[0] || 'overview';
  const params = new URLSearchParams(location.search);
  return { page, arg: params.get('run') || params.get('dataset') };
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = checking session, null = signed out
  const [{ page, arg }, setRoute] = useState(route);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedDataset, setSelectedDataset] = useState(null);
  const mainRef = useRef(null);

  useEffect(() => {
    api('/auth/me').then(setUser).catch(() => setUser(null));
    const signedOut = () => setUser(null);
    window.addEventListener(UNAUTHORIZED_EVENT, signedOut);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, signedOut);
  }, []);
  const refresh = useCallback(async () => {
    setLoading(true);
    try { const data = await api('/customer-data/datasets'); setDatasets(data.datasets); setError(''); }
    catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { if (user) refresh(); }, [user, refresh]);
  useEffect(() => { if (mainRef.current) mainRef.current.scrollTop = 0; }, [page, arg]);
  useEffect(() => {
    const pop = () => setRoute(route());
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);
  const navigate = (next, value = null) => {
    let path = next === 'task' ? `/tasks/${value}` : PATHS[next];
    if (value && next === 'viewer') path += `?dataset=${encodeURIComponent(value)}`;
    if (value && next === 'map') path += `?run=${encodeURIComponent(value)}`;
    history.pushState({}, '', path);
    setRoute({ page: next, arg: value });
  };
  async function signOut() {
    await send('/auth/logout', 'POST').catch(() => {});
    setUser(null);
  }

  if (user === undefined) return <div className="map-loading"><Loading size={22}>Checking your session…</Loading></div>;
  if (user === null) return <Login onLogin={(u) => { setUser(u); }} />;

  const total = datasets.reduce((n, d) => n + d.row_count, 0);
  const lazyPage = (node, label) => <Suspense fallback={<Loading>{label}</Loading>}>{node}</Suspense>;
  const workPages = { work: 'My work', task: 'My work' };
  return <div className="overview-theme app-light">
    <header className="workspace-nav">
      <a className="workspace-brand" href="/" onClick={e => { e.preventDefault(); navigate('overview'); }}>
        <img src="/jsan-mark.svg" alt="" /><strong>JSAN</strong><span>Places intelligence</span>
      </a>
      <nav aria-label="Main navigation">
        <button className={['overview', 'data', 'operations'].includes(page) ? 'active' : ''} onClick={() => navigate('overview')}>POI workspace</button>
        <button className={workPages[page] ? 'active' : ''} onClick={() => navigate('work')}><Icon name="copy" />My work</button>
        <button className={['sources', 'map', 'providers', 'results'].includes(page) ? 'active' : ''} onClick={() => navigate('sources')}><Icon name="layers" />Compare</button>
        <button className={page === 'viewer' ? 'active' : ''} onClick={() => navigate('viewer', selectedDataset || datasets[0]?.id)}><Icon name="map" />AOI Viewer</button>
      </nav>
      <span className="project-tag">SEA PLACES POC</span>
      <span className="user-chip" title={user.roles.join(', ')}><span className="workspace-avatar">{user.display_name.slice(0, 1).toUpperCase()}</span>
        <span>{user.display_name}<small>{user.roles.length >= 5 ? 'Administrator · all roles' : Object.values(user.role_names || {}).join(' · ')}</small></span>
        <button className="ws-link" onClick={signOut}>Sign out</button></span>
    </header>
    {page === 'viewer' ? <div className="viewer-shell"><Suspense fallback={<div className="map-loading"><Loading size={22}>Opening AOI Viewer…</Loading></div>}><AoiViewer datasetId={arg} /></Suspense></div> :
    page === 'map' ? <div className="viewer-shell"><Suspense fallback={<div className="map-loading"><Loading size={22}>Opening comparison map…</Loading></div>}><ResultsMap runId={arg} onBack={() => navigate('sources')} /></Suspense></div> :
      <div className="workspace-layout">
        <aside className="workspace-sidebar">
          <div className="project-switch"><span className="project-symbol"><Icon name="globe" size={22} /></span><div><strong>SEA Places POC</strong><small>JSAN × HERE</small></div></div>
          <p className="nav-caption">WORKSPACE</p>
          <nav aria-label="Workspace navigation">
            <button className={page === 'overview' ? 'active' : ''} onClick={() => navigate('overview')}><Icon name="layers" />Overview</button>
            <button className={page === 'data' ? 'active' : ''} onClick={() => navigate('data')}><Icon name="copy" />Customer Data<span className="nav-count">{loading ? <Spinner size={10} /> : error ? '!' : datasets.length}</span></button>
            <button className={page === 'sources' ? 'active' : ''} onClick={() => navigate('sources')}><Icon name="link" />Sources & comparison</button>
            {isSupervisor(user) && <button className={page === 'providers' ? 'active' : ''} onClick={() => navigate('providers')}><Icon name="target" />HERE vs Google/Grab</button>}
            <button className={page === 'results' ? 'active' : ''} onClick={() => navigate('results')}><Icon name="layers" />Comparison results</button>
            <button className={workPages[page] ? 'active' : ''} onClick={() => navigate('work')}><Icon name="type" />My work</button>
            {hasRole(user, 'ops_manager', 'qc_lead', 'qc_analyst') && <button className={page === 'delivery' ? 'active' : ''} onClick={() => navigate('delivery')}><Icon name="download" />Delivery</button>}
            {isSupervisor(user) && <button className={page === 'ops' ? 'active' : ''} onClick={() => navigate('ops')}><Icon name="target" />Operations dashboard</button>}
            <button className={page === 'operations' ? 'active' : ''} onClick={() => navigate('operations')}><Icon name="layers" />POC readiness</button>
          </nav>
          <div className="scope-note"><span className="tiny-dot" /> THREE ASSIGNED AREAS<p>One workspace for your customer baseline and POI verification journey.</p></div>
          <div className="sidebar-footer">{loading ? <Loading size={11}>Checking storage…</Loading> : <><span className={`tiny-dot ${error ? 'offline' : ''}`} />{error ? 'Storage needs attention' : 'Customer storage connected'}</>}<small>JSAN · Southeast Asia</small></div>
        </aside>
        <main className="workspace-main" ref={mainRef}>
          {page === 'operations' ? lazyPage(<OperationsWorkspace datasets={datasets} />, 'Loading POC readiness…') :
           page === 'sources' ? lazyPage(<ComparisonDashboard datasets={datasets} user={user} onOpenMap={(run) => navigate('map', run)} />, 'Loading comparison…') :
           page === 'providers' ? lazyPage(<ProviderComparison datasets={datasets} onSaved={() => navigate('results')} />, 'Loading comparison…') :
           page === 'results' ? lazyPage(<SavedComparisons user={user} />, 'Loading comparison results…') :
           page === 'work' ? lazyPage(<MyWork onOpenTask={(id) => navigate('task', id)} />, 'Loading your work…') :
           page === 'task' ? lazyPage(<TaskWindow key={arg} taskId={arg} user={user} onBack={() => navigate('work')} />, 'Loading task…') :
           page === 'delivery' ? lazyPage(<Delivery datasets={datasets} user={user} />, 'Loading delivery…') :
           page === 'ops' ? lazyPage(<TeamOps user={user} onOpenTask={(id) => navigate('task', id)} />, 'Loading operations…') :
           page === 'data' ? <CustomerData datasets={datasets} refresh={refresh} storageError={error} loading={loading}
            selected={selectedDataset} setSelected={setSelectedDataset} onMap={id => navigate('viewer', id)} onCompare={() => navigate('sources')} /> : <Overview datasets={datasets} loading={loading} error={error} refresh={refresh} navigate={navigate} onSelect={setSelectedDataset} /> }
          <footer className="workspace-bottom">JSAN Places Intelligence<span>SEA Places POC · Customer baseline workspace</span></footer>
        </main>
      </div>}
  </div>;
}
