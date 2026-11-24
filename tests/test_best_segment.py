"""Tests for selects.best_segment."""

import math

from selects.best_segment import best_run, choose_segment, clip_bar, ramp


def clip(shake, sharpness=None, brightness=None, shadows=None):
    """Signals for a made-up clip; anything not given is clean."""
    n = len(shake)
    return {
        "shake": shake,
        "sharpness": sharpness or [100.0] * n,
        "brightness": brightness or [100.0] * n,
        "highlights": [0.0] * n,
        "shadows": shadows or [0.0] * n,
        "motion": [0.0] * n,
    }


def test_ramp_is_zero_at_ok_and_one_at_bad():
    assert ramp(0.0, 0.0, 1.5) == 0.0
    assert ramp(0.75, 0.0, 1.5) == 0.5
    assert ramp(9.0, 0.0, 1.5) == 1.0


def test_best_run_keeps_the_good_middle():
    scores = [0.2, 0.9, 0.9, 0.9, 0.2]
    assert best_run(scores, bar=0.5, min_length=2) == (1, 4)


def test_best_run_never_crosses_an_unusable_second():
    scores = [0.9, 0.9, None, 0.9, 0.9, 0.9]
    assert best_run(scores, bar=0.5, min_length=2) == (3, 6)


def test_best_run_returns_none_when_nothing_is_good_enough():
    assert best_run([0.3, 0.4, 0.2], bar=0.5, min_length=2) is None


def test_clip_bar_never_drops_below_half():
    assert clip_bar([0.1, 0.2, 0.3]) == 0.5
    assert clip_bar([None, None]) == 0.5


def test_shaky_start_and_end_are_cut():
    pick = choose_segment(clip(shake=[2.0, 1.8, 0.1, 0.1, 0.1, 0.1, 1.9, 2.2]))
    assert (pick.start_s, pick.end_s) == (2, 6)
    assert any("0-2 s cut: shake" in reason for reason in pick.reasons)


def test_black_frame_splits_the_clip():
    pick = choose_segment(clip(shake=[0.1] * 7, shadows=[0, 0, 98, 0, 0, 0, 0]))
    assert (pick.start_s, pick.end_s) == (3, 7)
    assert any("black frame" in reason for reason in pick.reasons)


def test_all_shaky_clip_is_not_usable():
    pick = choose_segment(clip(shake=[2.5, 3.0, 2.8, 2.6]))
    assert not pick.usable
    assert "nothing usable" in pick.reasons[0]


def test_missing_motion_data_is_never_kept():
    pick = choose_segment(clip(shake=[math.nan, 0.1, 0.1, 0.1]))
    assert pick.start_s == 1
