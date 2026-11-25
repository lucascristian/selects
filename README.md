# SELECTS

SELECTS finds the usable part of each video clip, so an editor does not have to watch every take to find it.

It reads a folder of camera clips and measures every second of video for sharpness, exposure and camera shake. For each B-roll clip it recommends the best segment and says why the rest was cut. For clips where someone talks to the camera, it transcribes the speech, finds the repeated takes of the same line and recommends the best one. Every choice can be checked against the segments an editor picked by hand.

I built it for my own work: I film weddings, events and business content on a Sony FX30. A three-minute video usually starts from 40–50 minutes of footage, and most of the time goes into finding the few good seconds in each clip.

> **Status:** catalog, proxies, visual signals, best B-roll segment, dialog takes and evaluation work and are tested.
> Exporting to DaVinci Resolve is planned (see [Roadmap](#roadmap)).

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

For dialog it compares the takes of each line:

```
$ python -m selects takes

Some speech but not dialog (kept as B-roll): LCS_FX30_3459.MP4, LCS_FX30_4577.MP4, ...

Line 1: "Hey guys, bine v -am găsit la prima suptămâna de facultate. ..."  (2 take(s))
  LCS_FX30_6577.MP4   5.7- 11.5 s  score 0.78  (complete 79%, clear 0.83, picture 0.71)
      "Hey guys, bine v -am găsit la prima suptămâna de facultate. Astăzi mă vom muta încă mi... Pah, încoată."
  LCS_FX30_6577.MP4  13.9- 20.8 s  score 0.92  (complete 100%, clear 0.98, picture 0.74)  <- best
      "Hey guys, bine v -am găsit la prima suptămâna de facultate. Stau în cameră cu încă 4 băiți. ..."
```

The first take falls apart at the end. The words the model is unsure about ("mi... Pah, încoată") lower its `clear` score.

## How it works

```
camera clips ──► 1 catalog ──► 2 proxies ──► 3 signals per second ──► 4 best segment ─┐
 (MP4 + XML)     ffprobe +     720p H.264    sharpness, exposure,     score, cut,      │
                 Sony XML      + Sony LUT    camera motion / shake    reasons          ├─► 6 evaluation
                      │                                                                │   overlap with
                      └──────► 5 speech ──► takes ──► group repeats ──► best take ─────┘   hand labels
                               faster-whisper, word timestamps, local
                      (all results stored in DuckDB)
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
5. **Dialog takes.**
   - **Transcription.** FFmpeg decodes the audio, and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`large-v3-turbo`, run locally on the CPU) turns it into Romanian text with a timestamp and a confidence value for every word.
   - **Dialog or B-roll.** A clip counts as dialog only when speech fills at least 30 % of it (and has at least 5 words). Off-camera directions from the crew, and phrases the model invents in background noise, stay B-roll.
   - **Takes and lines.** A pause longer than 1.5 s starts a new take. Takes are compared word by word, after removing case, punctuation, diacritics and filler sounds. Takes that are at least 50 % alike are attempts at the same line, even when they sit in different clips.
   - **Best take.** Each take is scored on three things:
     - complete (40 %): how much of the line's longest version it says;
     - clear (30 %): the model's mean confidence, which drops on mumbled or stumbled words;
     - picture (30 %): the B-roll score of the seconds it covers.

     Each filler sound or word said twice in a row costs a little. On a tie the later take wins. The recommended range keeps 0.25 s before the first word and 0.5 s after the last.
6. **Evaluation.** The chosen segment or take is compared with the one the editor marked, as overlap (intersection over union: 1 = same seconds, 0 = none in common).

## Results so far

The test set is 13 of my own FX30 clips (S-Log3, 25 and 50 fps, horizontal and vertical, 2.6 minutes in total). I labelled the best segment of each clip by hand **before** writing any of the algorithms.

| | |
|---|---|
| B-roll clips where my pick has less shake than the rest of the clip | **8 of 8** (median shake 0.38 inside vs 1.16 outside) |
| Mean overlap between the chosen segment and my pick (8 usable B-roll clips) | **0.54** (a fixed quality bar gave 0.42) |
| Clips I marked unusable that it also rejected | **0 of 3** |
| Clips where it decided "dialog" or "B-roll" the same way I did | **13 of 13** (2 dialog, 11 B-roll) |
| Mean overlap between the recommended take and my pick (2 dialog clips) | **0.84** (0.78 and 0.90) |
| Proxy speed on an Apple M4 MacBook Pro | 1.55× real time |
| Full visual analysis of the 13 clips | about 12 s |
| Transcription of the 13 clips (2.6 min of audio, CPU) | about 45 s |

What these numbers do **not** show:
- **The sample is small, and the 40 % bar was chosen on these same clips.** The 0.54 is therefore optimistic. The next step is to measure it on new clips the algorithm has not seen.
- **Some choices cannot be seen in these signals.** In one clip I preferred a darker but meaningful moment to a brighter one. In two others the clip was ruined by a false start and by a person walking in front of the lens. In a fourth the focus was wrong for the whole clip, so there is no sharper second to compare with.
- **The dialog result rests on 2 clips and 3 takes.** That proves the pipeline works end to end, but not much more. More dialog clips with several takes each are needed. The dialog clips are kept out of the B-roll numbers above.
- **The transcript is not perfect.** It writes "suptămâna" for "săptămâna" and "băiți" for "băieți". Takes are matched on whole words, so small spelling errors matter less than they seem.

## Quick start

Requirements:
- macOS or Linux;
- Python 3.12 or newer (developed on 3.14);
- FFmpeg with `ffprobe`;
- for S-Log3 footage, the Sony LUT that comes with DaVinci Resolve. On other systems change `DEFAULT_SONY_LUT` in `selects/proxies.py`.

The first `transcribe` downloads the speech model from Hugging Face (about 1.6 GB).

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
python -m selects transcribe        # speech to text with word timestamps
python -m selects takes             # group the takes of each line, recommend the best
python -m selects evaluate          # compare segments and takes with your labels
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
- A note starting with `dialog` marks a clip where someone talks to the camera. It is evaluated against the recommended take instead of the B-roll segment.

## Project layout

```
selects/
  probe.py          ffprobe metadata: duration, video stream, frame rate, rotation
  sony_xml.py       Sony XML sidecar: find it, read the gamma, detect log footage
  catalog.py        scan a folder into clip records
  database.py       DuckDB tables: clips, proxies, signals, picks, words, takes
  proxies.py        FFmpeg proxy command with the LUT
  signals.py        sharpness, exposure, camera motion and shake per second
  best_segment.py   per-second scores, best run, reasons
  transcribe.py     audio with FFmpeg, faster-whisper words with timestamps
  takes.py          dialog or not, takes, lines, best take
  labels.py         read and check the hand-made labels
  evaluate.py       overlap between chosen and labelled segments
  __main__.py       command line interface
tests/              pytest suite (77 tests, no footage or speech model needed)
```

## Tests

```bash
python -m pytest
```

The tests use small made-up inputs instead of real footage, so they run anywhere:
- metadata dictionaries and XML strings;
- a checkerboard and its blurred copy for sharpness;
- a noise image shifted by a known number of pixels for motion;
- a tiny generated video file;
- made-up transcripts, and a stand-in for the speech model.

## Roadmap

- [x] Catalog with ffprobe and Sony XML metadata, stored in DuckDB
- [x] 720p analysis proxies with the S-Log3 → Rec.709 LUT
- [x] Per-second sharpness, exposure and camera motion / shake
- [x] Best segment with reasons, and evaluation against hand labels
- [x] Dialog clips: transcribe speech, group takes of the same line, recommend the best take
- [ ] Export to DaVinci Resolve: recommended segments as markers or subclips on a timeline
- [ ] Larger labelled set, with clips kept aside for testing only
- [ ] Simple review interface

## Built with

Python, OpenCV, NumPy, DuckDB, FFmpeg, faster-whisper, pytest.
