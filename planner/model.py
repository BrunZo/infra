from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional


@dataclass
class Estimate:
    """
    What the planner needs to know about a tag, beyond the DAG itself.

    - weight: importance relative to siblings. A child's share of its parent
      is weight / sum of sibling weights (the `share` in prioritization).
    - halving_hours, shape: the return curve, see curves.py. Leaves only.
    - spent_hours: already invested; the curve continues from there, so a
      well-fed leaf is worth less per hour than a neglected one.
    """
    name: str
    weight: float = 1.0
    halving_hours: Optional[float] = None
    shape: str = "log"
    spent_hours: float = 0.0


@dataclass
class Leaf:
    name: str
    coefficient: float          # share of the target this leaf is worth
    shape: str
    halving_hours: float
    spent_hours: float


@dataclass
class Allocation:
    name: str
    hours: float
    coefficient: float
    gain: float                 # target return from the new hours, in fresh hours
    next_hour: float            # target return of one more hour after the plan


@dataclass
class Plan:
    target: str
    horizon: date
    capacity_hours: float
    allocations: List[Allocation]
    schedule: Dict[date, List[tuple]]      # day -> [(leaf, hours)]
    marginal_return: float                 # target return of the last hour bought
    unestimated: List[str] = field(default_factory=list)

    @property
    def planned_hours(self) -> float:
        return sum(a.hours for a in self.allocations)

    @property
    def gain(self) -> float:
        return sum(a.gain for a in self.allocations)
