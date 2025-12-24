import argparse
import csv
from pathlib import Path

from .. import db, tag

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
    added_tags = 0

    for row in csv_reader:
        name = row[0]
        direct_ancestors = []

        if row[1] != "":
            for token in row[1].split(" "):      
                if (ancestor := db.get_tag_by_name(args.db_path, token)) is None:
                    print(f"Ancestor tag {token} not found")
                    continue
                direct_ancestors.append(ancestor.id)
                
        if db.get_tag_by_name(args.db_path, name):
            print(f"Tag {name} already exists")
            continue
        
        db.add_tag(args.db_path, tag.Tag(name=name, direct_ancestors=direct_ancestors))
        added_tags += 1

    print(f"Loaded {added_tags} tags")

if __name__ == "__main__":
    main()