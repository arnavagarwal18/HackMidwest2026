// Turns a place in the take ({ bar, time_s, lead_s }) into the two things a jump does:
// move the media and highlight the bar's row in the problem-bar list.
export function createJumper({ player, barList }) {
  function jumpTo(place) {
    if (!place) return;
    if (place.time_s !== null) player.seekTo(Math.max(0, place.time_s - place.lead_s));
    if (place.bar !== null) barList.highlight(place.bar);
  }
  return { jumpTo };
}
