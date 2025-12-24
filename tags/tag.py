from dataclasses import dataclass
from typing import List

@dataclass
class Tag:
    name: str
    direct_ancestors: List[int]
    id: int = None

@dataclass
class TagRelationship:
    parent_tag_id: int
    child_tag_id: int
    path_length: int
    id: int = None