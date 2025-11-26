import argparse
import csv
import datetime
from pathlib import Path

from .. import db, timelog_entry

def parse_args():
    p = argparse.ArgumentParser()

    p.add_argument(
        "--db-path", dest="db_path", 
        type=Path, required=True,
        help="The path to the database file",
    )

    p.add_argument(
        "--csv-file", dest="csv_file",
        type=Path, required=True,
        help="The CSV file to load"
    )
    
    return p.parse_args()

def main():
    args = parse_args()
    
    csv_reader = csv.reader(args.csv_file.open())
    added_entries = 0
    for row in csv_reader:
        start = datetime.datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
        duration = datetime.timedelta(seconds=int(row[1]))
        tags = row[2].split(" ")
        description = row[3]
        entry = timelog_entry.TimeLogEntry(start=start, duration=duration, tags=tags, description=description)
        db.add_entry(args.db_path, entry)
        added_entries += 1

    print(f"Loaded {added_entries} entries")

if __name__ == "__main__":
    main()