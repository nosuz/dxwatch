#!/usr/bin/env python3
"""Export dxpedition table from SQLite to an Excel file."""

import sqlite3
from pathlib import Path

from openpyxl import Workbook

DB_PATH = Path("data") / "spots.db"
OUTPUT_PATH = Path("data") / "DX_export.xlsx"

COLUMNS = [
    "id",
    "callsign",
    "entity_name",
    "dxcc",
    "grid",
    "start_dt",
    "end_dt",
    "url",
    "notes",
    "created_at",
    "updated_at",
]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            f"""
            SELECT {", ".join(COLUMNS)}
            FROM dxpedition
            ORDER BY id
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = "dxpedition"

    ws.append(COLUMNS)
    for row in rows:
        ws.append([row[col] for col in COLUMNS])

    # 見やすさのための簡単な列幅調整
    widths = {
        "A": 8,   # id
        "B": 14,  # callsign
        "C": 28,  # entity_name
        "D": 8,   # dxcc
        "E": 10,  # grid
        "F": 14,  # start_dt
        "G": 14,  # end_dt
        "H": 40,  # url
        "I": 40,  # notes
        "J": 22,  # created_at
        "K": 22,  # updated_at
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    print(f"exported: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
