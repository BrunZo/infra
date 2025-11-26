import datetime
import sqlite3
from pathlib import Path

from .timelog_entry import TimeLogEntry

def get_db(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path: Path):
    conn = get_db(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS time_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start DATETIME NOT NULL,
            duration_seconds INTEGER NOT NULL,
            tags TEXT NOT NULL,
            description TEXT NOT NULL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def row_to_entry(row) -> TimeLogEntry:
    return TimeLogEntry(
        id=row["id"],
        start=row["start"],
        duration=datetime.timedelta(seconds=row["duration_seconds"]),
        tags=row["tags"].split(","),
        description=row["description"],
        last_updated=row["last_updated"]
    )

def add_entry(db_path: Path, entry: TimeLogEntry): 
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO time_logs (start, duration_seconds, tags, description) VALUES (?, ?, ?, ?)",
        (entry.start, entry.duration.total_seconds(), ",".join(entry.tags), entry.description)
    )
    conn.commit()
    conn.close()

def query_all_entries(db_path: Path):
    conn = get_db(db_path)
    cursor = conn.execute("SELECT * FROM time_logs")
    results = [row_to_entry(row) for row in cursor.fetchall()]
    conn.close()
    return results

