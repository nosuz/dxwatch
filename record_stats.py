#!/usr/bin/env python3
"""
record_stats.py — Record per-band station count snapshots into spots.db.

Counts distinct Tx (sc) and Rx (rc) stations active in the last 3 minutes,
grouped by mode and band, and inserts one row per combination.

Modes (mutually exclusive):
  from_jp  — JP transmitting, DX receiving  (sa==339, ra!=339)
  to_jp    — DX transmitting, JP receiving  (ra==339, sa!=339)
  local    — JP transmitting, JP receiving  (sa==339, ra==339)

Usage:
    python record_stats.py

Cron examples:
    */10 * * * *  cd /workspaces && ~/venv/bin/python record_stats.py
    */15 * * * *  cd /workspaces && ~/venv/bin/python record_stats.py
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "spots.db"
WINDOW = 180  # seconds — matches server retention window
BANDS = ["80m", "40m", "30m", "20m", "17m", "15m", "12m", "10m", "6m"]


def init_table(db: sqlite3.Connection) -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS station_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at TEXT    NOT NULL,
            mode        TEXT    NOT NULL,
            band        TEXT    NOT NULL,
            tx_count    INTEGER NOT NULL,
            rx_count    INTEGER NOT NULL,
            spot_count  INTEGER NOT NULL
        )
    """)
    db.execute(
        "CREATE INDEX IF NOT EXISTS idx_stats_recorded_at ON station_stats(recorded_at)"
    )


def main() -> None:
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA busy_timeout = 5000")
    init_table(db)

    now = datetime.now(timezone.utc)
    cutoff = now.timestamp() - WINDOW
    recorded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    rows = db.execute(
        "SELECT payload FROM spots WHERE ts >= ?", (cutoff,)
    ).fetchall()

    # Parse and deduplicate by (sc, rc, spot_ts) — local spots appear on both MQTT topics
    seen: set = set()
    spots: list = []
    for (payload,) in rows:
        d = json.loads(payload)
        key = (d.get("sc"), d.get("rc"), d.get("ts"))
        if key not in seen:
            seen.add(key)
            spots.append(d)

    categories = {
        "from_jp": [s for s in spots if s.get("sa") == 339 and s.get("ra") != 339],
        "to_jp":   [s for s in spots if s.get("ra") == 339 and s.get("sa") != 339],
        "local":   [s for s in spots if s.get("sa") == 339 and s.get("ra") == 339],
    }

    total = 0
    for mode, mode_spots in categories.items():
        bands: dict = {}
        for s in mode_spots:
            band = s.get("b", "?")
            if band not in bands:
                bands[band] = {"tx": set(), "rx": set(), "spots": 0}
            if s.get("sc"):
                bands[band]["tx"].add(s["sc"])
            if s.get("rc"):
                bands[band]["rx"].add(s["rc"])
            bands[band]["spots"] += 1

        for band in BANDS:
            tx = len(bands[band]["tx"]) if band in bands else 0
            rx = len(bands[band]["rx"]) if band in bands else 0
            spots_n = bands[band]["spots"] if band in bands else 0
            db.execute(
                "INSERT INTO station_stats(recorded_at, mode, band, tx_count, rx_count, spot_count)"
                " VALUES(?, ?, ?, ?, ?, ?)",
                (recorded_at, mode, band, tx, rx, spots_n),
            )
            total += 1
            print(f"  {mode:8s}  {band:5s}  tx={tx:4d}  rx={rx:4d}  spots={spots_n:5d}")

    db.commit()
    db.close()
    print(f"{recorded_at}  {len(spots)} unique spots → {total} rows inserted")


if __name__ == "__main__":
    main()
