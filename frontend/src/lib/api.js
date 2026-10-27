/** Fired when the server says the session ended; App shows the sign-in screen. */
export const UNAUTHORIZED_EVENT = 'jsan:unauthorized';

export async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, { credentials: 'same-origin', ...options });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new Error('Cannot reach the server. Check your connection and that the backend is running.');
  }
  if (response.status === 401 && !path.startsWith('/auth/login')) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  let data;
  try { data = await response.json(); }
  catch { throw new Error('The API did not return a valid response. Check that the backend is running.'); }
  if (!response.ok) {
    const detail = data.detail;
    const error = new Error(typeof detail === 'string' ? detail : detail?.message || 'The request could not be completed.');
    error.issues = detail?.issues || [];
    error.status = response.status;
    throw error;
  }
  return data;
}

/** JSON request shorthand: send('/tasks/1/qc', 'POST', { action: 'approve' }). */
export function send(path, method, body) {
  return api(path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
}
