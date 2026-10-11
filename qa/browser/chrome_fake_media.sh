#!/bin/sh
# Stands in for the Chrome binary (point CHROME at this file): adds Chrome's fake camera and microphone, so no real device is opened,
# then replaces itself with the real Chrome so frontend/tests/browser.mjs still launches it with --mute-audio and stops it by its handle.
REAL_CHROME="${REAL_CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$REAL_CHROME" ]; then
  echo "Chrome not found at $REAL_CHROME; set REAL_CHROME to its binary." >&2
  exit 127
fi
exec "$REAL_CHROME" --use-fake-ui-for-media-stream --use-fake-device-for-media-stream --mute-audio "$@"
