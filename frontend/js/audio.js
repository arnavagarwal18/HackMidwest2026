// The one AudioContext for the whole page. Every click and every recording timestamp uses its clock
// (audioCtx.currentTime), never setTimeout timing, because timing feedback is in milliseconds.
let context = null;

// Call from a click handler the first time: browsers only let a context run after a user gesture.
export async function getAudioContext() {
  if (!context) {
    const Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) {
      throw new Error('This browser cannot play or record audio. Please use Safari or Chrome.');
    }
    context = new Ctor();
  }
  if (context.state === 'suspended') {
    await context.resume();
  }
  return context;
}
