// Translation to English via Google's public web endpoint (no API key, best effort, may be rate limited).
// Text is only sent when the user asks for a translation.
const MAX_QUERY_LENGTH = 450;
const MAX_PARALLEL = 4;
const ENDPOINT = 'https://translate.googleapis.com/translate_a/single';

const cache = new Map(); // text -> Promise<string>
const transliterationCache = new Map();

/** True when the text contains letters from a non-Latin script (Thai, Chinese, Arabic, Cyrillic, …). */
export function needsTranslation(value) {
  return typeof value === 'string' && /(?=\p{L})[^\p{Script=Latin}]/u.test(value);
}

function splitText(text) {
  const chunks = [];
  let start = 0;
  while (start < text.length) {
    let end = Math.min(start + MAX_QUERY_LENGTH, text.length);
    if (end < text.length) {
      const boundary = text.lastIndexOf(' ', end);
      if (boundary > start) end = boundary;
    }
    chunks.push(text.slice(start, end).trim());
    start = end;
    while (text[start] === ' ') start++;
  }
  return chunks.filter(Boolean);
}

async function requestChunk(chunk) {
  const params = new URLSearchParams({ client: 'gtx', sl: 'auto', tl: 'en', dt: 't', q: chunk });
  let response;
  try {
    response = await fetch(`${ENDPOINT}?${params}`);
  } catch {
    throw new Error('Translation service is unreachable. Check the internet connection.');
  }
  if (response.status === 429) throw new Error('Translation limit reached. Try again in a minute.');
  if (!response.ok) throw new Error(`Translation service returned HTTP ${response.status}.`);
  const result = await response.json();
  const segments = result?.[0];
  if (!Array.isArray(segments) || !segments.length || segments.some((s) => typeof s?.[0] !== 'string')) {
    throw new Error('Translation service returned an invalid response.');
  }
  return segments.map((s) => s[0]).join('');
}

async function requestTransliterationChunk(chunk) {
  const params = new URLSearchParams({ client: 'gtx', sl: 'auto', tl: 'en', dt: 'rm', q: chunk });
  let response;
  try {
    response = await fetch(`${ENDPOINT}?${params}`);
  } catch {
    throw new Error('Transliteration service is unreachable. Check the internet connection.');
  }
  if (response.status === 429) throw new Error('Transliteration limit reached. Try again in a minute.');
  if (!response.ok) throw new Error(`Transliteration service returned HTTP ${response.status}.`);
  const result = await response.json();
  const segments = result?.[0];
  const romanized = Array.isArray(segments)
    ? segments.map((segment) => segment?.[3]).filter((value) => typeof value === 'string' && value).join(' ')
    : '';
  if (!romanized) throw new Error('Transliteration service could not transliterate this text.');
  return romanized;
}

export function translateToEnglish(text) {
  const key = text.trim();
  if (!cache.has(key)) {
    const pending = Promise.all(splitText(key).map(requestChunk)).then((parts) => parts.join(' '));
    // Failed requests are not cached, so a retry can succeed.
    pending.catch(() => cache.delete(key));
    cache.set(key, pending);
  }
  return cache.get(key);
}

export function transliterateToLatin(text) {
  const key = text.trim();
  if (!transliterationCache.has(key)) {
    const pending = Promise.all(splitText(key).map(requestTransliterationChunk)).then((parts) => parts.join(' '));
    pending.catch(() => transliterationCache.delete(key));
    transliterationCache.set(key, pending);
  }
  return transliterationCache.get(key);
}

/** Translates many strings with limited parallelism. Resolves to Map(text -> English). */
async function transformMany(texts, transform) {
  const unique = [...new Set(texts.map((t) => t.trim()).filter(Boolean))];
  const out = new Map();
  let next = 0;
  let firstError = null;
  const worker = async () => {
    while (next < unique.length) {
      const text = unique[next++];
      try { out.set(text, await transform(text)); } catch (e) { firstError ??= e; }
    }
  };
  await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, unique.length) }, worker));
  if (!out.size && firstError) throw firstError;
  return out;
}

/** Translates many strings with limited parallelism. Resolves to Map(text -> English). */
export function translateMany(texts) {
  return transformMany(texts, translateToEnglish);
}

/** Transliterate many strings into Latin script with limited parallelism. */
export function transliterateMany(texts) {
  return transformMany(texts, transliterateToLatin);
}
