"""Serializable prediction report schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from penaltysoccer.data.fixtures import MatchFixture
from penaltysoccer.data.markets import MarketBook


@dataclass
class PredictionSummary:
    home_win: float
    draw: float
    away_win: float
    home_goal_expectation: float
    away_goal_expectation: float
    btts_yes: float
    totals: dict[str, dict[str, float]]
    asian_handicaps: dict[str, dict[str, Any]]
    top_exact_scores: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PredictionContext:
    understat_recent_xg: dict[str, Any] = field(default_factory=dict)
    clubelo: dict[str, Any] = field(default_factory=dict)


@dataclass
class FixturePredictionReport:
    fixture: MatchFixture
    summary: PredictionSummary
    model_predictions: dict[str, dict[str, Any]]
    market_book: MarketBook
    betting_analysis: list[dict[str, Any]] = field(default_factory=list)
    context: PredictionContext = field(default_factory=PredictionContext)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
