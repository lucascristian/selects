"""Tests for selects.takes."""

from selects.takes import (
    Take,
    best_takes,
    count_restarts,
    group_takes,
    is_dialog,
    normalize,
    score_takes,
    similarity,
    split_takes,
)
from selects.transcribe import Word


def words(text: str, start: float = 0.0, step: float = 0.3, probability: float = 0.95) -> list[Word]:
    """Made-up transcript: one word every `step` seconds."""
    return [Word(start + i * step, start + i * step + 0.25, w, probability)
            for i, w in enumerate(text.split())]


def take(text: str, clip: str = "A.MP4", start: float = 0.0, probability: float = 0.95) -> Take:
    return Take(clip, words(text, start, probability=probability))


def test_normalize_ignores_case_punctuation_and_diacritics():
    assert normalize("Bună,") == normalize("buna") == "buna"
    assert normalize("Șapte!") == "sapte"


def test_long_pause_starts_a_new_take():
    transcript = words("hey guys bine ati venit", start=1.0) + words("hey guys bine ati venit", start=6.0)
    takes = split_takes("A.MP4", transcript)
    assert len(takes) == 2
    assert takes[1].start == 6.0


def test_short_pause_stays_in_the_same_take():
    transcript = words("hey guys", start=0.0) + words("bine ati venit", start=1.5)
    assert len(split_takes("A.MP4", transcript)) == 1


def test_similar_lines_match_and_different_lines_do_not():
    first = take("hey guys bine v-am gasit la prima saptamana de facultate")
    second = take("hey guys bine v-am gasit la prima saptamana stau in camera")
    other = take("acum suntem la cumparaturi si iau banane")
    assert similarity(first, second) > 0.5
    assert similarity(first, other) < 0.5


def test_group_takes_across_clips():
    takes = [
        take("hey guys bine ati venit la noi", clip="A.MP4"),
        take("acum mergem la magazin", clip="A.MP4", start=10),
        take("hey guys bine ati venit la noi acasa", clip="B.MP4"),
    ]
    group_takes(takes)
    assert takes[0].group == takes[2].group
    assert takes[1].group != takes[0].group


def test_restarts_are_counted():
    assert count_restarts(take("stai stai unde mergi")) == 1
    assert count_restarts(take("stai unde mergi")) == 0


def test_complete_clear_take_beats_a_stumbled_one():
    stumbled = take("hey guys bine ati venit ă ă la", probability=0.6)
    clean = take("hey guys bine ati venit la noi acasa", start=10)
    takes = [stumbled, clean]
    group_takes(takes)
    score_takes(takes)
    assert best_takes(takes)[clean.group] is clean
    assert "2 filler sound(s)" in stumbled.reasons


def test_shaky_picture_lowers_the_score():
    steady = take("hey guys bine ati venit la noi")
    shaky = take("hey guys bine ati venit la noi", start=10)
    shaky.picture = 0.2
    takes = [steady, shaky]
    group_takes(takes)
    score_takes(takes)
    assert best_takes(takes)[steady.group] is steady


def test_on_a_tie_the_later_take_wins():
    first = take("hey guys bine ati venit")
    second = take("hey guys bine ati venit", start=10)
    takes = [first, second]
    group_takes(takes)
    score_takes(takes)
    assert best_takes(takes)[first.group] is second


def test_a_few_words_in_a_long_clip_are_not_dialog():
    assert not is_dialog(words("stai ca lumina nu pica pe tine"), clip_duration=33.0)


def test_speech_through_most_of_the_clip_is_dialog():
    assert is_dialog(words("deci acum suntem la cumparaturi si iau banane"), clip_duration=4.0)


def test_too_few_words_are_never_dialog():
    assert not is_dialog(words("nooo"), clip_duration=1.0)
