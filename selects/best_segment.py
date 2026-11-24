"""Choose the best segment of a B-roll clip from its per-second signals.

Every second gets a score from 0 (bad) to 1 (clean). The bar a second must
clear is set per clip (the clip's own 40th percentile, never below 0.5), so in
a mostly good clip only its best part is kept. The chosen segment is the run of
seconds whose scores add up best above that bar: it grows over good seconds
and stops where the footage turns worse. Black frames are never crossed.
"""

import math
from dataclasses import dataclass, field

import numpy as np

# Thresholds picked by looking at the first 13 labelled FX30 clips.
# They are a starting point, not tuned on a separate test set.
SHAKE_BAD = 1.5         # shake at or above this costs the full shake penalty
SHARP_OK = 0.5          # share of the clip's sharp level that costs nothing
BLACK_FRAME = 50.0      # % of pure black pixels that makes a second unusable
DARK = 40.0             # mean brightness below this is a (small) penalty
WEIGHTS = {"shake": 0.6, "blur": 0.25, "dark": 0.15}

QUALITY_BAR = 0.5       # no second scoring at or below this is ever worth keeping
BAR_QUANTILE = 0.4      # per clip, a kept second must also beat 40 % of the clip's seconds
MIN_LENGTH_S = 2        # shorter segments are not worth recommending


@dataclass
class Pick:
    start_s: int | None     # None = no part of the clip is usable
    end_s: int | None
    score: float            # mean score of the chosen seconds (0 when nothing is usable)
    reasons: list[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        return self.start_s is not None


def ramp(value: float, ok: float, bad: float) -> float:
    """0 when value is at the ok level, 1 at the bad level, a straight line between."""
    return min(1.0, max(0.0, (value - ok) / (bad - ok)))


def second_penalties(signals: dict[str, list[float]]) -> list[dict[str, float]]:
    """For each second, how much each problem hurts it (0 = not at all, 1 = fully)."""
    sharpness = np.array(signals["sharpness"])
    sharp_level = float(np.percentile(sharpness, 90)) or 1.0

    penalties = []
    for second, sharp in enumerate(sharpness):
        shake = signals["shake"][second]
        brightness = signals["brightness"][second]
        black = signals["shadows"][second]
        penalties.append({
            "black frame": 1.0 if black >= BLACK_FRAME else 0.0,
            "no motion data": 1.0 if math.isnan(shake) else 0.0,
            "shake": 0.0 if math.isnan(shake) else ramp(shake, 0.0, SHAKE_BAD),
            "blur": ramp(-sharp / sharp_level, -SHARP_OK, 0.0),
            "dark": ramp(-brightness, -DARK, 0.0),
        })
    return penalties


def second_scores(penalties: list[dict[str, float]]) -> list[float | None]:
    """Turn penalties into a 0-1 score. None = unusable (black frame, no motion data)."""
    scores = []
    for p in penalties:
        if p["black frame"] or p["no motion data"]:
            scores.append(None)
            continue
        cost = WEIGHTS["shake"] * p["shake"] + WEIGHTS["blur"] * p["blur"] + WEIGHTS["dark"] * p["dark"]
        scores.append(1.0 - cost)
    return scores


def clip_bar(scores: list[float | None]) -> float:
    """The quality bar for one clip: its 40th percentile score, but never below 0.5."""
    known = [s for s in scores if s is not None]
    if not known:
        return QUALITY_BAR
    return max(QUALITY_BAR, float(np.quantile(known, BAR_QUANTILE)))


def best_run(scores: list[float | None], bar: float, min_length: int) -> tuple[int, int] | None:
    """Seconds [start, end) whose (score - bar) adds up to the most (maximum subarray).

    Every second above the bar adds to the total and every second below takes
    away, so the run stretches over good footage and stops at worse footage.
    An unusable second (None) ends the run. A tiny bonus per second makes a
    longer run win a tie. Returns None when no run of at least min_length
    seconds has a positive total.
    """
    best, best_total = None, 0.0
    for start in range(len(scores)):
        total = 0.0
        for end in range(start + 1, len(scores) + 1):
            if scores[end - 1] is None:
                break
            total += scores[end - 1] - bar + 1e-6
            if end - start >= min_length and total > best_total:
                best, best_total = (start, end), total
    return best


def main_problem(penalty: dict[str, float]) -> str:
    return max(penalty, key=penalty.get)


def explain_cuts(penalties: list[dict[str, float]], scores: list[float | None],
                 start: int, end: int) -> list[str]:
    """Describe why the seconds outside the pick were left out, grouped into ranges."""
    reasons = []
    for first, last in [(0, start), (end, len(scores))]:
        second = first
        while second < last:
            problem = main_problem(penalties[second])
            run_end = second
            while run_end + 1 < last and main_problem(penalties[run_end + 1]) == problem:
                run_end += 1
            worst = max(penalties[s][problem] for s in range(second, run_end + 1))
            label = problem if worst > 0 else "weaker than the pick"
            reasons.append(f"{second}-{run_end + 1} s cut: {label}")
            second = run_end + 1
    return reasons


def choose_segment(signals: dict[str, list[float]]) -> Pick:
    """The recommended segment of one clip, with reasons a person can check."""
    penalties = second_penalties(signals)
    scores = second_scores(penalties)
    run = best_run(scores, clip_bar(scores), MIN_LENGTH_S)

    if run is None:
        problems = {main_problem(p) for p, s in zip(penalties, scores)
                    if s is None or s <= QUALITY_BAR}
        why = ", ".join(sorted(problems)) or "no run of good seconds is long enough"
        return Pick(None, None, 0.0, [f"nothing usable: {why}"])

    start, end = run
    chosen = scores[start:end]
    shake = [signals["shake"][s] for s in range(start, end)]
    reasons = [
        f"{start}-{end} s kept: mean score {np.mean(chosen):.2f}, "
        f"shake {np.nanmedian(shake):.2f} (clip {np.nanmedian(signals['shake']):.2f})",
    ]
    reasons += explain_cuts(penalties, scores, start, end)
    return Pick(start, end, float(np.mean(chosen)), reasons)
