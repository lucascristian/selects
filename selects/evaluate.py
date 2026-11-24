"""Compare the algorithm's picks with the editor's hand-made labels."""

from dataclasses import dataclass


def overlap(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Intersection over union of two time ranges: 1 = identical, 0 = no shared second."""
    shared = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    combined = max(a[1], b[1]) - min(a[0], b[0])
    return shared / combined if combined > 0 else 0.0


@dataclass
class Comparison:
    file_name: str
    label: tuple[float, float] | None   # None = the editor found nothing usable
    pick: tuple[float, float] | None    # None = the algorithm found nothing usable
    score: float                        # overlap, or 1/0 when one side is "nothing usable"


def compare(file_name: str, label: tuple | None, pick: tuple | None) -> Comparison:
    if label is not None and pick is not None:
        return Comparison(file_name, label, pick, overlap(label, pick))
    agree = (label is None) == (pick is None)
    return Comparison(file_name, label, pick, 1.0 if agree else 0.0)
