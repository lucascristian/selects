"""Tests for selects.labels."""

import pytest

from selects.labels import load_labels, parse_label


def row(start="1", end="4", problems="shake", note=""):
    return {"file_name": "C0001.MP4", "start_s": start, "end_s": end,
            "problems": problems, "note": note}


def test_parse_label_reads_segment_and_problems():
    label = parse_label(row(start="1.5", end="8", problems="focus + shake"))
    assert (label.start_s, label.end_s) == (1.5, 8.0)
    assert label.problems == {"focus", "shake"}
    assert label.usable


def test_empty_segment_means_nothing_usable():
    label = parse_label(row(start="", end="", problems="other"))
    assert label.start_s is None
    assert not label.usable


@pytest.mark.parametrize("bad", [
    row(start="5", end="2"),
    row(start="1", end=""),
    row(problems="expunere"),
])
def test_bad_rows_raise(bad):
    with pytest.raises(ValueError):
        parse_label(bad)


def test_load_labels_keys_by_file_name(tmp_path):
    csv_file = tmp_path / "labels.csv"
    csv_file.write_text(
        "file_name,start_s,end_s,problems,note\n"
        "A.MP4,0,3,none,good\n"
        "B.MP4,,,shake,all shaky\n",
        encoding="utf-8",
    )
    labels = load_labels(csv_file)
    assert set(labels) == {"A.MP4", "B.MP4"}
    assert labels["B.MP4"].note == "all shaky"
