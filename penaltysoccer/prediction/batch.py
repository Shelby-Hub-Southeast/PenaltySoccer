"""Batch prediction from configuration dictionaries."""

from __future__ import annotations

from typing import Any

from penaltysoccer.data.fixtures import MatchFixture
from penaltysoccer.data.markets import load_market_book_from_config
from penaltysoccer.models.persistence import ModelBundle

from .report_schema import FixturePredictionReport
from .single import DEFAULT_HOME_HANDICAPS, DEFAULT_TOTAL_LINES, predict_fixture


def best_ev(report: FixturePredictionReport) -> float:
    """Return the highest EV in a report, or negative infinity if none exist."""

    values = [float(item["expected_value"]) for item in report.betting_analysis]
    return max(values) if values else float("-inf")


def value_bet_count(report: FixturePredictionReport) -> int:
    """Return number of value bets in a report."""

    return sum(1 for item in report.betting_analysis if item["is_value_bet"])


def sort_reports(reports: list[FixturePredictionReport], sort_by: str = "value_bets") -> list[FixturePredictionReport]:
    """Sort reports for batch display."""

    if sort_by == "best_ev":
        return sorted(reports, key=best_ev, reverse=True)
    if sort_by == "home_win":
        return sorted(reports, key=lambda report: report.summary.home_win, reverse=True)
    if sort_by == "away_win":
        return sorted(reports, key=lambda report: report.summary.away_win, reverse=True)
    if sort_by == "value_bets":
        return sorted(reports, key=lambda report: (value_bet_count(report), best_ev(report)), reverse=True)
    if sort_by == "input":
        return reports
    raise ValueError("sort_by must be one of: input, value_bets, best_ev, home_win, away_win")


def predict_batch_from_config(bundle: ModelBundle, config: dict[str, Any]) -> list[FixturePredictionReport]:
    """Predict all fixtures in a prediction config dictionary."""

    source = config.get("market_source", "config")
    total_lines = [float(x) for x in config.get("totals", DEFAULT_TOTAL_LINES)]
    home_handicaps = [float(x) for x in config.get("handicaps", DEFAULT_HOME_HANDICAPS)]
    top_scores = int(config.get("top_scores", 8))
    recent = int(config.get("recent", 6))
    min_ev = float(config.get("min_ev", 0.0))
    min_edge = float(config.get("min_edge", 0.0))
    kelly_fraction = float(config.get("kelly_fraction", 0.25))
    max_kelly = config.get("max_kelly", 0.03)
    max_kelly = None if max_kelly is None else float(max_kelly)
    sort_by = str(config.get("sort_by", "value_bets"))

    reports: list[FixturePredictionReport] = []
    for raw_fixture in config.get("fixtures", []):
        fixture = MatchFixture.from_mapping(raw_fixture)
        market_book = load_market_book_from_config(raw_fixture.get("markets"), source=source)
        reports.append(
            predict_fixture(
                bundle=bundle,
                fixture=fixture,
                market_book=market_book,
                total_lines=total_lines,
                home_handicaps=home_handicaps,
                top_scores=top_scores,
                recent=recent,
                min_ev=min_ev,
                kelly_fraction_multiplier=kelly_fraction,
                max_kelly=max_kelly,
                min_edge=min_edge,
            )
        )
    return sort_reports(reports, sort_by)
