export async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error('The API did not return a valid response. Check that the backend is running.'); }
  if (!response.ok) {
    const detail = data.detail;
    const error = new Error(typeof detail === 'string' ? detail : detail?.message || 'The request could not be completed.');
    error.issues = detail?.issues || [];
    throw error;
  }
  return data;
}
