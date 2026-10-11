// Turns a place in the take ({ bar, time_s, lead_s }) into the two things a jump does: move the media, and select the bar's box
// in Bar by bar and bring it into view (skipped with { select: false }, e.g. for "Play this bar", whose box is already selected).
// barBoxes: { select(barNumber, { reveal }) }.
export function createJumper({ player, barBoxes }) {
  function jumpTo(place, { select = true } = {}) {
    if (!place) return;
    if (place.time_s !== null) player.seekTo(Math.max(0, place.time_s - place.lead_s));
    if (select && place.bar !== null) barBoxes.select(place.bar, { reveal: true });
  }
  return { jumpTo };
}
