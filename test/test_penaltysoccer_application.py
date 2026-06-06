import pytest
import pandas as pd

from penaltysoccer.betting.ev import analyze_binary_market, analyze_push_market
from penaltysoccer.data.fixtures import MatchFixture
from penaltysoccer.data.loaders import filter_before_cutoff
from penaltysoccer.data.markets import AsianHandicapMarket, MarketBook, TotalMarket, load_market_book_from_config
from penaltysoccer.prediction.batch import sort_reports
from penaltysoccer.prediction.report_schema import FixturePredictionReport, PredictionSummary
from penaltysoccer.reporting.markdown_report import render_reports_markdown
from penaltysoccer.reporting.terminal_report import best_value_bet, value_rule


def test_market_validation_rejects_invalid_odds():
    with pytest.raises(ValueError, match="greater than 1.0"):
        TotalMarket(line=2.5, over=1.0)

    with pytest.raises(ValueError, match="must include over or under"):
        TotalMarket(line=2.5)

    with pytest.raises(ValueError, match="side must be home or away"):
        AsianHandicapMarket(side="draw", line=0.5, odds=1.9)  # type: ignore[arg-type]


def test_market_book_parses_metadata_from_config():
    book = load_market_book_from_config(
        {
            "bookmaker": "sample-book",
            "captured_at": "2026-01-01T00:00:00+00:00",
            "1x2": {"home": 1.9, "draw": 3.4, "away": 4.2},
            "totals": [{"line": 2.5, "over": 1.91, "under": 1.95}],
            "asian_handicap": [{"side": "home", "line": -0.5, "odds": 1.85}],
        }
    )

    assert book.one_x_two is not None
    assert book.one_x_two.bookmaker == "sample-book"
    assert book.totals[0].captured_at == "2026-01-01T00:00:00+00:00"
    assert book.asian_handicaps[0].source == "config"


def test_push_market_uses_ev_kelly_rule_without_raw_edge_filter():
    analysis = analyze_push_market(
        market_type="asian_handicap",
        selection="home",
        line=-1.0,
        odds=1.92,
        win_probability=0.4386,
        push_probability=0.2472,
        min_ev=0.0,
        min_edge=0.0,
        kelly_fraction_multiplier=0.25,
        max_kelly=0.03,
    )

    assert analysis.edge < 0
    assert analysis.expected_value > 0
    assert analysis.suggested_kelly > 0
    assert analysis.edge_filter_applied is False
    assert analysis.is_value_bet is True
    assert value_rule(analysis.to_dict()) == "EV+Kelly"


def test_binary_market_still_applies_raw_edge_filter():
    analysis = analyze_binary_market(
        market_type="1x2",
        selection="home",
        odds=1.7,
        win_probability=0.5723,
        min_ev=-1.0,
        min_edge=0.0,
    )

    assert analysis.edge < 0
    assert analysis.edge_filter_applied is True
    assert analysis.is_value_bet is False
    assert value_rule(analysis.to_dict()) == "EV+Kelly+RawEdge"


def test_filter_before_cutoff_keeps_only_past_rows():
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
            "value": [1, 2, 3],
        }
    )

    filtered = filter_before_cutoff(df, "2025-01-03")

    assert filtered is not None
    assert filtered["value"].tolist() == [1, 2]


def _dummy_report(name: str, value_bets: int, best_ev: float, home_win: float = 0.5):
    betting = []
    for idx in range(value_bets):
        betting.append(
            {
                "market_type": "total",
                "selection": "over",
                "line": 2.5 + idx,
                "odds": 1.9,
                "win_probability": 0.55,
                "push_probability": 0.0,
                "lose_probability": 0.45,
                "edge": 0.02,
                "expected_value": best_ev - idx * 0.01,
                "suggested_kelly": 0.01,
                "is_value_bet": True,
                "source": "config",
                "bookmaker": "sample-book",
                "edge_filter_applied": True,
            }
        )
    if value_bets == 0:
        betting.append(
            {
                "market_type": "1x2",
                "selection": "home",
                "line": None,
                "odds": 1.8,
                "win_probability": 0.4,
                "push_probability": 0.0,
                "lose_probability": 0.6,
                "edge": -0.15,
                "expected_value": best_ev,
                "suggested_kelly": 0.0,
                "is_value_bet": False,
                "source": "config",
                "bookmaker": None,
                "edge_filter_applied": True,
            }
        )

    return FixturePredictionReport(
        fixture=MatchFixture(home=name, away="Away"),
        summary=PredictionSummary(
            home_win=home_win,
            draw=0.25,
            away_win=0.25,
            home_goal_expectation=1.5,
            away_goal_expectation=1.0,
            btts_yes=0.5,
            totals={"2.5": {"under": 0.45, "push": 0.0, "over": 0.55}},
            asian_handicaps={"-0.5": {"home": {"win": 0.5, "push": 0.0}, "away": {"win": 0.5}}},
        ),
        model_predictions={},
        market_book=MarketBook(),
        betting_analysis=betting,
        metadata={"models": ["poisson"], "training_match_count": 10},
    )


def test_batch_sorting_and_best_value_rendering():
    low = _dummy_report("Low", value_bets=1, best_ev=0.05)
    high = _dummy_report("High", value_bets=2, best_ev=0.03)

    reports = sort_reports([low, high], "value_bets")

    assert reports[0].fixture.home == "High"
    assert best_value_bet(high) == "total over 2.5"


def test_markdown_report_contains_raw_edge_and_rule():
    report = _dummy_report("Home", value_bets=1, best_ev=0.05)

    markdown = render_reports_markdown([report])

    assert "Raw Edge" in markdown
    assert "Rule" in markdown
    assert "EV+Kelly+RawEdge" in markdown
