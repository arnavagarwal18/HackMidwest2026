// Silences the tone when the page goes away: pagehide (closing, navigating) and the page turning hidden (phone locked, app switched).
export function stopWhenLeaving(player, { page = window, doc = document } = {}) {
  const stopIfLeaving = () => player.stop();
  page.addEventListener('pagehide', stopIfLeaving);
  doc.addEventListener('visibilitychange', () => {
    if (doc.visibilityState === 'hidden') stopIfLeaving();
  });
}
