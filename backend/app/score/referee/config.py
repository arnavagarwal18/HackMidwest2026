"""Referee limits and the trumpet's written range, in one place."""
CONFIDENCE_FLOOR = 0.7
MAX_BARS_REFEREED = 20
TIMEOUT_S = 60
MAX_OUTPUT_TOKENS = 2048
MAX_TOOL_TEXT_CHARS = 500

# trumpet written range F#3..D6, as MIDI numbers (middle C = C4 = 60)
LOWEST_MIDI = 54
HIGHEST_MIDI = 86

LENGTH_TOLERANCE_BEATS = 1e-3
AGENT_NAME = "referee"
