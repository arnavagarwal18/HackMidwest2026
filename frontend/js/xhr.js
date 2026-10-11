// Upload with progress: fetch cannot report how much of a request body was sent, XMLHttpRequest can.
// Resolves to the part of a fetch Response that http.js reads ({ ok, status, json() }); rejects when the request never got an answer.

// onProgress({ loaded, total }) runs as the body goes out. `body` is a FormData holding File objects: the browser streams
// them from disk, so a big video is not copied into memory here.
export function sendWithProgress(method, url, body, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open(method, url);
    request.upload.addEventListener('progress', (event) => {
      if (event.lengthComputable) onProgress({ loaded: event.loaded, total: event.total });
    });
    request.addEventListener('load', () => resolve({
      ok: request.status >= 200 && request.status < 300,
      status: request.status,
      json: async () => JSON.parse(request.responseText),
    }));
    request.addEventListener('error', () => reject(new Error('The connection broke while sending.')));
    request.addEventListener('abort', () => reject(new Error('The upload was cancelled.')));
    request.addEventListener('timeout', () => reject(new Error('The upload timed out.')));
    request.send(body);
  });
}
