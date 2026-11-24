"""Read the hand-made labels: the best segment of each clip, chosen by the editor."""

import csv
from dataclasses import dataclass
from pathlib import Path

PROBLEM_WORDS = {"shake", "focus", "exposure", "other", "none"}


@dataclass
class Label:
    file_name: str
    start_s: float | None  # None when no part of the clip is usable
    end_s: float | None
    problems: set[str]
    note: str

    @property
    def usable(self) -> bool:
        return self.start_s is not None


def parse_label(row: dict) -> Label:
    """Turn one CSV row into a Label and check that it makes sense."""
    start_text, end_text = row["start_s"].strip(), row["end_s"].strip()
    if start_text and end_text:
        start_s, end_s = float(start_text), float(end_text)
        if start_s >= end_s:
            raise ValueError(f"{row['file_name']}: start {start_s} is not before end {end_s}")
    elif start_text or end_text:
        raise ValueError(f"{row['file_name']}: fill both start_s and end_s, or neither")
    else:
        start_s = end_s = None

    problems = {word.strip() for word in row["problems"].split("+") if word.strip()}
    unknown = problems - PROBLEM_WORDS
    if unknown:
        raise ValueError(f"{row['file_name']}: unknown problem word(s) {sorted(unknown)}")

    return Label(row["file_name"].strip(), start_s, end_s, problems, row["note"].strip())


def load_labels(csv_path: Path) -> dict[str, Label]:
    """Read labels.csv into {file name: Label}."""
    with open(csv_path, newline="", encoding="utf-8") as file:
        labels = [parse_label(row) for row in csv.DictReader(file)]
    return {label.file_name: label for label in labels}
