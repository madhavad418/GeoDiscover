import { useCallback, useEffect, useMemo, useState } from 'react';
import Icon from './Icon.jsx';
import { Spinner } from './Loading.jsx';
import { needsTranslation, translateMany, transliterateMany } from '../lib/translation.js';

// Once the user turns translation on, later records translate automatically until they turn it off.
const PREF_KEY = 'jsan.autoTranslate';
const TRANSLITERATION_PREF_KEY = 'jsan.autoTransliterate';
const readPref = () => { try { return localStorage.getItem(PREF_KEY) === '1'; } catch { return false; } };
const writePref = (on) => { try { localStorage.setItem(PREF_KEY, on ? '1' : '0'); } catch { /* storage unavailable */ } };
const readTransliterationPref = () => { try { return localStorage.getItem(TRANSLITERATION_PREF_KEY) === '1'; } catch { return false; } };
const writeTransliterationPref = (on) => { try { localStorage.setItem(TRANSLITERATION_PREF_KEY, on ? '1' : '0'); } catch { /* storage unavailable */ } };

/**
 * Translation state for a set of field values. Only values in a non-Latin script are sent.
 * Returns { available, count, status, on, error, toggle, t } where t(value) gives the English text or null.
 */
export function useTranslate(values) {
  const signature = values.filter(needsTranslation).map((v) => v.trim()).join('\u0001');
  const candidates = useMemo(() => (signature ? [...new Set(signature.split('\u0001'))] : []), [signature]);
  const [on, setOn] = useState(readPref);
  const [status, setStatus] = useState('idle');
  const [map, setMap] = useState(() => new Map());
  const [error, setError] = useState('');
  const [transliterationOn, setTransliterationOn] = useState(readTransliterationPref);
  const [transliterationStatus, setTransliterationStatus] = useState('idle');
  const [transliterationMap, setTransliterationMap] = useState(() => new Map());
  const [transliterationError, setTransliterationError] = useState('');

  const run = useCallback(async () => {
    setStatus('loading');
    setError('');
    try {
      setMap(await translateMany(candidates));
      setStatus('done');
    } catch (e) {
      setError(e.message);
      setStatus('error');
      setOn(false);
    }
  }, [candidates]);

  const runTransliteration = useCallback(async () => {
    setTransliterationStatus('loading');
    setTransliterationError('');
    try {
      setTransliterationMap(await transliterateMany(candidates));
      setTransliterationStatus('done');
    } catch (e) {
      setTransliterationError(e.message);
      setTransliterationStatus('error');
      setTransliterationOn(false);
      writeTransliterationPref(false);
    }
  }, [candidates]);

  useEffect(() => {
    setMap(new Map());
    setStatus('idle');
    setError('');
    setTransliterationMap(new Map());
    setTransliterationStatus('idle');
    setTransliterationError('');
  }, [candidates]);

  useEffect(() => {
    if (on && candidates.length && status === 'idle') run();
  }, [on, candidates, status, run]);

  useEffect(() => {
    if (transliterationOn && candidates.length && transliterationStatus === 'idle') runTransliteration();
  }, [transliterationOn, candidates, transliterationStatus, runTransliteration]);

  const toggle = () => {
    const next = !on;
    setOn(next);
    writePref(next);
    if (next && status !== 'done') run();
  };
  const toggleTransliteration = () => {
    const next = !transliterationOn;
    setTransliterationOn(next);
    writeTransliterationPref(next);
    if (next && transliterationStatus !== 'done') runTransliteration();
  };
  const t = (value) => (on && typeof value === 'string' && map.get(value.trim())) || null;
  const r = (value) => (transliterationOn && typeof value === 'string' && transliterationMap.get(value.trim())) || null;
  return {
    available: candidates.length > 0, count: candidates.length, status, on, error, toggle, t,
    transliterationStatus, transliterationOn, transliterationError, toggleTransliteration, r,
  };
}

export function TranslateToggle({ tr, compact = false }) {
  if (!tr.available) return null;
  const loading = tr.status === 'loading';
  return (
    <span className="translate-toggle">
      <button type="button" className={`translate-btn ${tr.on ? 'on' : ''}`} onClick={tr.toggle} disabled={loading}
        title={tr.on ? 'Show the original text' : `Translate ${tr.count} non-English field${tr.count > 1 ? 's' : ''} to English`}>
        {loading ? <><Spinner size={11} />Translating…</> : tr.on ? <><Icon name="translate" size={12} />Show original</> : <><Icon name="translate" size={12} />{compact ? 'Translate' : 'Translate to English'}</>}
      </button>
      {tr.error && <span className="translate-error" role="alert">{tr.error}</span>}
    </span>
  );
}

export function TransliterateToggle({ tr }) {
  if (!tr.available) return null;
  const loading = tr.transliterationStatus === 'loading';
  return (
    <span className="translate-toggle">
      <button type="button" className={`translate-btn ${tr.transliterationOn ? 'on' : ''}`} onClick={tr.toggleTransliteration} disabled={loading}
        title={tr.transliterationOn ? 'Show the original script' : `Transliterate ${tr.count} non-Latin field${tr.count > 1 ? 's' : ''} to Latin script`}>
        {loading ? <><Spinner size={11} />Transliterating…</> : tr.transliterationOn ? <><Icon name="type" size={12} />Show original</> : <><Icon name="type" size={12} />Transliterate</>}
      </button>
      {tr.transliterationError && <span className="translate-error" role="alert">{tr.transliterationError}</span>}
    </span>
  );
}

/** Renders an English translation and/or Latin transliteration with the original underneath. */
export function Tx({ tr, value }) {
  const english = tr.t(value);
  const transliteration = tr.r(value);
  if ((!english || english === String(value).trim()) && !transliteration) return value;
  return (
    <span className="tx">
      {english && english !== String(value).trim() && <span>{english}</span>}
      {transliteration && <small className="tx-transliteration">{transliteration}</small>}
      <small className="tx-orig" lang="">{value}</small>
    </span>
  );
}
