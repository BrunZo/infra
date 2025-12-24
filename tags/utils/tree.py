from typing import List
from pathlib import Path
from .. import tag, db

def show_tree(db_path: Path, start_tag_id: int):

    visited_edges = set[int]()
    depth = 0

    def dfs(tag_id: int):
        nonlocal depth
        tag = db.get_tag_by_id(db_path, tag_id)
        print(f"{'  ' * depth}{tag.name}")

        descendants_ids = db.get_direct_descendants_ids(db_path, tag_id)
        for descendant_id in descendants_ids:
            if (tag_id, descendant_id) in visited_edges:
                continue
            visited_edges.add((tag_id, descendant_id))
            tag = db.get_tag_by_id(db_path, tag_id)
            depth += 1
            dfs(descendant_id)
            depth -= 1

    dfs(start_tag_id)