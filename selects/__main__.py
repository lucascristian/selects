"""Command line entry point: python -m selects <command>.

Commands:
    scan FOLDER   read every clip in FOLDER and save it to the catalog
    proxies       make an analysis proxy for every clip in the catalog
    report        print a short summary of the catalog
    signals       print per-second sharpness, exposure and camera motion next to your labels
    analyze       measure every proxy, save the signals and choose the best segment
    evaluate      compare the chosen segments with your labels
"""

import argparse
import math
import subprocess
from pathlib import Path

from selects.catalog import scan_folder
from selects.best_segment import choose_segment
from selects.database import connect, save_clips, save_pick, save_proxy, save_signals
from selects.evaluate import compare
from selects.labels import load_labels
from selects.proxies import DEFAULT_SONY_LUT, make_proxy, proxy_path_for
from selects.signals import measure_signals

DEFAULT_DB = Path("data/selects.duckdb")
DEFAULT_PROXIES_DIR = Path("data/proxies")
DEFAULT_LABELS = Path("data/labels.csv")
BAR_WIDTH = 20


def run_scan(con, folder: Path) -> None:
    records, problems = scan_folder(folder)
    save_clips(con, records)
    print(f"Catalogued {len(records)} clip(s) from {folder}")
    for problem in problems:
        print(f"  Skipped {problem}")


def run_proxies(con, proxies_dir: Path) -> None:
    clips = con.execute(
        "SELECT path, file_name, duration_s, is_log FROM clips ORDER BY path"
    ).fetchall()
    if not clips:
        print("The catalog is empty. Run: python -m selects scan <folder>")
        return

    for path, file_name, duration_s, clip_is_log in clips:
        lut_path = None
        if clip_is_log:
            if DEFAULT_SONY_LUT.exists():
                lut_path = DEFAULT_SONY_LUT
            else:
                print(f"  Warning: LUT not found, {file_name} stays in log")

        proxy_path = proxy_path_for(Path(path), proxies_dir)
        try:
            seconds = make_proxy(Path(path), proxy_path, lut_path)
        except subprocess.CalledProcessError as error:
            print(f"  Failed {file_name}: {error.stderr.strip()}")
            continue

        save_proxy(con, path, str(proxy_path), lut_path is not None, seconds)
        speed = duration_s / seconds
        lut_note = "with LUT" if lut_path else "no LUT"
        print(f"  {file_name}: {seconds:.1f} s for {duration_s:.1f} s of video "
              f"({speed:.2f}x real time, {lut_note})")


def run_report(con) -> None:
    total = con.execute(
        "SELECT count(*), coalesce(sum(duration_s), 0), coalesce(sum(size_bytes), 0) FROM clips"
    ).fetchone()
    print(f"Clips: {total[0]}   Footage: {total[1] / 60:.1f} min   Size: {total[2] / 1e9:.2f} GB")

    rows = con.execute("""
        SELECT is_log, count(*) AS clips, round(sum(duration_s) / 60, 1) AS minutes
        FROM clips
        GROUP BY is_log
        ORDER BY is_log DESC
    """).fetchall()
    for clip_is_log, clips, minutes in rows:
        label = "Log (S-Log3)" if clip_is_log else "Not log"
        print(f"  {label}: {clips} clip(s), {minutes} min")

    speed = con.execute("""
        SELECT round(sum(c.duration_s) / sum(p.seconds), 2)
        FROM proxies AS p JOIN clips AS c ON c.path = p.clip_path
    """).fetchone()[0]
    if speed is not None:
        print(f"  Proxy speed: {speed}x real time")


def show(value: float, width: int, decimals: int) -> str:
    """Format a number for the table; unknown values (NaN) print as a dash."""
    if math.isnan(value):
        return f"{'-':>{width}}"
    return f"{value:{width}.{decimals}f}"


def describe_label(label) -> str:
    if label is None:
        return "no label"
    problems = "+".join(sorted(label.problems)) or "-"
    if not label.usable:
        return f"your pick: nothing usable   problems: {problems}"
    return f"your pick: {label.start_s:g}-{label.end_s:g} s   problems: {problems}"


