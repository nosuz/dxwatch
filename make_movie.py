#!/usr/bin/env python3
"""Assemble a day's PNG snapshots into an MP4 timelapse.

Usage:
  python make_movie.py                          # yesterday, 30 s total
  python make_movie.py 2025-03-25               # specific date, 30 s total
  python make_movie.py 2025-03-25 --duration 60 # specific date, 60 s total
"""

import argparse
from datetime import date, timedelta
from pathlib import Path
import subprocess

OUT_DIR = Path(__file__).parent / "data" / "timelapse"

DEFAULT_DURATION = 30  # total video length in seconds


def make_movie(target_date: date, total_seconds: int = DEFAULT_DURATION) -> Path | None:
    day_dir = OUT_DIR / target_date.isoformat()
    frames = sorted(day_dir.glob("*.png")) if day_dir.exists() else []
    if len(frames) < 2:
        print(f"[make_movie] {target_date}: only {len(frames)} frame(s), skipping")
        return None

    frame_duration = total_seconds / len(frames)
    out_path = OUT_DIR / f"{target_date.isoformat()}.mp4"

    list_file = day_dir / "frames.txt"
    with open(list_file, "w") as f:
        for p in frames:
            f.write(f"file '{p.resolve()}'\n")
            f.write(f"duration {frame_duration}\n")
        # ffmpeg concat needs the last file listed twice (no trailing duration)
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
    print(f"[make_movie] saved {out_path}  ({len(frames)} frames, {frame_duration:.2f} s/frame, {total_seconds} s total)")
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate FT8 spot timelapse video")
    parser.add_argument("date", nargs="?", type=date.fromisoformat,
                        default=date.today() - timedelta(days=1),
                        help="Date to process (YYYY-MM-DD, default: yesterday)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help=f"Total video duration in seconds (default: {DEFAULT_DURATION})")
    args = parser.parse_args()
    make_movie(args.date, args.duration)
