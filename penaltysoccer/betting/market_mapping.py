"""Map prediction probabilities to market EV analysis."""

from __future__ import annotations

from typing import Any

from penaltysoccer.data.markets import MarketBook

from .ev import BetAnalysis, analyze_binary_market, analyze_push_market


def analyze_market_book(
    market_book: MarketBook,
    prediction: dict[str, Any],
    min_ev: float = 0.0,
    kelly_fraction_multiplier: float = 0.25,
    max_kelly: float | None = 0.03,
) -> list[BetAnalysis]:
    """Analyze all available market prices against an ensemble prediction."""

    analyses: list[BetAnalysis] = []

    if market_book.one_x_two:
        market = market_book.one_x_two
        h, d, a = prediction["home_draw_away"]
        analyses.extend(
            [
                analyze_binary_market("1x2", "home", market.home, h, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly),
                analyze_binary_market("1x2", "draw", market.draw, d, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly),
                analyze_binary_market("1x2", "away", market.away, a, market.source, market.captured_at, min_ev, kelly_fraction_multiplier, max_kelly),
            ]
        )

    for market in market_book.totals:
        probs = prediction["totals"].get(str(market.line))
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
                )
            )

    for market in market_book.asian_handicaps:
        probs = prediction["asian_handicaps_home_perspective"].get(str(market.line))
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
            )
        )

    return analyses
