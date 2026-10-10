"""Tunable numbers for note diagnosis (expected notes, alignment, marking)."""

# Needleman-Wunsch scores (step 3)
SCORE_SAME_MIDI = 2.0
SCORE_WITHIN_SEMITONE = -0.5
SCORE_OTHER_SUBSTITUTION = -1.0
SCORE_GAP = -1.0

# Pass 2 only pairs notes whose played onset is within this many beats of the fitted time.
PASS2_WINDOW_BEATS = 1.0
# Pass 2 takes off this x min(1, distance in beats from the fitted time) from every pair's score, so the
# closer pairing wins a tie.
PASS2_TIME_PENALTY = 0.5
# Least-squares fit of onset_s = offset_s + beat * sec_per_beat needs this many same-midi pairs.
MIN_FIT_PAIRS = 3

# Marking (step 4)
OK_TOLERANCE_SEMITONES = 0.5
CONFIDENCE_THRESHOLD = 0.5
CENTS_PER_SEMITONE = 100
# Tuning offset: the median sharp/flat of pairs within OK_TOLERANCE_SEMITONES, needing this many such pairs
# and clamped to +-TUNING_MAX_SEMITONES; marking then judges each note against the player's own tuning.
TUNING_MIN_PAIRS = 5
TUNING_MAX_SEMITONES = 0.4
# An unpaired played note this many beats before the first pair, or after the last pair's end, is outside the range.
OUTSIDE_MARGIN_BEATS = 1.0

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

# Transposition (step 2)
INSTRUMENT_DEFAULT_TRANSPOSITION = {"trumpet": -2, "violin": 0, "piano": 0}
DETECTION_CANDIDATES = (0, -2, -3, -7, -9)
DETECTION_MIN_GAIN = 0.15
# Quality gains are sums of fractions; this absorbs float noise so an exact +0.15 counts.
DETECTION_EPSILON = 1e-9
MIN_TRANSPOSITION_SEMITONES = -12
MAX_TRANSPOSITION_SEMITONES = 12

SOURCE_FILE = "file"
SOURCE_DEFAULT = "default"
SOURCE_DETECTED = "detected"
SOURCE_USER = "user"

# Problems, tiers and sentences (steps 7-8)
PROBLEM_NOTES = "notes"
PROBLEM_FORM = "form"
MIN_TIMED_NOTES_FOR_TIMING_PROBLEM = 2
TIMING_SIZE_FULL_MS = 200
DRIFT_SIZE_FULL_PCT = 20
MULTI_BAR_BONUS = 0.25
TIER1_MAX = 3
TIER1_MIN_CERTAINTY = 0.6
TIER1_MIN_SCORE = 0.15
TIER2_MAX = 7
RANK_DECIMALS = 4

# Take errors the analysis route explains
ERROR_NO_SCORE = "no_score"
ERROR_DIAGNOSIS_FAILED = "diagnosis_failed"
ERROR_STORAGE = "storage_error"
