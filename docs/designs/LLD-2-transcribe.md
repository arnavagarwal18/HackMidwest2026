# LLD-2 change 2: pYIN transcription

Source: approved design LLD-2 "Take capture and transcription" (id 01a12743-2d24-712f-b70a-e615b75af76b), item 01a12748-708f-7158-a251-632204da6887, as sent by ARCHITECT-7 (M-130).

INTERFACE: transcribe(wav_path, instrument, profile) -> list[PlayedNote]. Also accept a start offset (calib_end_s, default 0).
PlayedNote: { i: int (0-based), onset_s: float, offset_s: float (raw recording times), midi_float: float (median pitch as fractional MIDI, already corrected by profile pitch offset), midi: int (rounded), cents_off: float ((midi_float - midi) x 100), confidence: float 0-1, voiced_ratio: float 0-1 }. Make it a dataclass with to_dict.
Profile (dict) fields used: pitch_offset_cents (default 0), noise_floor_db (default -60). Default profile = those defaults.

TRANSCRIPTION (backend/app/takes/transcribe.py, librosa pYIN): 1) load the wav (16 kHz mono) from calib_end_s on; 2) frames every 10 ms (hop 160 samples, frame 1024); 3) frames quieter than noise_floor_db + 6 dB are silent; 4) librosa.pyin with fmin/fmax per instrument (violin 180-2700 Hz, trumpet 150-1100 Hz) gives pitch + voiced probability per frame; 5) frame pitch midi = 69 + 12 log2(f/440) - pitch_offset_cents/100.
NOTE SPLITTING: a new note starts at a librosa onset (onset_detect with backtrack) or where the running median pitch over 50 ms moves >= 0.7 semitones from the current note's median for >= 40 ms; a note ends at the next start or at 80 ms of silence/unvoiced frames. Drop notes with < 60 ms of voiced frames. midi_float = median of the note's voiced frames; confidence = mean voiced probability x voiced_ratio. No notes at all -> raise NoNotesHeard (error code no_notes_heard).

TESTS (synthetic, generated in the test with numpy): 8 sine notes (A4, B4, C#5 ... at 100 BPM) give 8 notes with right MIDI numbers and onsets within 30 ms; same with 6 Hz vibrato of 30 cents still right; with white noise at -30 dB still found with lower confidence; the wav shifted 20 cents sharp with profile pitch_offset_cents 20 gives cents_off within 5 of 0; a silent wav raises NoNotesHeard.
