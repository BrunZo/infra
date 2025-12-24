"""
Two-way sync between database and CSV files for tag management.
"""
from collections import defaultdict
import csv
from pathlib import Path
from typing import List, Dict, Set, Optional
from dataclasses import dataclass

from tags import db
from tags.tag import Tag
from tags.utils import tree


@dataclass
class SyncResult:
    """Results of a sync operation."""
    added: int = 0
    updated: int = 0
    deleted: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []


def export_to_csv(db_path: Path, csv_path: Path):
    """
    Export all tags from database to CSV file.
    
    Format: id, name, direct_ancestors
    - id: tag ID (integer)
    - name: tag name
    - direct_ancestors: space-separated ancestor names
    """
    with db.transaction(db_path, dry_run=False) as conn:
        tags = db.get_all_tags(conn)
        
        id_to_name = {tag.id: tag.name for tag in tags}
        
        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'name', 'direct_ancestors'])
            
            for tag in tags:
                ancestor_names = [id_to_name[aid] for aid in tag.direct_ancestors]
                ancestor_str = " ".join(ancestor_names) if ancestor_names else ""
                
                writer.writerow([tag.id, tag.name, ancestor_str])


def import_from_csv(
    db_path: Path,
    csv_path: Path,
    delete_missing: bool = False,
    dry_run: bool = False
) -> SyncResult:
    """
    Import tags from CSV file with two-way sync.
    
    Args:
        db_path: Path to the database
        csv_path: Path to the CSV file
        delete_missing: If True, delete tags from DB that are not in CSV
        dry_run: If True, don't actually modify the database, just report what would happen
    
    Returns:
        SyncResult with statistics about the sync operation
    """
    result = SyncResult()

    @dataclass
    class CsvTag:
        id: Optional[int]
        name: str
        ancestor_names: List[str]

    def _read_csv_tags(csv_path: Path) -> List[CsvTag]:
        """
        Read tags from CSV file.
        Returns list of CsvTag objects with ancestor names (not IDs yet).
        """
        def _parse_row(row: Dict[str, str]) -> CsvTag:
            tag_id_str = row.get('id', '').strip()
            tag_id = int(tag_id_str) if tag_id_str else None
            name = row.get('name', '').strip()
            ancestor_str = row.get('direct_ancestors', '').strip()
            ancestor_names = ancestor_str.split() if ancestor_str else []
            return CsvTag(id=tag_id, name=name, ancestor_names=ancestor_names)
        
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return [_parse_row(row) for row in reader]

    csv_tags = _read_csv_tags(csv_path)
    csv_ids = {tag.id for tag in csv_tags if tag.id is not None}
    csv_names = {tag.name for tag in csv_tags}
    name_to_index = {tag.name: index for index, tag in enumerate(csv_tags)}
    
    with db.transaction(db_path, dry_run=False) as read_conn:
        existing_tags = {tag.id: tag for tag in db.get_all_tags(read_conn)}
    name_to_id = {tag.name: tag.id for tag in existing_tags.values()}
    
    dependency_graph = defaultdict(list)

    for csv_tag in csv_tags:
        for ancestor_name in csv_tag.ancestor_names:
            if ancestor_name not in name_to_id:
                dependency_graph[csv_tag.name].append(ancestor_name)

    dependency_graph = dict(dependency_graph)
    
    visited: Set[int] = set()
    topological_order: List[int] = []

    def _dfs(tag_name: str):
        visited.add(tag_name)
        children = dependency_graph.get(tag_name, [])
        for child in children:
            if child not in visited:
                _dfs(child)
        topological_order.append(tag_name)
    
    for tag_name in csv_names:
        if tag_name not in visited:
            _dfs(tag_name)
    
    with db.transaction(db_path, dry_run=dry_run) as conn:
        for tag_name in topological_order:
            csv_tag = csv_tags[name_to_index[tag_name]]
            if csv_tag.id is None:
                result.added += 1
                ancestor_ids = [name_to_id[ancestor_name] for ancestor_name in csv_tag.ancestor_names]
                response = db.add_tag(conn, Tag(name=csv_tag.name, direct_ancestors=ancestor_ids))
                if isinstance(response, list):
                    result.errors.extend(response)
                else:
                    csv_tag.id = response
                    name_to_id[csv_tag.name] = response
            else:
                result.updated += 1
                ancestor_ids = [name_to_id[ancestor_name] for ancestor_name in csv_tag.ancestor_names]
                response = db.update_tag(conn, Tag(id=csv_tag.id, name=csv_tag.name, direct_ancestors=ancestor_ids))
                if isinstance(response, list):
                    result.errors.extend(response)

        if delete_missing:
            for tag_id in existing_tags.keys():
                if tag_id in csv_ids:
                    continue
                result.deleted += 1
                db.delete_tag(conn, tag_id)

        if dry_run:
            tree.show_tree(conn, 1)
    
    return result
