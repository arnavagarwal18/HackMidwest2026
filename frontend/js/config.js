// URL switches read once at load: ?mock=1 answers from frontend/mock/, ?api=<origin> targets another back end.
const params = new URLSearchParams(window.location.search);

export const MOCK_MODE = params.get('mock') === '1';
export const API_BASE = (params.get('api') || '').replace(/\/$/, '');
