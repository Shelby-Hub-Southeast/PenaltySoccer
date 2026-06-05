"""Expected value helpers for betting markets."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .kelly import fractional_kelly, kelly_fraction


@dataclass(frozen=True)
class BetAnalysis:
    market_type: str
    selection: str
    line: float | None
    odds: float
    win_probability: float
    push_probability: float
    lose_probability: float
    implied_probability: float
    edge: float
    expected_value: float
    full_kelly: float
    suggested_kelly: float
    is_value_bet: bool
    source: str = "config"
    captured_at: str | None = None

    def to_dict(self) -> dict[str, float | str | bool | None]:
        return asdict(self)


def analyze_push_market(
    market_type: str,
    selection: str,
    line: float | None,
    odds: float,
    win_probability: float,
    push_probability: float = 0.0,
    source: str = "config",
    captured_at: str | None = None,
    min_ev: float = 0.0,
    kelly_fraction_multiplier: float = 0.25,
    max_kelly: float | None = 0.03,
) -> BetAnalysis:
    """Analyze a market that may include a push settlement."""

    p_win = float(win_probability)
    p_push = float(push_probability)
    p_lose = max(0.0, 1.0 - p_win - p_push)
    decimal_odds = float(odds)
    implied = 1.0 / decimal_odds
    edge = p_win - implied
    ev = p_win * (decimal_odds - 1.0) - p_lose
    full_kelly = kelly_fraction(p_win, decimal_odds, p_lose)
    suggested = fractional_kelly(full_kelly, kelly_fraction_multiplier, max_kelly)
    return BetAnalysis(
        market_type=market_type,
        selection=selection,
        line=line,
        odds=decimal_odds,
        win_probability=p_win,
        push_probability=p_push,
        lose_probability=p_lose,
        implied_probability=implied,
        edge=edge,
        expected_value=ev,
        full_kelly=full_kelly,
        suggested_kelly=suggested,
        is_value_bet=ev > min_ev and suggested > 0,
        source=source,
        captured_at=captured_at,
    )


def analyze_binary_market(
    market_type: str,
    selection: str,
    odds: float,
    win_probability: float,
    source: str = "config",
    captured_at: str | None = None,
    min_ev: float = 0.0,
    kelly_fraction_multiplier: float = 0.25,
    max_kelly: float | None = 0.03,
) -> BetAnalysis:
    """Analyze a binary win/lose market with no push."""

    return analyze_push_market(
        market_type=market_type,
        selection=selection,
        line=None,
        odds=odds,
        win_probability=win_probability,
        push_probability=0.0,
        source=source,
        captured_at=captured_at,
        min_ev=min_ev,
        kelly_fraction_multiplier=kelly_fraction_multiplier,
        max_kelly=max_kelly,
    )
