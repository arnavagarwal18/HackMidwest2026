"""Giving each detected hand to the learner's left or right by the nearest pose wrist (MediaPipe's own label is ignored)."""
import math

from . import config

Point = tuple[float, float]


def _distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def assign_hands(pose: list[list[float]] | None, hands: list[list[list[float]]]) -> tuple[list | None, list | None]:
    """(left_hand, right_hand): each hand goes to the wrist it is closest to; when two hands want the same wrist the closer one keeps it.

    Without a pose there are no wrists to compare with, so both sides are None.
    """
    if pose is None or not hands:
        return None, None
    wrists = [tuple(pose[config.LEFT_WRIST][:2]), tuple(pose[config.RIGHT_WRIST][:2])]
    hand_wrists = [tuple(hand[0][:2]) for hand in hands[:config.HANDS_MAX]]  # landmark 0 of a hand is its wrist
    pairs = sorted((_distance(wrist, wrists[side]), index, side) for index, wrist in enumerate(hand_wrists) for side in range(2))
    sides: list[list | None] = [None, None]
    taken_hands: set[int] = set()
    for _, index, side in pairs:  # closest hand-wrist pairs first; a hand and a wrist are each used once
        if index not in taken_hands and sides[side] is None:
            sides[side] = hands[index]
            taken_hands.add(index)
    return sides[0], sides[1]
