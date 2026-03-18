#!/usr/bin/env python3
"""Export dxpedition table from SQLite to an Excel file."""

import sqlite3
from pathlib import Path

from openpyxl import Workbook

DB_PATH = Path("data") / "spots.db"
OUTPUT_PATH = Path("data") / "DX_export.xlsx"

COLUMNS = [
    "callsign",
    "entity_name",
    "dxcc",
    "grid",
    "start_dt",
    "end_dt",
    "url",
    "notes",
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
            ORDER BY callsign
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
        "A": 14,  # callsign
        "B": 28,  # entity_name
        "C": 8,   # dxcc
        "D": 10,  # grid
        "E": 14,  # start_dt
        "F": 14,  # end_dt
        "G": 40,  # url
        "H": 40,  # notes
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_PATH)
    print(f"exported: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
