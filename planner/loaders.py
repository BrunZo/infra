"""
Inputs for the planner: the DAG (tags db or tags CSV) and the estimates CSV.

Estimates CSV, one row per tag, blanks mean default:

    name,weight,effort_hours,shape,spent_hours,deadline
    topology_final,,,,,2026-12-10
    topology_p1,2,40,linear,12,
    piano_repertoire,1,30,diminishing,,
"""
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable

from planner.dag import Children
from planner.model import Estimate


def children_from_tags_db(db_path: Path) -> Children:
    from tags import db
    with db.transaction(db_path, dry_run=True) as conn:
        tags = db.get_all_tags(conn)
    id_to_name = {t.id: t.name for t in tags}
    return _children((t.name, [id_to_name[a] for a in t.direct_ancestors]) for t in tags)


def children_from_tags_csv(csv_path: Path) -> Children:
    """Same format as tags/loaders/export_to_csv: id, name, direct_ancestors."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return _children((r["name"].strip(), r.get("direct_ancestors", "").split()) for r in rows)


def _children(pairs: Iterable) -> Children:
    children = defaultdict(list)
    for name, parents in pairs:
        children.setdefault(name, [])
        for parent in parents:
            children[parent].append(name)
    return dict(children)


def estimates_from_csv(csv_path: Path, known: Iterable[str]) -> Dict[str, Estimate]:
    known = set(known)
    estimates = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            row = {k: (v or "").strip() for k, v in row.items()}
            name = row["name"]
            if name not in known:
                raise ValueError(f"Estimate for unknown tag '{name}'")
            estimates[name] = Estimate(
                name=name,
                weight=float(row["weight"]) if row.get("weight") else 1.0,
                effort_hours=float(row["effort_hours"]) if row.get("effort_hours") else None,
                shape=row.get("shape") or "linear",
                spent_hours=float(row["spent_hours"]) if row.get("spent_hours") else 0.0,
                deadline=date.fromisoformat(row["deadline"]) if row.get("deadline") else None,
            )
    return estimates
