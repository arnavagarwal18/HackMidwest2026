"""The referee's four tools, bound to one run's state (a RefereeSession), plus the checker inside submit_ruling.

Every tool returns plain data and never raises: bad input comes back as {'error': ...}. Only
submit_ruling changes anything, and only the session's list of rulings. The photo is not touched.
"""
import io
import logging
import threading
from pathlib import Path

from PIL import Image, ImageOps
from strands import tool

from app.agents.trace import Trace
from app.score.compare import NO_NOTES_TEXT, CompareResult, DoubtfulBar
from app.score.model import Bar, Score
from app.score.note_text import homr_bar_keys, write_out
from app.score.reader_agent import IMAGE_FORMATS
from app.score.reading import ReadBar, Reading
from app.score.referee import config
from app.score.referee.checks import check_homr_bar, check_reader_bar
from app.score.referee.result import BarCheck, Ruling

logger = logging.getLogger(__name__)

PICKS = ("homr", "reader")
BarBox = tuple[int, int, int, int]  # left, top, right, bottom in photo pixels


class RefereeSession:
    """One referee run's state: the two readings, their checks, and the rulings made so far."""

    def __init__(self, score: Score, reading: Reading, compare: CompareResult, image_path: Path,
                 trace: Trace | None = None, bar_boxes: dict[int, BarBox] | None = None) -> None:
        self._score = score
        self._image_path = Path(image_path)
        self._trace = trace
        self._bar_boxes = bar_boxes or {}
        self._homr_bars: dict[int, Bar] = {bar.bar: bar for bar in score.bars}
        self._reader_bars: dict[int, ReadBar] = {}
        for read_bar in reading.bars:
            self._reader_bars.setdefault(read_bar.bar, read_bar)
        self._first_bar = min(self._homr_bars, default=1)
        self.doubtful: dict[int, DoubtfulBar] = {
            entry["bar"]: entry for entry in compare.doubtful_bars[: config.MAX_BARS_REFEREED]
        }
        self._rulings: dict[int, Ruling] = {}
        self._lock = threading.Lock()
        self._closed = False

    def close(self) -> list[Ruling]:
        """Stop taking rulings (a run that timed out must not change things later) and return those made."""
        with self._lock:
            self._closed = True
            return list(self._rulings.values())

    def reader_bar(self, bar: int) -> ReadBar | None:
        return self._reader_bars.get(bar)

    def _homr_check(self, bar: int) -> BarCheck | None:
        homr = self._homr_bars.get(bar)
        if homr is None:
            return None
        return check_homr_bar(homr, self._score.time_signature, self._score.key_fifths, bar == self._first_bar)

    def _reader_check(self, bar: int) -> BarCheck | None:
        read_bar = self._reader_bars.get(bar)
        if read_bar is None:
            return None
        return check_reader_bar(read_bar, self._score.time_signature, self._score.key_fifths, bar == self._first_bar)

    def _trace_add(self, event: str, name: str, detail: str = "") -> None:
        if self._trace is not None:
            self._trace.add(config.AGENT_NAME, event, name, detail)

    # --- the four tools ---

    def list_doubtful_bars(self) -> list[dict]:
        """List the bars where the two readings disagree: bar number, homr's notes and the reader's notes."""
        self._trace_add("tool", "list_doubtful_bars", f"{len(self.doubtful)} bars")
        return [
            {"bar": e["bar"], "homr_text": e["homr_text"], "reader_text": e["reader_text"]}
            for e in self.doubtful.values()
        ]

    def get_bar(self, bar: int) -> dict:
        """Get both readings of one doubtful bar with their code checks, and the time and key signature.

        Args:
            bar: the bar number
        """
        self._trace_add("tool", "get_bar", f"bar {bar}")
        entry = self.doubtful.get(bar)
        if entry is None:
            return {"error": "unknown_bar"}
        homr = self._homr_bars.get(bar)
        reader = self._reader_bars.get(bar)
        homr_text = entry["homr_text"] if homr is None else (write_out(homr_bar_keys(homr)) or NO_NOTES_TEXT)
        return {
            "bar": bar,
            "homr": {"text": homr_text, "checks": self._homr_check(bar)},
            "reader": None if reader is None else {"text": entry["reader_text"], "checks": self._reader_check(bar)},
            "time_signature": list(self._score.time_signature),
            "key_signature": self._score.key_fifths,
        }

    def look_at_bar(self, bar: int) -> dict:
        """Look at the photo of one doubtful bar (the whole photo when the bar's place on it is not known).

        Args:
            bar: the bar number
        """
        self._trace_add("tool", "look_at_bar", f"bar {bar}")
        if bar not in self.doubtful:
            return {"error": "unknown_bar"}
        block = self._cropped_block(bar) or self._whole_photo_block()
        if block is None:
            return {"error": "no_image"}
        return {"status": "success", "content": [block]}

    def submit_ruling(self, bar: int, pick: str, why: str, confidence: float) -> dict:
        """Give the final ruling for one doubtful bar. Call it once per bar.

        Args:
            bar: the bar number
            pick: 'homr', 'reader' or 'neither'
            why: one short sentence saying why
            confidence: how sure you are, from 0 to 1
        """
        confidence = _confidence(confidence)
        why = str(why)[: config.MAX_TOOL_TEXT_CHARS]
        with self._lock:
            rejected = self._rejection(bar, pick, confidence)
            outcome = {"accepted": rejected is None, "rejected_because": rejected}
            if rejected not in ("unknown_bar", "already_ruled", "run_over"):
                self._rulings[bar] = Ruling(bar=bar, pick=pick if pick in PICKS else "neither", why=why,
                                            confidence=confidence, **outcome)
        verdict = "accepted" if rejected is None else f"rejected, {rejected}"
        self._trace_add("ruling", f"bar {bar}", f"{pick} ({confidence:g}): {verdict}. {why}")
        return outcome

    def _rejection(self, bar: int, pick: str, confidence: float) -> str | None:
        """The checker: None when the ruling is accepted, else why not. Called with the lock held."""
        if self._closed:
            return "run_over"
        if bar not in self.doubtful:
            return "unknown_bar"
        if bar in self._rulings:
            return "already_ruled"
        if pick not in PICKS:
            return "neither"
        checks = self._homr_check(bar) if pick == "homr" else self._reader_check(bar)
        if checks is None:
            return "no_reading"
        if not checks["length_ok"]:
            return "length"
        if not checks["range_ok"]:
            return "range"
        if confidence < config.CONFIDENCE_FLOOR:
            return "low_confidence"
        return None

    def _cropped_block(self, bar: int) -> dict | None:
        box = self._bar_boxes.get(bar)
        if box is None:
            return None
        try:
            with Image.open(self._image_path) as photo:
                cropped = ImageOps.exif_transpose(photo).crop(box)
            buffer = io.BytesIO()
            cropped.save(buffer, format="PNG")
            return {"image": {"format": "png", "source": {"bytes": buffer.getvalue()}}}
        except Exception:
            logger.exception("Referee: could not crop bar %s from %s, sending the whole photo", bar, self._image_path)
            return None

    def _whole_photo_block(self) -> dict | None:
        try:
            image_format = IMAGE_FORMATS[self._image_path.suffix.lower()]
            return {"image": {"format": image_format, "source": {"bytes": self._image_path.read_bytes()}}}
        except Exception:
            logger.exception("Referee: could not read the photo %s", self._image_path)
            return None

    def strands_tools(self) -> list:
        """The four tools as Strands tools, each bound to this session."""
        methods = (self.list_doubtful_bars, self.get_bar, self.look_at_bar, self.submit_ruling)
        return [tool(method) for method in methods]


def _confidence(value: object) -> float:
    try:
        return min(1.0, max(0.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