def run_signals(con, labels_path: Path, only: str | None) -> None:
    rows = con.execute("""
        SELECT c.file_name, p.proxy_path
        FROM clips AS c JOIN proxies AS p ON p.clip_path = c.path
        ORDER BY c.file_name
    """).fetchall()
    if not rows:
        print("No proxies yet. Run: python -m selects proxies")
        return
    labels = load_labels(labels_path) if labels_path.exists() else {}

    for file_name, proxy_path in rows:
        if only and only not in file_name:
            continue
        label = labels.get(file_name)
        signals = measure_signals(Path(proxy_path))
        top = max(signals["sharpness"]) or 1.0

        print(f"\n{file_name}   {describe_label(label)}")
        print(f"  {'sec':>4}  {'sharpness (vs sharpest second)':<{BAR_WIDTH + 10}}"
              f"{'bright':>7}{'white%':>8}{'black%':>8}{'motion':>8}{'shake':>7}")
        for second, value in enumerate(signals["sharpness"]):
            bar = "#" * round(BAR_WIDTH * value / top)
            in_pick = (label is not None and label.usable
                       and second < label.end_s and second + 1 > label.start_s)
            mark = "  <- your pick" if in_pick else ""
            print(f"  {second:3d}s  {bar:<{BAR_WIDTH}}  {value:8.1f}"
                  f"{signals['brightness'][second]:7.0f}"
                  f"{signals['highlights'][second]:8.1f}"
                  f"{signals['shadows'][second]:8.1f}"
                  f"{show(signals['motion'][second], 8, 0)}"
                  f"{show(signals['shake'][second], 7, 2)}{mark}")


def proxies_in_catalog(con) -> list[tuple[str, str, str]]:
    return con.execute("""
        SELECT c.path, c.file_name, p.proxy_path
        FROM clips AS c JOIN proxies AS p ON p.clip_path = c.path
        ORDER BY c.file_name
    """).fetchall()


def run_analyze(con) -> None:
    rows = proxies_in_catalog(con)
    if not rows:
        print("No proxies yet. Run: python -m selects proxies")
        return
    for clip_path, file_name, proxy_path in rows:
        signals = measure_signals(Path(proxy_path))
        pick = choose_segment(signals)
        save_signals(con, clip_path, signals)
        save_pick(con, clip_path, pick)

        where = f"{pick.start_s}-{pick.end_s} s" if pick.usable else "nothing usable"
        print(f"\n{file_name}: {where}")
        for reason in pick.reasons:
            print(f"  {reason}")


def show_range(segment: tuple | None) -> str:
    return "none" if segment is None else f"{segment[0]:g}-{segment[1]:g}"


def run_evaluate(con, labels_path: Path) -> None:
    if not labels_path.exists():
        print(f"No labels file at {labels_path}")
        return
    labels = load_labels(labels_path)
    rows = con.execute("""
        SELECT c.file_name, k.start_s, k.end_s
        FROM picks AS k JOIN clips AS c ON c.path = k.clip_path
        ORDER BY c.file_name
    """).fetchall()
    if not rows:
        print("No picks yet. Run: python -m selects analyze")
        return

    print(f"{'clip':<20}{'yours':>10}{'picked':>10}{'overlap':>9}")
    usable_scores, empty_scores, skipped = [], [], []
    for file_name, start_s, end_s in rows:
        label = labels.get(file_name)
        if label is None or label.note.startswith("dialog"):
            skipped.append(file_name)
            continue
        yours = (label.start_s, label.end_s) if label.usable else None
        picked = (start_s, end_s) if start_s is not None else None
        result = compare(file_name, yours, picked)
        (usable_scores if label.usable else empty_scores).append(result.score)
        print(f"{file_name:<20}{show_range(yours):>10}{show_range(picked):>10}{result.score:9.2f}")

    if usable_scores:
        print(f"\nMean overlap on clips you marked usable: "
              f"{sum(usable_scores) / len(usable_scores):.2f} ({len(usable_scores)} clips)")
    if empty_scores:
        print(f"Clips you marked unusable that it also rejected: "
              f"{int(sum(empty_scores))} of {len(empty_scores)}")
    if skipped:
        print(f"Not evaluated (dialog or no label): {', '.join(skipped)}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="selects", description="SELECTS footage catalog")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="database file")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan", help="add every clip in a folder to the catalog")
    scan.add_argument("folder", type=Path)
    proxies = commands.add_parser("proxies", help="make analysis proxies for all clips")
    proxies.add_argument("--out", type=Path, default=DEFAULT_PROXIES_DIR)
    commands.add_parser("report", help="print a summary of the catalog")
    signals = commands.add_parser("signals", help="print per-second signals next to your labels")
    signals.add_argument("clip", nargs="?", help="only clips whose name contains this text")
    signals.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    commands.add_parser("analyze", help="measure proxies, save signals, choose best segments")
    evaluate = commands.add_parser("evaluate", help="compare chosen segments with your labels")
    evaluate.add_argument("--labels", type=Path, default=DEFAULT_LABELS)

    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(args.db)

    if args.command == "scan":
        run_scan(con, args.folder)
    elif args.command == "proxies":
        run_proxies(con, args.out)
    elif args.command == "report":
        run_report(con)
    elif args.command == "signals":
        run_signals(con, args.labels, args.clip)
    elif args.command == "analyze":
        run_analyze(con)
    elif args.command == "evaluate":
        run_evaluate(con, args.labels)

    con.close()


if __name__ == "__main__":
    main()
