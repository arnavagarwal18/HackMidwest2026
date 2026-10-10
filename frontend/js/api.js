import { showUnreachable, clearBanner } from './banner.js';
import { mockResponse } from './mock.js';

const params = new URLSearchParams(window.location.search);
export const MOCK_MODE = params.get('mock') === '1';
const API_BASE = (params.get('api') || '').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(code, message, status, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details; // the rest of the error object, e.g. notes for calibration_failed
  }
}

class NetworkError extends Error {}

function buildOptions(method, body) {
  if (body === undefined) return { method };
  if (body instanceof FormData) return { method, body };
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
}

async function rawResponse(method, path, body) {
  if (MOCK_MODE) {
    const mocked = await mockResponse(method, path);
    if (!mocked) {
      throw new ApiError('mock_missing', `No mock response for ${method} ${path}.`, 0);
    }
    return mocked;
  }
  let res;
  try {
    res = await fetch(API_BASE + path, buildOptions(method, body));
  } catch (err) {
    console.error(`Cannot reach the server for ${method} ${path}:`, err);
    throw new NetworkError(err.message);
  }
  let parsed = null;
  try {
    parsed = await res.json();
  } catch (err) {
    console.error(`${method} ${path} returned a non-JSON body (HTTP ${res.status}):`, err);
  }
  return { ok: res.ok, status: res.status, body: parsed };
}

async function attempt(method, path, body) {
  const { ok, status, body: data } = await rawResponse(method, path, body);
  if (data && data.error) {
    const { code, message, ...details } = data.error;
    throw new ApiError(code || 'error', message || 'The app server reported an error.', status, details);
  }
  if (!ok || data === null) {
    throw new ApiError(
      `http_${status}`,
      `The app server answered ${method} ${path} with an unexpected response (HTTP ${status}).`,
      status,
    );
  }
  return data;
}

// Server down: show the banner and wait; each Retry press repeats this request once.
function waitForRetry(method, path, body) {
  return new Promise((resolve, reject) => {
    showUnreachable(async () => {
      try {
        const data = await attempt(method, path, body);
        clearBanner();
        resolve(data);
      } catch (err) {
        if (err instanceof NetworkError) return; // banner stays; user can press Retry again
        clearBanner();
        reject(err);
      }
    });
  });
}

export async function request(method, path, body) {
  try {
    return await attempt(method, path, body);
  } catch (err) {
    if (err instanceof NetworkError) return waitForRetry(method, path, body);
    throw err;
  }
}

export const api = {
  get: (path) => request('GET', path),
  post: (path, body) => request('POST', path, body ?? {}),
  // Multipart upload: the audio/photo goes in field 'file', other values as text fields.
  upload: (path, file, fields = {}) => {
    const form = new FormData();
    form.append('file', file);
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    return request('POST', path, form);
  },
  // Multipart with several named files (calibration: ref_0..2, click).
  uploadMany: (path, files, fields = {}) => {
    const form = new FormData();
    Object.entries(files).forEach(([key, file]) => form.append(key, file));
    Object.entries(fields).forEach(([key, value]) => form.append(key, value));
    return request('POST', path, form);
  },
};
