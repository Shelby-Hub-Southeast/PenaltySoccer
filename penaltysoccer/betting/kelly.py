"""Kelly staking helpers."""

from __future__ import annotations


def kelly_fraction(win_probability: float, odds: float, lose_probability: float | None = None) -> float:
    """Return full Kelly fraction for decimal odds.

    ``lose_probability`` is optional so markets with a push probability can pass
    ``1 - win - push``. Negative Kelly values are clipped to zero because the
    application layer reports actionable positive sizing only.
    """

    b = odds - 1.0
    if b <= 0:
        return 0.0
    p = float(win_probability)
    q = float(1.0 - p if lose_probability is None else lose_probability)
    value = (b * p - q) / b
    return max(0.0, value)


def fractional_kelly(full_kelly: float, fraction: float = 0.25, max_fraction: float | None = None) -> float:
    """Apply fractional Kelly and an optional cap."""

    stake = max(0.0, float(full_kelly) * float(fraction))
    if max_fraction is not None:
        stake = min(stake, float(max_fraction))
    return stake
