"""Finds sentences left pointing back at nothing once the Checker has dropped the sentence before them."""
import re
from typing import Any

ORPHAN_REASON = "orphaned: it refers back to a sentence that was dropped"

_BACK_REFERENCE = re.compile(r"^\W*(?:this|that|it|these|those|which)\b", re.IGNORECASE)


def starts_with_back_reference(item: Any) -> bool:
    """True when the item's text opens with This, That, It, These, Those or which."""
    return isinstance(item, dict) and isinstance(item.get("text"), str) and bool(_BACK_REFERENCE.match(item["text"]))


def orphaned_indexes(items: list, dropped: set[int]) -> list[int]:
    """Indexes of kept items that start with a back-reference while the item before them is dropped (or itself an orphan)."""
    gone = set(dropped)
    orphans = []
    for index, item in enumerate(items):
        if index not in gone and index - 1 in gone and starts_with_back_reference(item):
            gone.add(index)
            orphans.append(index)
    return orphans
