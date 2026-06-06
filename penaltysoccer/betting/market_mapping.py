"""Map prediction probabilities to market EV analysis."""

from __future__ import annotations

from typing import Any

from penaltysoccer.data.markets import MarketBook

from .ev import BetAnalysis, analyze_binary_market, analyze_push_market


def _line_key(line: float) -> str:
    """Return the key format used by prediction dictionaries."""

    return str(float(line))


def analyze_market_book(
    market_book: MarketBook,
    prediction: dict[str, Any],
    min_ev: float = 0.0,
    kelly_fraction_multiplier: float = 0.25,
    max_kelly: float | None = 0.03,
    min_edge: float = 0.0,
) -> list[BetAnalysis]:
    """Analyze all available market prices against an ensemble prediction.

    Asian handicap predictions are stored from the home-line perspective. For an
    away-side market, the equivalent home line is ``-away_line``.
    """

    analyses: list[BetAnalysis] = []

    if market_book.one_x_two:
        market = market_book.one_x_two
        h, d, a = prediction["home_draw_away"]
        analyses.extend(
            [
                analyze_binary_market("1x2", "home", market.home, h, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly, min_edge, market.bookmaker),
                analyze_binary_market("1x2", "draw", market.draw, d, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly, min_edge, market.bookmaker),
                analyze_binary_market("1x2", "away", market.away, a, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly, min_edge, market.bookmaker),
            ]
        )

    for market in market_book.totals:
        probs = prediction["totals"].get(_line_key(market.line))
        if not probs:
            continue
        if market.over:
            analyses.append(
                analyze_push_market(
                    "total",
                    "over",
                    market.line,
                    market.over,
                    probs["over"],
                    probs["push"],
                    market.source,
                    market.captured_at,
                    min_ev,
                    kelly_fraction_multiplier,
                    max_kelly,
                    min_edge,
                    market.bookmaker,
                )
            )
        if market.under:
            analyses.append(
                analyze_push_market(
                    "total",
                    "under",
                    market.line,
                    market.under,
                    probs["under"],
                    probs["push"],
                    market.source,
                    market.captured_at,
                    min_ev,
                    kelly_fraction_multiplier,
                    max_kelly,
                    min_edge,
                    market.bookmaker,
                )
            )

    for market in market_book.asian_handicaps:
        home_line = market.line if market.side == "home" else -market.line
        probs = prediction["asian_handicaps_home_perspective"].get(_line_key(home_line))
        if not probs:
            continue
        side_probs = probs[market.side]
        analyses.append(
            analyze_push_market(
                "asian_handicap",
                market.side,
                market.line,
                market.odds,
                side_probs["win"],
                side_probs["push"],
                market.source,
                market.captured_at,
                min_ev,
                kelly_fraction_multiplier,
                max_kelly,
                min_edge,
                market.bookmaker,
            )
        )

    return analyses
