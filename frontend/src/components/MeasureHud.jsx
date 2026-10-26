import Icon from './Icon.jsx';

export default function MeasureHud({ distance, area, points, onUndo, onClear, onClose }) {
  return (
    <div className="panel hud">
      <div className="hud-stats">
        <div><label>Distance</label><b>{distance}</b></div>
        <div><label>Area</label><b>{area}</b></div>
        <div><label>Points</label><b>{points}</b></div>
      </div>
      <div className="hud-actions">
        <button className="icon-btn" onClick={onUndo} title="Undo last point"><Icon name="undo" /></button>
        <button className="icon-btn" onClick={onClear} title="Clear"><Icon name="trash" /></button>
        <button className="icon-btn" onClick={onClose} title="Exit (Esc)"><Icon name="x" /></button>
      </div>
      <p className="hud-hint">Click to add points · double-click to finish · Esc to exit</p>
    </div>
  );
}
