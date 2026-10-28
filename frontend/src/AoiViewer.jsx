import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import MapView from './components/MapView.jsx';
import Sidebar from './components/Sidebar.jsx';
import Toolbar from './components/Toolbar.jsx';
import InfoPanel from './components/InfoPanel.jsx';
import EmptyState from './components/EmptyState.jsx';
import Toasts, { useToasts } from './components/Toasts.jsx';
import Icon from './components/Icon.jsx';
import Loading from './components/Loading.jsx';
import AreaCollection from './components/AreaCollection.jsx';
import { ACCEPT, LAYER_COLORS, readFiles, exportableFeature, download, slug } from './lib/loaders.js';
import { BASEMAPS } from './lib/mapStyle.js';
import { mergeBbox, fmtNum, inBbox, pointInGeom } from './lib/geo.js';
import { streetViewUrl, visiblePlaces } from './lib/places.js';

/** Zoom box and centre for a boundary or a place. */
function focusOf(L, fid) {
  if (L.kind === 'points') {
    const [x, y] = L.data.features[fid].geometry.coordinates;
    return { bbox: [x, y, x, y], center: [x, y] };
  }
  return L.stats[fid];
}

const params = new URLSearchParams(location.search);
let layerSeq = 0;
let taskSeq = 0;

/**
 * The AOI Viewer. Other pages reuse it with `preset` ({ message, load(signal) -> layers }) for read-only layers,
 * `uploads={false}` to hide file loading, and `overlay(layers, updateLayer)` for extra map controls.
 */
