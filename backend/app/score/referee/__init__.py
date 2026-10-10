"""Score referee: settles the bars where homr and the reader agent disagree (LLD-8)."""
from app.score.referee.agent import run
from app.score.referee.result import RefereeResult

__all__ = ["RefereeResult", "run"]
