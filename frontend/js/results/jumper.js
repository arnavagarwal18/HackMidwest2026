// Turns a place in the take ({ bar, time_s, lead_s }) into the two things a jump does:
// move the media and highlight the bar's row in the problem-bar list (skipped with { highlight: false }, e.g. when the tap came from the bar strip).
export function createJumper({ player, barList }) {
  function jumpTo(place, { highlight = true } = {}) {
    if (!place) return;
    if (place.time_s !== null) player.seekTo(Math.max(0, place.time_s - place.lead_s));
    if (highlight && place.bar !== null) barList.highlight(place.bar);
  }
  return { jumpTo };
}
