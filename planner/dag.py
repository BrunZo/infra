"""
Reduce a tag DAG under a target to a flat list of weighted leaves.

The target's return is a weighted sum of its children's, recursively:

    return(n) = sum over children c of  w(c) / W(n) * return(c)

where W(n) is the sum of the weights of n's children. Unrolled, the target's
return is linear in the leaves' returns, with coefficient

    coefficient(leaf) = sum over paths target -> leaf of the product of shares

A leaf reached by two paths counts twice: serving two ends is worth more.
"""
from collections import defaultdict
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


def flatten(children: Children, target: str, estimates: Dict[str, Estimate]) -> Tuple[List[Leaf], List[str]]:
    """
    Returns (leaves, unestimated). Unestimated leaves have no curve, so they
    get no time, but they keep their share: the return they stand for is
    real, just not plannable yet.
    """
    nodes = descendants(children, target)
    order = topological_order(children, nodes, target)

    coefficient = defaultdict(float)
    coefficient[target] = 1.0
    for n in order:
        kids = children.get(n, [])
        total = sum(_weight(estimates, c) for c in kids)
        for c in kids:
            if total == 0:
                break
            coefficient[c] += coefficient[n] * _weight(estimates, c) / total

    leaves, unestimated = [], []
    for n in order:
        if children.get(n):
            continue
        e = estimates.get(n)
        if e is None or e.halving_hours is None:
            unestimated.append(n)
            continue
        leaves.append(Leaf(
            name=n,
            coefficient=coefficient[n],
            shape=e.shape,
            halving_hours=e.halving_hours,
            spent_hours=e.spent_hours,
        ))
    return leaves, unestimated


def _weight(estimates: Dict[str, Estimate], name: str) -> float:
    e = estimates.get(name)
    return e.weight if e else 1.0
