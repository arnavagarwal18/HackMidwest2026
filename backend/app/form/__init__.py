"""Video form analysis (LLD-4): run, get_flags and get_flag are the package's API for the other modules."""
from .flags import FormFlag, get_flag, get_flags
from .runner import run

__all__ = ["FormFlag", "get_flag", "get_flags", "run"]
