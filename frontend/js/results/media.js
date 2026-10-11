// The take's media: a <video> (with a stage the overlay canvas can sit on) or an <audio> for a mic take, at the top of the results.
// When the recording cannot be loaded the section hides itself (nothing to show), and the error is logged and reported.
import { reportError } from '../banner.js';
import { element } from '../dom.js';

export function isVideoTake(analysis, takeSetupKind) {
  return takeSetupKind === 'video' || (analysis.form_status ?? 'none') !== 'none';
}

// Returns { section, mediaElement, stage, formFlagSlot, seekTo(seconds) }.
// stage is the box around the video (position: relative) for the overlay; formFlagSlot is empty, for the form flag list.
export function createMediaPlayer({ video, url }) {
  const mediaElement = element(video ? 'video' : 'audio', '', video ? 'take-video' : 'take-audio', { controls: '', preload: 'auto', src: url });
  const stage = element('div', '', 'video-stage', { id: 'video-stage' });
  stage.append(mediaElement);
  const formFlagSlot = element('div', '', 'form-flag-slot', { id: 'form-flag-slot', 'data-slot': 'form-flags' });
  const section = element('section', '', 'results-media', { id: 'results-media', 'aria-label': video ? 'Your video' : 'Your recording' });
  section.append(stage);
  if (video) section.append(formFlagSlot);

  mediaElement.addEventListener('error', () => {
    const code = mediaElement.error?.code ?? 'unknown';
    console.error(`The take's media could not be loaded (media error ${code}):`, url);
    section.hidden = true;
    reportError(new Error('The recording could not be loaded, so jumping to a moment will not work.'));
  });

  async function seekTo(seconds) {
    mediaElement.currentTime = seconds;
    try {
      await mediaElement.play();
    } catch (err) {
      console.error('The browser did not start playback:', err);
      reportError(new Error('Press play on the recording to hear that moment; the browser blocked automatic playback.'));
    }
  }

  return { section, mediaElement, stage, formFlagSlot, seekTo };
}
