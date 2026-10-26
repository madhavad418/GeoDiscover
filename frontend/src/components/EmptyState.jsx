import Icon from './Icon.jsx';

const FORMATS = ['.geojson', '.zip / .shp (shapefile)', '.qmd', '.csv', '.xlsx / .xls'];

export default function EmptyState({ onBrowse }) {
  return (
    <div className="panel empty">
      <div className="empty-art">
        <span className="ring r1" /><span className="ring r2" /><span className="ring r3" />
        <span className="empty-ic"><img src="/jsan-mark.svg" alt="JSAN" width="32" height="30" /></span>
      </div>
      <h2>Visualise your areas of interest</h2>
      <p>Load AOI boundary files and place extracts (CSV or Excel with latitude/longitude). Click any area or place for its details, then jump into Street View.</p>
      <button className="btn-primary" onClick={onBrowse}><Icon name="upload" />Choose files</button>
      <div className="empty-formats">{FORMATS.map((f) => <span key={f}>{f}</span>)}</div>
    </div>
  );
}
