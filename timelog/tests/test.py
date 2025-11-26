import argparse
from datetime import datetime, timedelta
from pathlib import Path

from .. import db, timelog_entry

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db-path", dest="db_path", 
        type=Path, required=True,
        help="The path to the database file",
    )
    return p.parse_args()

def test_add_entry(db_path: Path):
    entry = timelog_entry.TimeLogEntry(
        start=datetime.now(), 
        duration=timedelta(hours=1), 
        tags=["work", "programming"], 
        description="Worked on project"
    )
    db.add_entry(db_path, entry)

def test_query_all_entries(db_path: Path):
    entries = db.query_all_entries(db_path)
    print(entries)

def all_tests():
    args = parse_args()
    db.init_db(args.db_path)
    test_add_entry(args.db_path)
    test_query_all_entries(args.db_path)

if __name__ == "__main__":
    all_tests()