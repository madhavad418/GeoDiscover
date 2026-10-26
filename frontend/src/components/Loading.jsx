export function Spinner({ size = 16 }) {
  return <svg className="loading-spinner" width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.5" opacity=".2" />
    <path d="M12 3a9 9 0 0 1 9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
  </svg>;
}

export default function Loading({ children = 'Loading…', size = 18 }) {
  return <span className="loading-indicator" role="status"><Spinner size={size} /><span>{children}</span></span>;
}
