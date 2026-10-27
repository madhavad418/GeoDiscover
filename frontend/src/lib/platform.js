export const OUTCOMES = {
  no_change: { label: 'Matched / No change', color: '#7d9db4' },
  potential_update: { label: 'Potential UPDATE', color: '#e8c27a' },
  potential_new: { label: 'Potential NEW', color: '#5fd39a' },
  verification_required: { label: 'Verification required', color: '#71bfff' },
  potential_delete: { label: 'Potential DELETE', color: '#ff6b8b' },
  fallout_review: { label: 'Fallout review', color: '#b98cff' },
};

export const DECISIONS = {
  new: 'NEW', update: 'UPDATE', delete: 'DELETE', no_change: 'NO CHANGE', field_review: 'FIELD REVIEW', hold: 'HOLD',
};

export const SUPERVISOR_ROLES = ['ops_manager', 'qc_lead'];
export const hasRole = (user, ...roles) => !!user && roles.some((r) => user.roles.includes(r));
export const isSupervisor = (user) => hasRole(user, ...SUPERVISOR_ROLES);

export const fmtDate = (value) => (value ? new Date(value).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—');
export const today = () => new Date().toISOString().slice(0, 10);
