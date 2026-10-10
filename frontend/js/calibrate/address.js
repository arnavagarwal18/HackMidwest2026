// The address the phone should open for the tone page, and the QR code for it.
import { getLanAddress } from '../api.js';

export const TONE_PAGE = 'tone.html'; // frontend/tone.html, served by the static mount at /
export const LOCALHOST_NOTE = "This page was opened as localhost, so a phone can't reach it from this address. "
  + "Use the laptop's Wi-Fi address (for example 192.168.x.x) in its place.";
const LOCAL_HOSTS = ['localhost', '127.0.0.1', '[::1]'];

export const isLocalHost = (host) => LOCAL_HOSTS.includes(host.replace(/:\d+$/, ''));

// Base address of the app as a phone sees it: { base, note }. Uses GET /lan-address; when that route is missing or
// fails it falls back to the address of this page (note says what to do if that is localhost).
export async function findBaseAddress({ fetchLan = getLanAddress, location = window.location } = {}) {
  try {
    const answer = await fetchLan();
    if (answer && typeof answer.url === 'string' && answer.url) return { base: answer.url.replace(/\/$/, ''), note: null };
    console.error('GET /lan-address answered without a url:', answer);
  } catch (err) {
    console.error('GET /lan-address failed; using the address of this page instead:', err);
  }
  return { base: `${location.protocol}//${location.host}`, note: isLocalHost(location.host) ? LOCALHOST_NOTE : null };
}

export function toneUrl(base, instrument) {
  return `${base}/${TONE_PAGE}?instrument=${encodeURIComponent(instrument)}`;
}
