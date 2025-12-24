from pathlib import Path
from typing import Deque, List, Set
from collections import deque

from tags.tag import Tag
from tags import db


def check_ancestors_exist(db_path: Path, tag: Tag) -> List[str]:
    """
    Check that all ancestor IDs exist in the database.
    Returns list of error messages (empty if valid).
    """
    errors = []
    for ancestor_id in tag.direct_ancestors:
        if not db.tag_exists(db_path, ancestor_id):
            errors.append(f"Ancestor tag with ID {ancestor_id} not found")
    return errors


def check_self_reference(db_path: Path, tag: Tag) -> List[str]:
    """
    Check that a tag doesn't reference itself as an ancestor.
    Returns list of error messages (empty if valid).
    """
    errors = []
    if tag.id is not None and tag.id in tag.direct_ancestors:
        errors.append(f"Tag '{tag.name}' (ID: {tag.id}) cannot be its own ancestor")
    return errors


def check_cycles(db_path: Path, tag: Tag) -> List[str]:
    """
    Check if adding this tag would create a cycle in the tag hierarchy.
    Uses BFS to check if any ancestor is a descendant of this tag.
    Returns list of error messages (empty if valid).
    """
    errors = []
    
    descendants: Set[int] = set()
    queue: Deque[int] = deque([tag.id])
    
    while queue:
        current_id = queue.popleft()
        if current_id in descendants:
            continue
        descendants.add(current_id)
        
        for child_id in db.get_direct_descendants_ids(db_path, current_id):
            if child_id not in descendants:
                queue.append(child_id)
    
    for ancestor in tag.direct_ancestors:
        if ancestor in descendants:
            errors.append(f"Cycle detected: Tag '{tag.name}' (ID: {tag.id}) cannot have be a child of {ancestor}"
                           f" since {ancestor} is a descendant of {tag.name}.")
            continue

    return errors


def validate_tag(db_path: Path, tag: Tag) -> List[str]:

    checks = [check_ancestors_exist, check_self_reference, check_cycles]

    errors = []
    for check in checks:
        errors.extend(check(db_path, tag))
    return errors

