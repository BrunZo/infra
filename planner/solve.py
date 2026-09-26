"""
Allocate time slots to leaves to maximize the target's progress.

    maximize    sum_i coefficient_i * progress_i(spent_i + hours_i)
    subject to  for every deadline d:  sum of hours of leaves due by d  <=  capacity before d

Time is discrete (slots). The deadline constraints are nested, so the
feasible set is a polymatroid and, when every curve is concave, taking the
best marginal slot until nothing helps is exact. Otherwise (step curves) a
knapsack DP over leaves sorted by deadline is exact on the slot grid.
"""
import bisect
import heapq
import math
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Tuple

from planner.curves import CONCAVE_SHAPES, make_curve, saturation_hours
from planner.model import Leaf


@dataclass
class Capacity:
    slots: Dict[date, int]      # day -> slots available that day
    slot_hours: float

    def before(self, d: date) -> int:
        return sum(n for day, n in self.slots.items() if day < d)

    @property
    def total(self) -> int:
        return sum(self.slots.values())


def solve(leaves: List[Leaf], capacity: Capacity) -> Tuple[Dict[str, int], float, str]:
    """Returns (slots per leaf, marginal return per hour of the last slot, solver name)."""
    if all(leaf.shape in CONCAVE_SHAPES for leaf in leaves):
        slots, marginal = greedy(leaves, capacity)
        return slots, marginal, "greedy"
    return dp(leaves, capacity), math.nan, "dp"


def _gain(leaf: Leaf, capacity: Capacity):
    """gain(k) = target progress from giving the leaf k slots on top of what it has."""
    curve = make_curve(leaf.shape, leaf.effort_hours)
    base = curve(leaf.spent_hours)
    return lambda k: leaf.coefficient * (curve(leaf.spent_hours + k * capacity.slot_hours) - base)


def _max_useful_slots(leaf: Leaf, capacity: Capacity) -> int:
    left = saturation_hours(leaf.shape, leaf.effort_hours) - leaf.spent_hours
    if left <= 0:
        return 0
    if math.isinf(left):
        return capacity.before(leaf.deadline)
    return min(capacity.before(leaf.deadline), math.ceil(left / capacity.slot_hours - 1e-9))


def greedy(leaves: List[Leaf], capacity: Capacity) -> Tuple[Dict[str, int], float]:
    deadlines = sorted({leaf.deadline for leaf in leaves})
    limit = [capacity.before(d) for d in deadlines]
    used = [0] * len(deadlines)             # slots given to leaves due exactly at deadlines[j]

    def fits(j: int) -> bool:
        prefix = sum(used[:j])
        for k in range(j, len(deadlines)):
            prefix += used[k]
            if prefix + 1 > limit[k]:
                return False
        return True

    slots = {leaf.name: 0 for leaf in leaves}
    gains = {leaf.name: _gain(leaf, capacity) for leaf in leaves}
    cap = {leaf.name: _max_useful_slots(leaf, capacity) for leaf in leaves}
    index = {leaf.name: bisect.bisect_left(deadlines, leaf.deadline) for leaf in leaves}

    def marginal(name: str) -> float:
        k = slots[name]
        return gains[name](k + 1) - gains[name](k)

    heap = [(-marginal(leaf.name), leaf.name) for leaf in leaves if cap[leaf.name] > 0]
    heapq.heapify(heap)
    last = 0.0
    while heap:
        neg, name = heapq.heappop(heap)
        if -neg <= 1e-12:
            break
        j = index[name]
        if not fits(j):
            continue                        # usage only grows: blocked for good
        slots[name] += 1
        used[j] += 1
        last = -neg
        if slots[name] < cap[name]:
            heapq.heappush(heap, (-marginal(name), name))
    return slots, last / capacity.slot_hours


def dp(leaves: List[Leaf], capacity: Capacity) -> Dict[str, int]:
    order = sorted(leaves, key=lambda leaf: leaf.deadline)
    total = capacity.total
    NEG = -math.inf
    best = [0.0] + [NEG] * total           # best[u] = max progress using exactly u slots
    choices = []
    for leaf in order:
        gain = _gain(leaf, capacity)
        values = [gain(k) for k in range(_max_useful_slots(leaf, capacity) + 1)]
        nxt = [NEG] * (total + 1)
        choice = [0] * (total + 1)
        for u, base in enumerate(best):
            if base == NEG:
                continue
            for k, v in enumerate(values):
                if u + k > total:
                    break
                if base + v > nxt[u + k] + 1e-12:
                    nxt[u + k] = base + v
                    choice[u + k] = k
        for u in range(capacity.before(leaf.deadline) + 1, total + 1):
            nxt[u] = NEG
        best = nxt
        choices.append(choice)

    top = max(best)
    u = min(i for i, v in enumerate(best) if v >= top - 1e-12)     # least time for the best value
    slots = {}
    for leaf, choice in zip(reversed(order), reversed(choices)):
        slots[leaf.name] = choice[u]
        u -= choice[u]
    return slots
