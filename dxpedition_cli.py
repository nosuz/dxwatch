#!/usr/bin/env python3
"""CLI tool to insert or update DX-pedition records from a JSON file.

Usage:
    python dxpedition_cli.py data.json
    python dxpedition_cli.py data.json --db path/to/spots.db

JSON format — single object or array of objects:
    [
      {
        "callsign": "3Y0J",
        "entity_name": "Bouvet Island",
        "dxcc": 24,
        "grid": "JD78",
        "start_dt": "2025-01-15",
        "end_dt": "2025-02-01",
        "url": "https://example.com",
        "notes": "..."
      }
    ]

Upsert key: callsign (case-insensitive). If the callsign already exists,
the record is updated; otherwise a new row is inserted.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = str(Path("data") / "spots.db")


def upsert(db: sqlite3.Connection, record: dict) -> str:
    callsign = (record.get("callsign") or "").strip().upper()
    if not callsign:
        raise ValueError("'callsign' field is required")

    cur = db.execute("SELECT id FROM dxpedition WHERE callsign = ?", (callsign,))
    row = cur.fetchone()

    if row:
        db.execute(
            """
            UPDATE dxpedition
            SET entity_name=?, dxcc=?, grid=?, start_dt=?, end_dt=?, url=?, notes=?,
                updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
            WHERE callsign=?
            """,
            (
                record.get("entity_name"),
                record.get("dxcc"),
                record.get("grid"),
                record.get("start_dt"),
                record.get("end_dt"),
                record.get("url"),
                record.get("notes"),
                callsign,
            ),
        )
        return "updated"
    else:
        db.execute(
            """
            INSERT INTO dxpedition(callsign, entity_name, dxcc, grid, start_dt, end_dt, url, notes)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                callsign,
                record.get("entity_name"),
                record.get("dxcc"),
                record.get("grid"),
                record.get("start_dt"),
                record.get("end_dt"),
                record.get("url"),
                record.get("notes"),
            ),
        )
        return "inserted"


def main():
    parser = argparse.ArgumentParser(
        description="Insert or update DX-pedition records from a JSON file."
    )
    parser.add_argument("json_file", help="JSON file (single object or array of objects)")
    parser.add_argument("--db", default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    args = parser.parse_args()

    path = Path(args.json_file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    with open(path) as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error: invalid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    if isinstance(data, dict):
        records = [data]
    elif isinstance(data, list):
        records = data
    else:
        print("Error: JSON must be an object or array of objects", file=sys.stderr)
        sys.exit(1)

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(db_path))
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS dxpedition (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            callsign    TEXT    NOT NULL,
            entity_name TEXT,
            dxcc        INTEGER,
            grid        TEXT,
            start_dt    TEXT,
            end_dt      TEXT,
            url         TEXT,
            notes       TEXT,
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
        """
    )
    db.commit()
    errors = 0
    try:
        for record in records:
            try:
                action = upsert(db, record)
                callsign = (record.get("callsign") or "").strip().upper()
                print(f"{action}: {callsign}")
            except Exception as e:
                print(f"Error: {e} — record: {record}", file=sys.stderr)
                errors += 1
        db.commit()
    finally:
        db.close()

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
