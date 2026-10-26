import { useCallback, useState } from 'react';

let nextId = 0;

export function useToasts() {
  const [toasts, setToasts] = useState([]);
  const toast = useCallback((msg, type = 'ok') => {
    const id = ++nextId;
    setToasts((t) => [...t, { id, msg, type }]);
    const life = type === 'error' ? 6000 : 3200;
    setTimeout(() => setToasts((t) => t.map((x) => (x.id === id ? { ...x, out: true } : x))), life);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), life + 320);
  }, []);
  return [toasts, toast];
}

export default function Toasts({ toasts }) {
  return (
    <div className="toasts" role="status">
      {toasts.map((t) => <div key={t.id} className={`toast ${t.type} ${t.out ? 'out' : ''}`}>{t.msg}</div>)}
    </div>
  );
}
