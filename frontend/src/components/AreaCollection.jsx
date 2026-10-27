import { useEffect, useRef, useState } from 'react';
import { api, send } from '../lib/api.js';
import Loading from './Loading.jsx';
import './areaCollection.css';

export default function AreaCollection({ feature, onClose }) {
  const [options,setOptions]=useState(null), [error,setError]=useState('');
  const [budget,setBudget]=useState(100), [grid,setGrid]=useState(500), [language,setLanguage]=useState('');
  const [custom,setCustom]=useState(''), [run,setRun]=useState(null), [starting,setStarting]=useState(false);
  const [downloading,setDownloading]=useState(false), [cancelling,setCancelling]=useState(false);
  const [pollRetry,setPollRetry]=useState(0);
  const downloaded=useRef(null);
  const name=String(feature.properties?._name || feature.properties?.name || 'Uploaded AOI');
  useEffect(()=>{const c=new AbortController();api('/area-collection/options',{signal:c.signal}).then(setOptions).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();},[]);
  useEffect(()=>{
    if(!run || run.state!=='running') return;
    let stopped=false,timer; const c=new AbortController();
    const poll=async()=>{
      try {const next=await api(`/area-collection/runs/${run.id}`,{signal:c.signal}); if(!stopped){setRun(next);setError('');if(next.state==='running')timer=setTimeout(poll,1500);}}
      catch(e){if(!stopped)setError(`Progress check failed: ${e.message}. Retry to reconnect; the run may still be active.`);}
    };
    timer=setTimeout(poll,1000);return()=>{stopped=true;c.abort();clearTimeout(timer);};
  },[run?.id,run?.state,pollRetry]);
  async function download(id){
    setDownloading(true);setError('');
    try {
      const res=await fetch(`/api/area-collection/runs/${id}/excel`,{credentials:'same-origin'});
      if(!res.ok){const body=await res.json();throw new Error(body.detail || 'Download failed');}
      const url=URL.createObjectURL(await res.blob()), a=document.createElement('a');
      a.href=url;a.download=`JSAN_provider_extract_${id}.xlsx`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }catch(e){setError(e.message);}finally{setDownloading(false);}
  }
  useEffect(()=>{
    if(run && run.state!=='running' && downloaded.current!==run.id){
      downloaded.current=run.id;
      if(Object.values(run.providers).some(p=>p.records>0))download(run.id);
    }
  },[run]);
  async function start(){
    setStarting(true);setError('');
    try {setRun(await send('/area-collection/runs','POST',{
      name,geometry:feature.geometry,budget_per_provider:Number(budget),grid_metres:Number(grid),language,
      queries:custom.trim()?custom.split('\n').map(q=>q.trim()).filter(Boolean):null,
    }));}catch(e){setError(e.message);}finally{setStarting(false);}
  }
  async function cancel(){
    setCancelling(true);try{await send(`/area-collection/runs/${run.id}/cancel`,'POST');setPollRetry(n=>n+1);}catch(e){setError(e.message);}finally{setCancelling(false);}
  }
  const active=starting || run?.state==='running';
  return <div className="collection-overlay"><section className="collection-dialog" role="dialog" aria-modal="true" aria-labelledby="collection-title">
    <header><div><small>JSAN · AOI VIEWER</small><h2 id="collection-title">Collect POIs via APIs</h2><p>{name}</p></div><button className="btn-ghost" disabled={active || downloading} onClick={onClose} aria-label="Close collection">Close</button></header>
    <p>Search Google Places and AWS GrabMaps inside this polygon and download one Excel file with a combined <b>All POIs</b> sheet plus separate <b>Google</b> and <b>Grab</b> sheets, using the 35 HERE baseline columns.</p>
    <p className="collection-note">API results are ranked and limited; all POIs cannot be guaranteed. Export and reuse remain subject to your provider agreements. This extract is separate from approved HERE delivery.</p>
    {!run && <>
      {!options && !error && <Loading>Loading category queries…</Loading>}
      <div className="collection-fields"><label>Maximum requests per provider<input type="number" min="1" max="1000" value={budget} onChange={e=>setBudget(e.target.value)} /></label><label>Search grid<select value={grid} onChange={e=>setGrid(e.target.value)}><option value="250">250 m</option><option value="500">500 m</option><option value="1000">1 km</option><option value="2000">2 km</option></select></label><label>Response language<select value={language} onChange={e=>setLanguage(e.target.value)}><option value="">Provider default</option><option value="en">English</option><option value="th">Thai</option><option value="id">Indonesian</option><option value="fil">Filipino</option></select></label></div>
      <details><summary>Category and local-language search terms</summary><p>Default: {options?.queries.length ?? '…'} distinct names from the supplied HERE category reference. Replace with one term per line to focus the run or use local names. These are search terms, not a complete provider category taxonomy.</p><textarea aria-label="Custom search terms" rows="5" value={custom} onChange={e=>setCustom(e.target.value)} placeholder="Leave blank for all reference categories" /><details><summary>View default category queries</summary><p>{options?.queries.join(' · ')}</p></details></details>
      <p>Up to <b>{2*Number(budget) || 0} paid API requests</b> in total, including Google pagination and smaller searches for capped cells. A budget may stop the run before every cell/category is searched. Google phone and opening-hours fields can trigger higher pricing.</p>
      <button className="collection-primary" disabled={!options || starting || !Number.isInteger(Number(budget)) || budget<1 || budget>1000} onClick={start}>{starting?<Loading>Starting collection…</Loading>:'Start Google + Grab collection'}</button>
    </>}
    {run && <><p role="status">{active?<Loading>Collecting POIs…</Loading>:<b>Run {run.state}</b>} · {run.cells} grid cells · {run.queries.length} queries per cell</p>
      <div className="collection-results">{Object.entries(run.providers).map(([id,p])=><article key={id}><h3>{id==='google'?'Google Places':'AWS GrabMaps'}</h3><p>{p.state} · <b>{p.records.toLocaleString()} POIs</b></p><p>{p.requests}/{run.budget_per_provider} requests · {p.remaining_queries} searches pending</p><p>{p.duplicates} duplicates removed · {p.outside} outside polygon · {p.invalid_results} unusable results · {p.capped_queries} capped searches</p>{p.error && <p role="alert" className="collection-error">{p.error}</p>}</article>)}</div>
      <p>{run.notice}</p><p>Missing fields remain blank. Provider IDs occupy placeid; HERE category codes require a separate crosswalk. Grab v2 supplies POI names, addresses and categories; unavailable contact and routing fields remain blank. Sheet A1 comments contain the run status; POI ID comments retain attribution.</p>
      {active?<button className="btn-ghost" disabled={cancelling} onClick={cancel}>{cancelling?<Loading>Cancelling…</Loading>:'Cancel and keep collected results'}</button>:<button className="collection-primary" disabled={downloading} onClick={()=>download(run.id)}>{downloading?<Loading>Preparing Excel…</Loading>:'Download Excel · Google + Grab'}</button>}
    </>}
    {error && <div role="alert" className="collection-error"><p>{error}</p>{run?.state==='running' && <button className="btn-ghost" onClick={()=>{setError('');setPollRetry(n=>n+1);}}>Retry progress check</button>}</div>}
    {active && <small>Keep this view open. Cancel stops after the current API request finishes.</small>}
  </section></div>;
}
