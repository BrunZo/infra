"""
Allocate time slots to leaves to maximize the target's return.

    maximize    sum_i coefficient_i * return_i(spent_i + hours_i)
    subject to  sum_i hours_i <= capacity

Every curve is concave, so giving each slot to the leaf whose next slot is
worth most is exact. At the optimum every leaf that got time has roughly
the same marginal return: no hour could be moved and pay more elsewhere.
"""
import heapq
from typing import Dict, List, Tuple

from planner.curves import make_curve
from planner.model import Leaf


def gain_function(leaf: Leaf, slot_hours: float):
    """gain(k) = target return from giving the leaf k slots on top of what it has."""
    curve = make_curve(leaf.shape, leaf.halving_hours)
    base = curve(leaf.spent_hours)
    return lambda k: leaf.coefficient * (curve(leaf.spent_hours + k * slot_hours) - base)


def greedy(leaves: List[Leaf], total_slots: int, slot_hours: float) -> Tuple[Dict[str, int], float]:
    """Returns (slots per leaf, return per hour of the last slot bought)."""
    slots = {leaf.name: 0 for leaf in leaves}
    gains = {leaf.name: gain_function(leaf, slot_hours) for leaf in leaves}

    def marginal(name: str) -> float:
        k = slots[name]
        return gains[name](k + 1) - gains[name](k)

    heap = [(-marginal(leaf.name), leaf.name) for leaf in leaves if leaf.coefficient > 0]
    heapq.heapify(heap)
    last = 0.0
    for _ in range(total_slots):
        if not heap:
            break
        neg, name = heapq.heappop(heap)
        slots[name] += 1
        last = -neg
        heapq.heappush(heap, (-marginal(name), name))
    return slots, last / slot_hours
