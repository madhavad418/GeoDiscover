import { useEffect, useRef, useState } from 'react';
import Icon from './Icon.jsx';
import Loading from './Loading.jsx';
import './overview.css';

const AREAS = [
  {name:'Divisoria',city:'Metro Manila',country:'Philippines',code:'PHL',label:'01',coords:'14.60° N · 120.97° E'},
  {name:'Kampung Bali',city:'Jakarta',country:'Indonesia',code:'IDN',label:'02',coords:'6.19° S · 106.82° E'},
  {name:'Thanon Phaya Thai',city:'Bangkok',country:'Thailand',code:'THA',label:'03',coords:'13.76° N · 100.54° E'},
];

export default function Overview({datasets,loading,error,refresh,navigate,onSelect}) {
  const globeRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    const video = globeRef.current;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => { if (preference.matches) video.pause(); else video.play().catch(() => {}); };
    update(); preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  const toggleGlobe = () => {
    const video = globeRef.current;
    if (video.paused) video.play().catch(() => {}); else video.pause();
  };
  const total=datasets.reduce((n,d)=>n+d.row_count,0);
  const value=n=>loading?<Loading size={18}>Loading</Loading>:error?'—':n.toLocaleString();
  return <div className="ov-page">
    <div className="ov-topline"><span>Workspace <span>/</span> Overview</span><span className="ov-live"><i />Southeast Asia</span></div>
    <section className="ov-showcase" aria-labelledby="overview-title">
      <div className="ov-intro"><p className="ov-eyebrow">JSAN PLACES INTELLIGENCE</p><h1 id="overview-title">A world of places.<br/><em>A clearer perspective.</em></h1><p className="ov-description">Discover, compare and verify the places<br className="ov-desktop-break"/> that connect Southeast Asia.</p><button className="ov-primary" onClick={()=>navigate('viewer')}>Explore AOI Viewer <span aria-hidden="true">↗</span></button></div>
      <div className="ov-globe"><div className="ov-video-stage"><video ref={globeRef} src="./Globe_rotating.mp4" poster="./blue-globe.png" loop muted playsInline disablePictureInPicture disableRemotePlayback preload="auto" onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} aria-label="Rotating blue globe with POI map points" /></div><div className="ov-globe-toolbar"><span className="ov-globe-caption"><i/> THREE MARKETS. ONE CONNECTED VIEW.</span><button className="ov-video-toggle" onClick={toggleGlobe} aria-label={playing ? 'Pause globe animation' : 'Play globe animation'}>{playing ? 'Pause' : 'Play'}</button></div></div>
      <div className="ov-floating ov-baseline"><span className="ov-card-icon"><Icon name="pin" size={17}/></span><span>Customer baseline<strong>{value(total)}</strong><small>Stored POI records</small></span></div>
      <div className="ov-right-stats"><div className="ov-floating"><span className="ov-stat-label">Geographic scope<Icon name="globe" size={15}/></span><strong>03 <small>areas</small></strong><p>Across three countries</p></div><div className="ov-floating"><span className="ov-stat-label">Customer data<Icon name="layers" size={15}/></span><strong>{value(datasets.length)} <small>datasets</small></strong><p>Saved baseline versions</p></div><button className="ov-floating ov-open-data" onClick={()=>navigate('data')}><span className="ov-stat-label">Your next step <span>↗</span></span><b>Bring your data<br/>into focus.</b><span className="ov-import-link">Open Customer Data →</span></button></div>
      <div className="ov-hero-bottom"><span className="ov-partnership"><img src="/jsan-mark.svg" alt=""/>JSAN <span>×</span> HERE</span><span>SEA Places POC <i/> Boundary-led intelligence</span></div>
    </section>
    {error && <div className="ov-error" role="alert">Unable to load customer data. {error}<button onClick={refresh}>Retry connection</button></div>}
    <section className="ov-areas" aria-labelledby="areas-title"><div className="ov-section-heading"><div><p className="ov-eyebrow">YOUR GEOGRAPHIC FOOTPRINT</p><h2 id="areas-title">Three areas. Endless detail.</h2></div><button onClick={()=>navigate('viewer')}>View on map <span>↗</span></button></div>
      <div className="ov-area-grid">{AREAS.map(a=>{
        const saved=datasets.filter(d=>d.aoi===a.name);
        const count=saved.reduce((n,d)=>n+d.row_count,0);
        return <button className="ov-area" key={a.code} onClick={()=>{onSelect(saved[0]?.id || null);navigate('data');}}><div className="ov-area-top"><span className="ov-country">{a.code}</span><span className="ov-area-number">{a.label} <span>↗</span></span></div><div className="ov-area-title"><h3>{a.name}</h3><p>{a.city}, {a.country}</p></div><div className="ov-area-bottom"><span><i/>{loading?<Loading size={11}>Loading</Loading>:error?'Data unavailable':`${count.toLocaleString()} saved POIs`}</span><small>{a.coords}</small></div></button>;
      })}</div>
    </section>
    <section className="ov-workflow"><div><p className="ov-eyebrow">FROM DISCOVERY TO DELIVERY</p><h2>Every place has a process.</h2></div><div className="ov-steps">{[['01','Build your baseline','Import customer data','data'],['02','Find the differences','Collect and compare places','sources'],['03','Make it reliable','Review and verify changes','work']].map(([n,title,sub,page])=><button key={n} onClick={()=>navigate(page)}><span>{n}</span><div><b>{title}</b><small>{sub}</small></div><span className="ov-step-arrow">↗</span></button>)}</div></section>
  </div>;
}
