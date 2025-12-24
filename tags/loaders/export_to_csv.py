"""
Export tags from database to CSV file.
"""
import argparse
from pathlib import Path

from .. import sync


def parse_args():
    p = argparse.ArgumentParser(description="Export tags from database to CSV")
    p.add_argument(
        "--db-path", dest="db_path",
        type=Path, required=True,
        help="The path to the database file",
    )
    p.add_argument(
        "--csv-file", dest="csv_file",
        type=Path, required=True,
        help="The CSV file to export to",
    )
    return p.parse_args()


def main():
    args = parse_args()
    sync.export_to_csv(args.db_path, args.csv_file)
    print(f"Exported tags to {args.csv_file}")


if __name__ == "__main__":
    main()

