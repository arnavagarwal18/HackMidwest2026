// Transport layer: one fetch wrapper, error mapping and the server-down banner. Screens use api.js, not this.
import { waitInQueue } from './retry_queue.js';
import { API_BASE, MOCK_MODE } from './config.js';
import { mockResponse } from './mock.js';

export class ApiError extends Error {
  constructor(code, message, status, details = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
    this.details = details; // every other key of the error body, e.g. notes for calibration_failed
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
    const mocked = await mockResponse(method, path, body);
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
  if (!ok && data && data.error) { // a 2xx body may carry error: {...} as data (a failed analysis); only failures are errors
    const { error, ...rest } = data; // e.g. calibration_failed sends its notes beside error
    const { code, message, ...errorExtras } = error;
    throw new ApiError(code || 'error', message || 'The app server reported an error.', status, { ...errorExtras, ...rest });
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

// Server down: the request joins the retry queue; each Retry press repeats it once (see retry_queue.js).
function waitForRetry(method, path, body) {
  return new Promise((resolve, reject) => {
    waitInQueue(async () => {
      try {
        resolve(await attempt(method, path, body));
      } catch (err) {
        if (err instanceof NetworkError) return false; // banner stays; user can press Retry again
        reject(err);
      }
      return true;
    }, reject);
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

export const get = (path) => request('GET', path);
export const postJson = (path, body) => request('POST', path, body ?? {});

// Multipart: files is { fieldName: Blob|File }, fields is { name: value } sent as text.
export function postForm(path, files, fields = {}) {
  const form = new FormData();
  Object.entries(files).forEach(([name, file]) => form.append(name, file));
  Object.entries(fields).forEach(([name, value]) => form.append(name, value));
  return request('POST', path, form);
}
