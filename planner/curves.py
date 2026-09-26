"""
Return curves: the value produced by the hours invested in a leaf.

Nothing is ever finished. Every leaf can take more time and keeps paying,
just less each hour. Both shapes share one parameter, `halving` (hours):

| shape      | return(t)                        | the marginal hour is worth       |
|------------|----------------------------------|----------------------------------|
| log        | H * ln(1 + t/H)                  | 1/2 at t=H, 1/3 at 2H... never 0 |
| saturating | H / ln 2 * (1 - 2^(-t/H))        | halves every H hours             |

Both are scaled so the first hour is worth 1: return is measured in
"fresh hours". `log` is the default: open-ended practice (piano, math)
keeps paying. `saturating` is for things with a real ceiling.
"""
import math
from typing import Callable, Dict

Curve = Callable[[float], float]


def log(halving: float) -> Curve:
    return lambda t: halving * math.log1p(t / halving)


def saturating(halving: float) -> Curve:
    return lambda t: halving / math.log(2) * (1.0 - math.pow(2.0, -t / halving))


SHAPES: Dict[str, Callable[[float], Curve]] = {
    "log": log,
    "saturating": saturating,
}


def make_curve(shape: str, halving: float) -> Curve:
    if shape not in SHAPES:
        raise ValueError(f"Unknown shape '{shape}', expected one of {sorted(SHAPES)}")
    if halving <= 0:
        raise ValueError(f"halving must be positive, got {halving}")
    return SHAPES[shape](halving)
