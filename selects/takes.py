"""Split speech into takes, find takes of the same line, and recommend the best one.

A take is one attempt at a line: words that follow each other without a long
pause. Takes of the same line can sit in one clip (the speaker repeats it) or
in several clips (the camera was stopped between attempts), so they are
grouped by what was said, across all clips.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from selects.transcribe import Word

TAKE_GAP_S = 1.5        # a pause longer than this starts a new take
DIALOG_SHARE = 0.3      # speech must fill at least this share of a clip for it to be dialog
MIN_LINE_WORDS = 5      # a dialog clip needs at least this many words
SAME_LINE = 0.5         # text similarity (0-1) above which two takes are the same line
FILLERS = {"a", "aa", "aaa", "ă", "ăă", "ăăă", "î", "îî", "îîî", "m", "mm", "hm", "hmm", "eee", "ee"}
WEIGHTS = {"complete": 0.4, "clear": 0.3, "picture": 0.3}
FILLER_COST = 0.05      # taken off the score for every filler sound
HANDLE_BEFORE_S = 0.25  # room kept before the first word, so the cut is not too tight
HANDLE_AFTER_S = 0.5    # room kept after the last word


@dataclass
class Take:
    clip: str
    words: list[Word]
    group: int = -1                      # takes with the same group number say the same line
    picture: float = 1.0                 # picture quality during the take, 0-1 (1 = unknown)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def tokens(self) -> list[str]:
        return [token for word in self.words if (token := normalize(word.text))]


def normalize(text: str) -> str:
    """Lowercase, no diacritics, no punctuation: 'Bună,' and 'buna' count as the same word."""
    without_marks = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in without_marks if not unicodedata.combining(ch))
    return re.sub(r"[^\w]", "", without_marks.lower())


def is_dialog(words: list[Word], clip_duration: float) -> bool:
    """True when someone talks through a good part of the clip.

    A few words in a B-roll clip are usually the crew talking off camera, or the
    model inventing a phrase in background noise; those clips stay B-roll.
    """
    if len(words) < MIN_LINE_WORDS or clip_duration <= 0:
        return False
    speaking = sum(take.end - take.start for take in split_takes("", words))
    return speaking / clip_duration >= DIALOG_SHARE


def split_takes(clip: str, words: list[Word], gap: float = TAKE_GAP_S) -> list[Take]:
    """Cut the words of one clip into takes wherever the speaker pauses longer than gap."""
    takes: list[Take] = []
    for word in words:
        if takes and word.start - takes[-1].end <= gap:
            takes[-1].words.append(word)
        else:
            takes.append(Take(clip, [word]))
    return takes


def similarity(a: Take, b: Take) -> float:
    """How alike two takes are by their words, 0 (nothing shared) to 1 (identical)."""
    content_a = [t for t in a.tokens if t not in FILLERS]
    content_b = [t for t in b.tokens if t not in FILLERS]
    return SequenceMatcher(None, content_a, content_b).ratio()


def group_takes(takes: list[Take], threshold: float = SAME_LINE) -> None:
    """Give takes that say the same line the same group number (in place)."""
    next_group = 0
    for index, take in enumerate(takes):
        for earlier in takes[:index]:
            if similarity(take, earlier) >= threshold:
                take.group = earlier.group
                break
        else:
            take.group = next_group
            next_group += 1


def count_fillers(take: Take) -> int:
    return sum(1 for token in take.tokens if token in FILLERS)


def count_restarts(take: Take) -> int:
    """Words said twice in a row ('pe pe', 'noi noi'): the usual sign of a stumble."""
    tokens = [t for t in take.tokens if t not in FILLERS]
    return sum(1 for first, second in zip(tokens, tokens[1:]) if first == second)


def score_takes(takes: list[Take]) -> None:
    """Score every take against the other takes of the same line (in place).

    complete = share of the line's longest version that this take says
    clear    = the model's average confidence in the words (mumbling scores low)
    picture  = picture quality during the take (take.picture, from the B-roll
               scores); 1 when unknown, so the audio alone decides
    """
    for take in takes:
        siblings = [t for t in takes if t.group == take.group]
        longest = max(len([x for x in t.tokens if x not in FILLERS]) for t in siblings) or 1
        said = len([x for x in take.tokens if x not in FILLERS])

        complete = min(1.0, said / longest)
        clear = sum(w.probability for w in take.words) / len(take.words)
        fillers, restarts = count_fillers(take), count_restarts(take)

        take.score = (WEIGHTS["complete"] * complete + WEIGHTS["clear"] * clear
                      + WEIGHTS["picture"] * take.picture - FILLER_COST * (fillers + restarts))
        take.reasons = [
            f"complete {complete:.0%}",
            f"clear {clear:.2f}",
            f"picture {take.picture:.2f}",
        ]
        if fillers:
            take.reasons.append(f"{fillers} filler sound(s)")
        if restarts:
            take.reasons.append(f"{restarts} repeated word(s)")


def best_takes(takes: list[Take]) -> dict[int, Take]:
    """The highest scoring take of every line. On a tie the later take wins (usually the
    speaker's most practised attempt)."""
    best: dict[int, Take] = {}
    for take in takes:
        current = best.get(take.group)
        if current is None or take.score >= current.score:
            best[take.group] = take
    return best

