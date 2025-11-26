import argparse
import pandas as pd
from pathlib import Path

from . import db, timelog_entry

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--db-path", dest="db_path", 
        type=Path, required=True,
        help="The path to the database file",
    )
    return p.parse_args()

def by_tag_analysis(df: pd.DataFrame) -> pd.DataFrame:

    all_tags = sorted(set[str](df['tags'].str.cat(sep=' ').split(' ')))

    def _total_time_by_tag(tag: str) -> int:
        return df[df['tags'].str.contains(tag)]['duration'].sum()
    
    df_by_tags = pd.DataFrame({'tag': all_tags})
    df_by_tags['total_duration'] = df_by_tags['tag'].apply(_total_time_by_tag)
    df_by_tags = df_by_tags.sort_values(by='total_duration', ascending=False)
    return df_by_tags

def main():
    args = parse_args()

    df = db.query_all_entries(args.db_path)
    df_by_tags = by_tag_analysis(df)
    print(df_by_tags.to_string(index=False))

if __name__ == "__main__":
    main()