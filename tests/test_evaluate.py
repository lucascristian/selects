"""Tests for selects.evaluate."""

import pytest

from selects.evaluate import compare, overlap


def test_identical_ranges_overlap_fully():
    assert overlap((2, 6), (2, 6)) == 1.0


def test_half_shared_range():
    # shared 4-6 (2 s), together 2-8 (6 s)
    assert overlap((2, 6), (4, 8)) == pytest.approx(2 / 6)


def test_separate_ranges_do_not_overlap():
    assert overlap((0, 2), (5, 9)) == 0.0


def test_both_saying_nothing_usable_is_agreement():
    assert compare("A.MP4", None, None).score == 1.0


def test_pick_on_unusable_clip_is_a_miss():
    assert compare("A.MP4", None, (0, 3)).score == 0.0
