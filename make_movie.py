#!/usr/bin/env python3
"""Assemble a day's PNG snapshots into MP4 timelapse movies.

Usage:
  python make_movie.py                          # yesterday, 30 s, snapshot movie
  python make_movie.py 2025-03-25               # specific date, 30 s
  python make_movie.py 2025-03-25 --duration 60 # 60 s total
  python make_movie.py 2025-03-25 --heatmap     # per-band heatmap movies
  python make_movie.py 2025-03-25 --all         # snapshot + all heatmap movies
"""

import argparse
import re
from datetime import date, timedelta
from pathlib import Path
import subprocess

FRAMES_DIR = Path(__file__).parent / "data" / "timelapse_frames"
OUT_DIR = Path(__file__).parent / "data" / "timelapse"

DEFAULT_DURATION = 30  # total video length in seconds


def _run_ffmpeg(frames: list[Path], list_file: Path, out_path: Path,
                total_seconds: int) -> Path:
    frame_duration = total_seconds / len(frames)
    with open(list_file, "w") as f:
        for p in frames:
            f.write(f"file '{p.resolve()}'\n")
            f.write(f"duration {frame_duration}\n")
        f.write(f"file '{frames[-1].resolve()}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-vf", "scale=-2:720",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-crf", "23",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def make_movie(target_date: date, total_seconds: int = DEFAULT_DURATION) -> Path | None:
    """Generate timelapse from regular spot snapshots (HH-MM.png)."""
    day_dir = FRAMES_DIR / target_date.isoformat()
    # Exclude heatmap PNGs — match only HH-MM.png
    frames = sorted(p for p in (day_dir.glob("??-??.png") if day_dir.exists() else []))
    if len(frames) < 2:
        print(f"[make_movie] {target_date}: only {len(frames)} snapshot frame(s), skipping")
        return None

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{target_date.isoformat()}.mp4"
    _run_ffmpeg(frames, day_dir / "frames.txt", out_path, total_seconds)
    frame_duration = total_seconds / len(frames)
    print(f"[make_movie] saved {out_path}  ({len(frames)} frames, {frame_duration:.2f} s/frame, {total_seconds} s total)")
    return out_path


def make_heatmap_movies(target_date: date,
                        total_seconds: int = DEFAULT_DURATION) -> list[Path]:
    """Generate one timelapse per band from heatmap PNGs (HH-MM-heatmap-<band>.png)."""
    day_dir = FRAMES_DIR / target_date.isoformat()
    if not day_dir.exists():
        print(f"[make_movie] {target_date}: no frames directory, skipping heatmaps")
        return []

    # Discover bands from filenames
    band_pattern = re.compile(r"^\d{2}-\d{2}-heatmap-(.+)\.png$")
    bands: set[str] = set()
    for p in day_dir.iterdir():
        m = band_pattern.match(p.name)
        if m:
            bands.add(m.group(1))

    if not bands:
        print(f"[make_movie] {target_date}: no heatmap frames found")
        return []

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_paths: list[Path] = []
    for band in sorted(bands):
        frames = sorted(day_dir.glob(f"??-??-heatmap-{band}.png"))
        if len(frames) < 2:
            print(f"[make_movie] {target_date} {band}: only {len(frames)} frame(s), skipping")
            continue
        out_path = OUT_DIR / f"{target_date.isoformat()}-heatmap-{band}.mp4"
        _run_ffmpeg(frames, day_dir / f"frames-heatmap-{band}.txt", out_path, total_seconds)
        frame_duration = total_seconds / len(frames)
        print(f"[make_movie] saved {out_path}  ({len(frames)} frames, {frame_duration:.2f} s/frame, {total_seconds} s total)")
        out_paths.append(out_path)

    return out_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate FT8 spot timelapse video(s)")
    parser.add_argument("date", nargs="?", type=date.fromisoformat,
                        default=date.today() - timedelta(days=1),
                        help="Date to process (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help=f"Total video duration in seconds (default: {DEFAULT_DURATION})")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--heatmap", action="store_true",
                       help="Generate per-band heatmap movies only")
    group.add_argument("--all", action="store_true",
                       help="Generate snapshot movie + all heatmap movies")
    args = parser.parse_args()

    if args.heatmap:
        make_heatmap_movies(args.date, args.duration)
    elif args.all:
        make_movie(args.date, args.duration)
        make_heatmap_movies(args.date, args.duration)
    else:
        make_movie(args.date, args.duration)