export default function AoiViewer({ datasetId, preset = null, uploads = true, overlay = null }) {
  const [collectionFeature, setCollectionFeature] = useState(null);
  const [layers, setLayers] = useState([]);
  const [selected, setSelected] = useState(null); // { layerId, fid }
  const [hover, setHover] = useState(null);
  const [basemap, setBasemap] = useState(BASEMAPS[params.get('basemap')] ? params.get('basemap') : 'dark');
  const [labelsOn, setLabelsOn] = useState(true);
  const [measuring, setMeasuring] = useState(false);
  const [basemapOpen, setBasemapOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  // Loading tasks (file reads, saved-dataset download). Each finishes independently; the newest message shows.
  const [tasks, setTasks] = useState([]);
  const startTask = useCallback((message) => {
    const id = ++taskSeq;
    setTasks((all) => [...all, { id, message }]);
    let done = false;
    return () => { if (!done) { done = true; setTasks((all) => all.filter((t) => t.id !== id)); } };
  }, []);
  const busy = tasks.length ? tasks[tasks.length - 1].message : '';
  const [toasts, toast] = useToasts();

  const mapRef = useRef(null);
  const fileInputRef = useRef(null);
  const searchRef = useRef(null);
  const colorIdx = useRef(0);
  const pendingMeta = useRef(new Map()); // .qmd metadata that arrived before its layer
  const layersRef = useRef(layers);
  layersRef.current = layers;
  const measuringRef = useRef(measuring);
  measuringRef.current = measuring;

  const selectedLayer = selected && layers.find((l) => l.id === selected.layerId);
  const sel = selectedLayer ? selected : null;

  useEffect(() => { document.body.classList.toggle('info-open', !!sel); return () => document.body.classList.remove('info-open'); }, [sel]);
  useEffect(() => { document.body.classList.toggle('sidebar-open', sidebarOpen); return () => document.body.classList.remove('sidebar-open'); }, [sidebarOpen]);

  const fitBbox = useCallback((b) => mapRef.current?.fitBbox(b), []);

  /* ----- Loading ----- */
  const handleFiles = useCallback(async (fileList) => {
    const files = [...fileList];
    if (!files.length) return;
    const finish = startTask(`Reading ${files.length === 1 ? files[0].name : `${files.length} files`}…`);
    // Let the loader paint before parsing large CSV/Excel files on the main thread.
    await new Promise((r) => setTimeout(r, 30));
    let loaded, qmds;
    try {
      ({ layers: loaded, qmds } = await readFiles(files, toast));
    } finally {
      finish();
    }

    // Match .qmd sidecars to layers by base name; keep unmatched ones for later loads.
    for (const { base, meta } of qmds) pendingMeta.current.set(base, meta);
    const metaFor = new Map();
    for (const base of [...layersRef.current, ...loaded].map((l) => l.base)) {
      if (pendingMeta.current.has(base)) {
        metaFor.set(base, pendingMeta.current.get(base));
        pendingMeta.current.delete(base);
      }
    }
    const withMeta = (l) => (metaFor.has(l.base) ? { ...l, meta: { ...l.meta, ...metaFor.get(l.base) } } : l);
    const added = loaded.map((L) => withMeta({ ...L, id: `L${++layerSeq}`, color: LAYER_COLORS[colorIdx.current++ % LAYER_COLORS.length] }));

    setLayers((prev) => {
      // Re-loading a file with the same name replaces the old layer of the same kind
      // (a saved places dataset may share its base name with the AOI boundary file).
      const kept = prev.filter((l) => !added.some((a) => a.base === l.base && a.kind === l.kind)).map(withMeta);
      const next = [...kept, ...added];
      if (next.length && !next.some((l) => l.expanded)) next[0] = { ...next[0], expanded: true };
      return next;
    });

    if (added.length) {
      fitBbox(mergeBbox(added.map((l) => l.bbox)));
      const n = added.reduce((s, l) => s + l.data.features.length, 0);
      toast(`Added ${added.length} layer${added.length > 1 ? 's' : ''} · ${fmtNum(n)} feature${n > 1 ? 's' : ''}`);
    } else if (qmds.length) {
      toast(`Read metadata from ${qmds.length} .qmd file${qmds.length > 1 ? 's' : ''}`);
    }
  }, [toast, fitBbox, startTask]);

  useEffect(() => {
    if (!datasetId) return;
    const controller = new AbortController();
    const finish = startTask('Loading saved dataset…');
    fetch(`/api/customer-data/datasets/${encodeURIComponent(datasetId)}/geojson`, { signal: controller.signal })
      .then(async res => {
        if (!res.ok) throw new Error(res.status === 404 ? 'That saved dataset no longer exists.' : 'Could not load the saved dataset. Check customer storage.');
        const text = await res.text();
        const name = JSON.parse(text).name || 'Customer baseline';
        if (!controller.signal.aborted) await handleFiles([{ name: `${name}.geojson`, text: async () => text }]);
      })
      .catch(e => { if (e.name !== 'AbortError') toast(e.message, 'error'); })
      .finally(finish);
    return () => { controller.abort(); finish(); };
  }, [datasetId, handleFiles, toast, startTask]);

  // Preset layers supplied by the embedding page (e.g. a comparison's lists and its AOI boundary).
  useEffect(() => {
    if (!preset) return;
    const controller = new AbortController();
    const finish = startTask(preset.message || 'Loading map layers…');
    preset.load(controller.signal)
      .then((loaded) => {
        if (controller.signal.aborted) return;
        setLayers(loaded);
        const b = mergeBbox(loaded.filter((l) => l.visible).map((l) => l.bbox));
        if (b) requestAnimationFrame(() => fitBbox(b));
      })
      .catch((e) => { if (e.name !== 'AbortError') toast(e.message, 'error'); })
      .finally(finish);
    return () => { controller.abort(); finish(); };
  }, [preset, fitBbox, toast, startTask]);

  // ?file=a.geojson&file=b.geojson loads files by URL (when served over http).
  useEffect(() => {
    if (!uploads) return;
    const urls = [...params.getAll('file'), ...(params.get('files') || '').split(',').filter(Boolean)];
    if (!urls.length) return;
    Promise.allSettled(urls.map(async (u) => {
      const res = await fetch(u);
      if (!res.ok) throw new Error(`${u}: HTTP ${res.status}`);
      const buf = await res.arrayBuffer();
      const name = decodeURIComponent(u.split('/').pop().split('?')[0]);
      return { name, text: async () => new TextDecoder().decode(buf), arrayBuffer: async () => buf };
    })).then((results) => {
      results.filter((r) => r.status === 'rejected').forEach((r) => toast(String(r.reason.message || r.reason), 'error'));
      handleFiles(results.filter((r) => r.status === 'fulfilled').map((r) => r.value));
    });
  }, [handleFiles, toast, uploads]);

  const openPicker = () => fileInputRef.current?.click();

  /* ----- Layer actions ----- */
  const select = useCallback((layerId, fid, fly = false) => {
    setSelected({ layerId, fid });
    setSidebarOpen(false);
    if (fly) {
      const L = layersRef.current.find((l) => l.id === layerId);
      // Wait a frame so the info panel's padding is applied before flying.
      if (L) requestAnimationFrame(() => fitBbox(focusOf(L, fid).bbox));
    }
  }, [fitBbox]);

  const layerHandlers = useMemo(() => ({
    update: (id, patch) => {
      setLayers((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
      const L = layersRef.current.find((l) => l.id === id);
      // Drop the selection if its layer was hidden or its category filtered out.
      setSelected((s) => {
        if (s?.layerId !== id) return s;
        if (patch.visible === false) return null;
        if (patch.hiddenCats && patch.hiddenCats.includes(L?.data.features[s.fid]?.properties._cat)) return null;
        return s;
      });
    },
    zoom: fitBbox,
    select,
    hover: setHover,
    export: (L) => {
      const features = L.kind === 'points' ? visiblePlaces(L) : L.data.features;
      download(JSON.stringify({ type: 'FeatureCollection', features: features.map(exportableFeature) }), `${slug(L.base)}.geojson`, 'application/geo+json');
    },
    remove: (id) => {
      const L = layersRef.current.find((l) => l.id === id);
      setLayers((prev) => prev.filter((l) => l.id !== id));
      setSelected((s) => (s?.layerId === id ? null : s));
      setHover(null);
      if (L) toast(`Removed ${L.title}`);
    },
  }), [fitBbox, select, toast]);

  const clearAll = () => {
    setLayers([]);
    setSelected(null);
    setHover(null);
    toast('Cleared all layers');
  };

  const fitAll = useCallback(() => {
    const b = mergeBbox(layersRef.current.filter((l) => l.visible).map((l) => l.bbox));
    if (b) fitBbox(b);
    else toast('No visible layers to zoom to', 'warn');
  }, [fitBbox, toast]);

  const screenshot = async () => {
    const blob = await mapRef.current?.screenshot();
    if (!blob) return toast('Could not capture the map', 'error');
    download(blob, `geodiscover-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')}.png`);
    toast('Map saved as PNG');
  };

  const pickSearch = (h) => {
    if (!h.L.visible) layerHandlers.update(h.L.id, { visible: true });
    if (h.fid != null) return select(h.L.id, h.fid, true);
    setSelected(null);
    requestAnimationFrame(() => fitBbox(h.L.bbox));
  };

  /* ----- Keyboard shortcuts ----- */
  useEffect(() => {
    const onKey = (e) => {
      if (e.target.closest?.('input, textarea') || e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === '/') { e.preventDefault(); searchRef.current?.focus(); }
      else if (k === 'f') fitAll();
      else if (k === 'l') setLabelsOn((v) => !v);
      else if (k === 'm') setMeasuring((v) => !v);
      else if (k === 'b') setBasemapOpen((v) => !v);
      else if (k === 'escape') {
        setBasemapOpen(false);
        if (measuringRef.current) setMeasuring(false);
        else setSelected(null);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [fitAll]);

  /* ----- Drag & drop anywhere ----- */
  useEffect(() => {
    if (!uploads) return undefined;
    let depth = 0;
    const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files');
    const enter = (e) => { if (!hasFiles(e)) return; e.preventDefault(); depth++; setDragging(true); };
    const over = (e) => { if (hasFiles(e)) e.preventDefault(); };
    const leave = () => { if (--depth <= 0) { depth = 0; setDragging(false); } };
    const drop = (e) => {
      if (!hasFiles(e)) return;
      e.preventDefault();
      depth = 0;
      setDragging(false);
      handleFiles(e.dataTransfer.files);
    };
    window.addEventListener('dragenter', enter);
    window.addEventListener('dragover', over);
    window.addEventListener('dragleave', leave);
    window.addEventListener('drop', drop);
    return () => {
      window.removeEventListener('dragenter', enter);
      window.removeEventListener('dragover', over);
      window.removeEventListener('dragleave', leave);
      window.removeEventListener('drop', drop);
    };
  }, [handleFiles, uploads]);

  // Boundary names that contain the selected place.
  const containers = useMemo(() => {
    if (selectedLayer?.kind !== 'points') return [];
    const pt = selectedLayer.data.features[sel.fid].geometry.coordinates;
    return layers.filter((l) => l.kind === 'shapes').flatMap((l) => l.data.features
      .filter((f, i) => inBbox(pt, l.stats[i].bbox) && pointInGeom(pt, f.geometry))
      .map((f) => (f.properties._name === l.title ? l.displayName : `${f.properties._name} · ${l.displayName}`)));
  }, [layers, selectedLayer, sel?.fid]);

  const openStreetView = (point) => {
    window.open(streetViewUrl(point), '_blank', 'noopener,noreferrer');
  };

  const copyCentre = async () => {
    const [lon, lat] = focusOf(selectedLayer, sel.fid).center;
    const txt = `${lat.toFixed(6)}, ${lon.toFixed(6)}`;
    try { await navigator.clipboard.writeText(txt); toast(`Copied ${txt}`); } catch { toast(txt); }
  };

  return (
    <>
      <MapView
        ref={mapRef}
        layers={layers}
        basemap={basemap}
        labelsOn={labelsOn}
        selected={sel}
        hover={hover}
        measuring={measuring}
        onHover={setHover}
        onSelect={select}
        onClearSelection={() => setSelected(null)}
        onZoomTo={fitBbox}
        onExitMeasure={() => setMeasuring(false)}
      />

      <Sidebar
        layers={layers}
        selected={sel}
        dragging={dragging}
        allowUpload={uploads}
        onBrowse={openPicker}
        onClose={() => setSidebarOpen(false)}
        onClearAll={clearAll}
        layerHandlers={layerHandlers}
      />

      <Toolbar
        ref={searchRef}
        layers={layers}
        labelsOn={labelsOn}
        measuring={measuring}
        basemap={basemap}
        basemapOpen={basemapOpen}
        setBasemapOpen={setBasemapOpen}
        onPick={pickSearch}
        onFit={fitAll}
        onToggleLabels={() => setLabelsOn((v) => !v)}
        onToggleMeasure={() => setMeasuring((v) => !v)}
        onScreenshot={screenshot}
        onBasemap={setBasemap}
        onOpenSidebar={() => setSidebarOpen(true)}
      />

      <InfoPanel
        onCollect={uploads ? setCollectionFeature : undefined}
        layer={selectedLayer}
        fid={sel?.fid}
        onClose={() => setSelected(null)}
        containers={containers}
        onZoom={() => fitBbox(focusOf(selectedLayer, sel.fid).bbox)}
        onCopy={copyCentre}
        onStreetView={openStreetView}
        onExport={() => {
          const f = selectedLayer.data.features[sel.fid];
          download(JSON.stringify(exportableFeature(f), null, 2), `${slug(f.properties._name)}.geojson`, 'application/geo+json');
        }}
      />

      {layers.length === 0 && !busy && uploads && <EmptyState onBrowse={openPicker} />}
      {overlay?.(layers, layerHandlers.update)}
      {collectionFeature && <AreaCollection feature={collectionFeature} onClose={() => setCollectionFeature(null)} />}
      {busy && <div className="viewer-loading"><Loading size={16}>{busy}</Loading></div>}

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => { handleFiles(e.target.files); e.target.value = ''; }}
      />

      <div className={`drop-overlay ${dragging ? 'show' : ''}`}>
        <div className="drop-card"><Icon name="upload" size={36} />Drop to add boundaries or places</div>
      </div>
      <Toasts toasts={toasts} />
    </>
  );
}
