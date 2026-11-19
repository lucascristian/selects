"""Tests for selects.probe."""

from selects.probe import get_duration


def test_get_duration_converts_text_to_float():
    info = {"format": {"duration": "26.400000"}}
    assert get_duration(info) == 26.4