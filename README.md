# SELECTS

SELECTS finds the usable part of each video clip, so an editor does not have to watch every take to find it.

It reads a folder of camera clips and measures every second of video for sharpness, exposure and camera shake. For each clip it recommends the best segment, says why the rest was cut, and checks its choices against the segments an editor picked by hand.

I built it for my own work: I film weddings, events and business content on a Sony FX30. A three-minute video usually starts from 40–50 minutes of footage, and most of the time goes into finding the few good seconds in each clip.

> **Status:** catalog, proxies, visual signals, best-segment choice and evaluation work and are tested.
> Choosing between dialog takes and exporting to DaVinci Resolve are planned (see [Roadmap](#roadmap)).

## What it does

```
$ python -m selects analyze

LCS_FX30_4654.MP4: 14-24 s
  14-24 s kept: mean score 0.72, shake 0.50 (clip 1.32)
  0-14 s cut: shake
  24-27 s cut: shake
```

The per-second signals behind a decision can be inspected next to the editor's own pick:

```
$ python -m selects signals 3410

LCS_FX30_3410.MP4   your pick: 0-1.5 s   problems: shake
   sec  sharpness (vs sharpest second) bright  white%  black%  motion  shake
    0s  ###################       62.4    104     0.0     0.0       5   0.04  <- your pick
    1s  ####################      67.3    104     0.0     0.0       2   0.04  <- your pick
    2s  ################          54.6    105     0.0     0.0       4   0.13
    3s  ################          53.9    106     0.0     0.0       2   0.22
    4s  #######                   23.0    107     0.0     0.0     191   1.64
```

The last second is where the camera was stopped: the picture moves fast (`motion` 191) and unevenly (`shake` 1.64).

## How it works

```
camera clips ──► 1 catalog ──► 2 proxies ──► 3 signals per second ──► 4 best segment ──► 5 evaluation
 (MP4 + XML)     ffprobe +     720p H.264    sharpness, exposure,     score, cut,         overlap with
                 Sony XML      + Sony LUT    camera motion / shake    reasons             hand labels
                      └──────────── all results stored in DuckDB ─────────────┘
```

1. **Catalog.** `ffprobe` gives the technical facts of each clip (codec, resolution, frame rate, rotation, recording time in UTC). The Sony XML sidecar says whether the clip was shot in S-Log3. Everything goes into a DuckDB table.
2. **Proxies.** The originals are 4K, 10-bit 4:2:2 and decode slowly, so FFmpeg makes small 720p 8-bit proxies for analysis. Log clips get Sony's S-Log3/S-Gamut3.Cine → Rec.709 LUT in the same pass, so they look normal before they are measured. The originals are never changed.
3. **Signals, one value per second** (median or mean of all frames in that second):
   - **Sharpness:** variance of the Laplacian. Crisp edges give a high value and blur gives a low one. It is compared only within the same clip, because a dark or misty scene has few edges even when it is in focus.
   - **Exposure:** mean brightness plus the share of pure white (≥ 250) and pure black (≤ 8) pixels. This catches black frames and underexposed parts.
   - **Camera motion:** corners are tracked from frame to frame with Lucas–Kanade optical flow, and one shift is fitted to them with RANSAC, so a person walking through the frame does not count as camera movement. A 0.5 s moving average of that shift is the intended move (`motion`, e.g. a pan). What is left on top of it is `shake`.
4. **Best segment.**
   - Each second gets a score from 0 to 1 that loses points for shake (60 %), blur (25 %) and darkness (15 %).
   - Black frames and seconds with no trackable picture are never kept.
   - A second must beat the clip's own 40th percentile score, and always 0.5. This way a mostly good clip still gets trimmed to its best part.
   - The kept segment is the continuous run, at least 2 s long, whose scores add up best above that bar (maximum subarray). It grows over good footage and stops where the footage gets worse.
5. **Evaluation.** The chosen segment is compared with the one the editor marked, as overlap (intersection over union: 1 = same seconds, 0 = none in common).

## Results so far

The test set is 13 of my own FX30 clips (S-Log3, 25 and 50 fps, horizontal and vertical, 2.6 minutes in total). I labelled the best segment of each clip by hand **before** writing any of the algorithms.

| | |
|---|---|
| B-roll clips where my pick has less shake than the rest of the clip | **8 of 8** (median shake 0.38 inside vs 1.16 outside) |
| Mean overlap between the chosen segment and my pick (8 usable B-roll clips) | **0.54** (a fixed quality bar gave 0.42) |
| Clips I marked unusable that it also rejected | **0 of 3** |
| Proxy speed on an Apple M4 MacBook Pro | 1.55× real time |
| Full analysis of the 13 clips | about 12 s |

What these numbers do **not** show:
- **The sample is small, and the 40 % bar was chosen on these same clips.** The 0.54 is therefore optimistic. The next step is to measure it on new clips the algorithm has not seen.
- **Some choices cannot be seen in these signals.** In one clip I preferred a darker but meaningful moment to a brighter one. In two others the clip was ruined by a false start and by a person walking in front of the lens. In a fourth the focus was wrong for the whole clip, so there is no sharper second to compare with.
- **Dialog clips (2 of the 13) are left out of the scores.** For those I chose the take by what was said, which visual signals cannot judge.

## Quick start

Requirements: macOS or Linux, Python 3.12 or newer (developed on 3.14), FFmpeg with `ffprobe`. For S-Log3 footage you also need the Sony LUT that comes with DaVinci Resolve; on other systems change `DEFAULT_SONY_LUT` in `selects/proxies.py`.

```bash
git clone https://github.com/lucascristian/selects.git
cd selects
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
python -m selects scan data/raw     # add every clip in the folder to the catalog
python -m selects proxies           # make 720p analysis proxies
python -m selects report            # summary: clips, minutes, size, proxy speed
python -m selects analyze           # measure signals and choose the best segments
python -m selects signals [clip]    # per-second table next to your labels
python -m selects evaluate          # compare the choices with your labels
```

The database lives in `data/selects.duckdb` (change it with `--db`) and the proxies in `data/proxies/`. The `data/` folder is not committed, because footage and labels are private.

### Labels file

`data/labels.csv` holds one row per clip with the segment an editor would actually use:

```
file_name,start_s,end_s,problems,note
LCS_FX30_4577.MP4,1,4,focus+shake,focus missed at the start; shake at the end
LCS_FX30_6757.MP4,,,other,nothing usable; someone walked in front of the camera
LCS_FX30_6577.MP4,14,23,none,dialog;the good take
```

- Times are in seconds.
- Leave both times empty when nothing in the clip is usable.
- `problems` uses `shake`, `focus`, `exposure`, `other` or `none`, joined with `+`.
- A note starting with `dialog` keeps the clip out of the B-roll evaluation.

## Project layout

```
selects/
  probe.py          ffprobe metadata: duration, video stream, frame rate, rotation
  sony_xml.py       Sony XML sidecar: find it, read the gamma, detect log footage
  catalog.py        scan a folder into clip records
  database.py       DuckDB tables: clips, proxies, signals, picks
  proxies.py        FFmpeg proxy command with the LUT
  signals.py        sharpness, exposure, camera motion and shake per second
  best_segment.py   per-second scores, best run, reasons
  labels.py         read and check the hand-made labels
  evaluate.py       overlap between chosen and labelled segments
  __main__.py       command line interface
tests/              pytest suite (62 tests, no footage needed)
```

## Tests

```bash
python -m pytest
```

The tests use small made-up inputs instead of real footage, so they run anywhere:
- metadata dictionaries and XML strings;
- a checkerboard and its blurred copy for sharpness;
- a noise image shifted by a known number of pixels for motion;
- a tiny generated video file.

## Roadmap

- [x] Catalog with ffprobe and Sony XML metadata, stored in DuckDB
- [x] 720p analysis proxies with the S-Log3 → Rec.709 LUT
- [x] Per-second sharpness, exposure and camera motion / shake
- [x] Best segment with reasons, and evaluation against hand labels
- [ ] Dialog clips: transcribe speech, group takes of the same line, recommend the best take
- [ ] Export to DaVinci Resolve: recommended segments as markers or subclips on a timeline
- [ ] Larger labelled set, with clips kept aside for testing only
- [ ] Simple review interface

## Built with

Python, OpenCV, NumPy, DuckDB, FFmpeg, pytest.
