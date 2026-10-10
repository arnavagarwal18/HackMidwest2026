import zipfile
from pathlib import Path

import pytest

from app.score.exceptions import BadScoreFile
from app.score.parse import WARNING_CHORDS, WARNING_SEVERAL_PARTS, parse_score_file

FIXTURES = Path(__file__).parent / "fixtures"


def pitches(bar):
    return [n.pitch_midi for n in bar.notes]


def test_trumpet_transpose_is_read_and_written_pitch_kept():
    score = parse_score_file(FIXTURES / "trumpet_transpose.musicxml")
    assert score.written_transpose_semitones == -2
    assert score.title == "Trumpet Etude"
    assert score.tempo_bpm == 100
    assert score.time_signature == (4, 4)
    assert score.warnings == []
    assert [b.start_beat for b in score.bars] == [0, 4]
    assert [b.beats for b in score.bars] == [4, 4]
    assert [(n.name, n.pitch_midi) for n in score.bars[0].notes] == [("E5", 76), ("F5", 77), ("G5", 79)]


def test_ties_rests_and_absolute_beats():
    bar2 = parse_score_file(FIXTURES / "trumpet_transpose.musicxml").bars[1]
    assert [(n.idx, n.name, n.start_beat, n.dur_beats, n.tied_from_previous) for n in bar2.notes] == [
        (0, "A4", 4, 2, False),
        (1, "A4", 6, 1, True),
        (2, "rest", 7, 1, False),
    ]
    assert bar2.notes[2].pitch_midi is None


def test_two_parts_keeps_first_part_with_warning():
    score = parse_score_file(FIXTURES / "two_parts.musicxml")
    assert [pitches(b) for b in score.bars] == [[72], [70]]
    assert score.bars[1].notes[0].name == "Bb4"
    assert score.warnings == [WARNING_SEVERAL_PARTS]
    assert score.tempo_bpm == 90
    assert score.written_transpose_semitones is None


def test_chords_keep_top_note_with_warning():
    score = parse_score_file(FIXTURES / "chords.musicxml")
    assert score.time_signature == (3, 4)
    assert [pitches(b) for b in score.bars] == [[67, 62], [72]]
    assert [n.dur_beats for n in score.bars[0].notes] == [2, 1]
    assert score.warnings == [WARNING_CHORDS]


def test_midi_notes_are_rounded_to_sixteenths_and_gaps_become_rests():
    score = parse_score_file(FIXTURES / "off_grid.mid")
    assert score.tempo_bpm == pytest.approx(100)
    assert score.time_signature == (4, 4)
    assert score.warnings == []
    summary = [[(n.name, n.start_beat, n.dur_beats) for n in b.notes] for b in score.bars]
    assert summary == [
        [("C4", 0, 1), ("D4", 1, 1), ("E4", 2, 0.75), ("rest", 2.75, 0.25), ("F4", 3, 1)],
        [("rest", 4, 0.25), ("G4", 4.25, 3.5), ("rest", 7.75, 0.25)],
    ]


def test_mxl_compressed_file(tmp_path):
    mxl = tmp_path / "trumpet.mxl"
    container = (
        '<?xml version="1.0"?><container><rootfiles>'
        '<rootfile full-path="score.xml"/></rootfiles></container>'
    )
    with zipfile.ZipFile(mxl, "w") as archive:
        archive.writestr("META-INF/container.xml", container)
        archive.write(FIXTURES / "trumpet_transpose.musicxml", "score.xml")
    score = parse_score_file(mxl)
    assert score.written_transpose_semitones == -2
    assert len(score.bars) == 2


def test_broken_xml_raises_bad_score_file():
    with pytest.raises(BadScoreFile):
        parse_score_file(FIXTURES / "broken.musicxml")


def test_file_without_notes_raises_bad_score_file():
    with pytest.raises(BadScoreFile, match="no notes"):
        parse_score_file(FIXTURES / "no_notes.musicxml")


def test_missing_file_raises_bad_score_file(tmp_path):
    with pytest.raises(BadScoreFile):
        parse_score_file(tmp_path / "nope.musicxml")


def test_unsupported_extension_raises_bad_score_file(tmp_path):
    path = tmp_path / "song.pdf"
    path.write_bytes(b"%PDF")
    with pytest.raises(BadScoreFile, match="Unsupported"):
        parse_score_file(path)


def test_garbage_midi_raises_bad_score_file(tmp_path):
    path = tmp_path / "bad.mid"
    path.write_bytes(b"not a midi file")
    with pytest.raises(BadScoreFile):
        parse_score_file(path)
