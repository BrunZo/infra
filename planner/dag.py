"""
Reduce a tag DAG under a target to a flat list of weighted leaves.

The target's progress is a weighted sum of its children's, recursively:

    progress(n) = sum over children c of  w(c) / W(n) * progress(c)

where W(n) is the sum of the weights of n's children. Unrolled, that makes
the target's progress linear in the leaves' progress, with coefficient

    coefficient(leaf) = sum over paths target -> leaf of the product of shares

A leaf reached by two paths counts twice: serving two ends is worth more.
"""
from collections import defaultdict
from datetime import date
from typing import Dict, List, Set, Tuple

from planner.model import Estimate, Leaf

Children = Dict[str, List[str]]


def descendants(children: Children, target: str) -> Set[str]:
    seen = {target}
    stack = [target]
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in seen:
                seen.add(child)
                stack.append(child)
    return seen


def topological_order(children: Children, nodes: Set[str], target: str) -> List[str]:
    """Nodes under target, each one after all of its parents."""
    in_degree = {n: 0 for n in nodes}
    for n in nodes:
        for c in children.get(n, []):
            in_degree[c] += 1
    order, ready = [], [target]
    while ready:
        n = ready.pop()
        order.append(n)
        for c in children.get(n, []):
            in_degree[c] -= 1
            if in_degree[c] == 0:
                ready.append(c)
    if len(order) != len(nodes):
        raise ValueError(f"Cycle below '{target}'")
    return order


def flatten(
    children: Children,
    target: str,
    estimates: Dict[str, Estimate],
    horizon: date,
) -> Tuple[List[Leaf], List[str]]:
    """
    Returns (leaves, unestimated). Unestimated leaves have no effort, so
    they get no time, but they keep their share: the progress they stand
    for is real, just not plannable yet.
    """
    nodes = descendants(children, target)
    order = topological_order(children, nodes, target)

    coefficient = defaultdict(float)
    coefficient[target] = 1.0
    deadline = {n: horizon for n in nodes}

    def own_deadline(n: str) -> date:
        e = estimates.get(n)
        return min(horizon, e.deadline) if e and e.deadline else horizon

    deadline[target] = own_deadline(target)
    for n in order:
        kids = children.get(n, [])
        total = sum(_weight(estimates, c) for c in kids)
        for c in kids:
            if total == 0:
                break
            coefficient[c] += coefficient[n] * _weight(estimates, c) / total
            # Conservative: a leaf under two deadlines is planned against the earlier.
            deadline[c] = min(deadline[c], deadline[n], own_deadline(c))

    leaves, unestimated = [], []
    for n in order:
        if children.get(n):
            continue
        e = estimates.get(n)
        if e is None or e.effort_hours is None:
            unestimated.append(n)
            continue
        leaves.append(Leaf(
            name=n,
            coefficient=coefficient[n],
            deadline=deadline[n],
            shape=e.shape,
            effort_hours=e.effort_hours,
            spent_hours=e.spent_hours,
        ))
    return leaves, unestimated


def _weight(estimates: Dict[str, Estimate], name: str) -> float:
    e = estimates.get(name)
    return e.weight if e else 1.0
