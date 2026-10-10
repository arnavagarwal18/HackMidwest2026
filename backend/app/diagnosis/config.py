"""Tunable numbers for note diagnosis (expected notes, alignment, marking)."""

# Needleman-Wunsch scores (step 3)
SCORE_SAME_MIDI = 2.0
SCORE_WITHIN_SEMITONE = -0.5
SCORE_OTHER_SUBSTITUTION = -1.0
SCORE_GAP = -1.0

# Pass 2 only pairs notes whose played onset is within this many beats of the fitted time.
PASS2_WINDOW_BEATS = 1.0
# Least-squares fit of onset_s = offset_s + beat * sec_per_beat needs this many same-midi pairs.
MIN_FIT_PAIRS = 3

# Marking (step 4)
OK_TOLERANCE_SEMITONES = 0.5
CONFIDENCE_THRESHOLD = 0.5
CENTS_PER_SEMITONE = 100

# "Can't tell" verdicts
MIN_EXPECTED_NOTES = 3
MIN_ALIGNMENT_QUALITY = 0.4
MIN_PAIRED_FRACTION = 0.5

CANT_TELL_TOO_SHORT = "too_short"
CANT_TELL_LOW_MATCH = "low_match"
CANT_TELL_FEW_PAIRS = "few_pairs"

STATUS_OK = "ok"
STATUS_WRONG = "wrong"
STATUS_MISSED = "missed"
STATUS_UNCERTAIN = "uncertain"

GRID_METRONOME = "metronome"
GRID_FITTED = "fitted"

# Timing (step 5): a note is late / early beyond this many ms
LATE_EARLY_MS = 80
MS_PER_S = 1000
TIMED_STATUSES = (STATUS_OK, STATUS_WRONG)
# A bar's local tempo needs this many ok notes; drift beyond +-this percent of the target is rushing / dragging
MIN_BAR_NOTES_FOR_TEMPO = 2
DRIFT_LIMIT_PCT = 5.0
TIMING_LATE = "late"
TIMING_EARLY = "early"
DRIFT_RUSHING = "rushing"
DRIFT_DRAGGING = "dragging"
DRIFT_STEADY = "steady"
TIMING_DECIMALS = 2

# Error rate and clean tempo (step 6)
CLEAN_MAX_ERROR_RATE = 0.10
CLEAN_FALLBACK_FRACTION = 0.7
