import { forwardRef, useEffect, useRef } from 'react';
import Icon from './Icon.jsx';
import SearchBox from './SearchBox.jsx';
import { BASEMAPS } from '../lib/mapStyle.js';

function BasemapMenu({ basemap, open, setOpen, onChange }) {
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('pointerdown', close);
    return () => document.removeEventListener('pointerdown', close);
  }, [open, setOpen]);

  return (
    <div className="bm-wrap" ref={wrapRef}>
      <button className="tool bm-btn" onClick={() => setOpen(!open)} title="Basemap (B)">
        <Icon name="map" /><span className="bm-label">{BASEMAPS[basemap].label}</span>
      </button>
      {open && (
        <div className="panel bm-menu open">
          {Object.entries(BASEMAPS).map(([key, b]) => (
            <button key={key} className={`bm-card ${key === basemap ? 'active' : ''}`} onClick={() => { onChange(key); setOpen(false); }}>
              <img src={b.thumb} alt="" loading="lazy" />
              <span>{b.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const Toolbar = forwardRef(function Toolbar(props, searchRef) {
  const { layers, labelsOn, measuring, basemap, basemapOpen, setBasemapOpen, onPick, onFit, onToggleLabels, onToggleMeasure, onScreenshot, onBasemap, onOpenSidebar } = props;
  return (
    <div className="panel toolbar">
      <button className="tool only-mobile" onClick={onOpenSidebar} title="Layers"><Icon name="layers" /></button>
      <SearchBox ref={searchRef} layers={layers} onPick={onPick} />
      <div className="divider" />
      <button className="tool" onClick={onFit} title="Zoom to all layers (F)"><Icon name="fit" /></button>
      <button className={`tool ${labelsOn ? 'active' : ''}`} onClick={onToggleLabels} title="Toggle labels (L)"><Icon name="type" /></button>
      <button className={`tool ${measuring ? 'active' : ''}`} onClick={onToggleMeasure} title="Measure distance & area (M)"><Icon name="ruler" /></button>
      <button className="tool shot-btn" onClick={onScreenshot} title="Save map as PNG"><Icon name="camera" /></button>
      <div className="divider" />
      <BasemapMenu basemap={basemap} open={basemapOpen} setOpen={setBasemapOpen} onChange={onBasemap} />
    </div>
  );
});

export default Toolbar;
