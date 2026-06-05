"""Single-fixture prediction workflow."""

from __future__ import annotations

from difflib import get_close_matches
from typing import Any

import numpy as np
import pandas as pd

from penaltysoccer.betting.market_mapping import analyze_market_book
from penaltysoccer.data.fixtures import MatchFixture
from penaltysoccer.data.markets import MarketBook
from penaltysoccer.data.team_names import assert_team_known, list_known_teams
from penaltysoccer.models.ensemble import average_prediction_dicts
from penaltysoccer.models.persistence import ModelBundle

from .report_schema import FixturePredictionReport, PredictionContext, PredictionSummary

DEFAULT_TOTAL_LINES = [2.0, 2.25, 2.5, 2.75, 3.0, 3.25]
DEFAULT_HOME_HANDICAPS = [-1.5, -1.25, -1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]


def top_exact_scores(pred: Any, limit: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grid = pred.grid
    for home_goals in range(grid.shape[0]):
        for away_goals in range(grid.shape[1]):
            rows.append({"score": f"{home_goals}-{away_goals}", "probability": float(grid[home_goals, away_goals])})
    rows.sort(key=lambda item: item["probability"], reverse=True)
    return rows[:limit]


def prediction_from_grid(
    pred: Any,
    total_lines: list[float],
    home_handicaps: list[float],
    top_scores: int = 8,
) -> dict[str, Any]:
    totals = {}
    for line in total_lines:
        under, push, over = pred.totals(line)
        totals[str(line)] = {"under": under, "push": push, "over": over}

    handicaps = {}
    for line in home_handicaps:
        home_probs = pred.asian_handicap_probs("home", line)
        away_probs = pred.asian_handicap_probs("away", -line)
        handicaps[str(line)] = {
            "home_line": line,
            "home": home_probs,
            "away_equivalent_line": -line,
            "away": away_probs,
        }

    return {
        "home_win": pred.home_win,
        "draw": pred.draw,
        "away_win": pred.away_win,
        "home_draw_away": pred.home_draw_away,
        "home_goal_expectation": pred.home_goal_expectation,
        "away_goal_expectation": pred.away_goal_expectation,
        "btts_yes": pred.btts_yes,
        "btts_no": pred.btts_no,
        "double_chance_1x": pred.double_chance_1x,
        "double_chance_x2": pred.double_chance_x2,
        "double_chance_12": pred.double_chance_12,
        "draw_no_bet_home": pred.draw_no_bet_home,
        "draw_no_bet_away": pred.draw_no_bet_away,
        "totals": totals,
        "asian_handicaps_home_perspective": handicaps,
        "top_exact_scores": top_exact_scores(pred, top_scores),
    }


def safe_nanmean(values: list[float]) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return None
    return float(np.nanmean(arr))


def recent_xg_context(df: pd.DataFrame | None, fixture: MatchFixture, recent: int = 6) -> dict[str, Any]:
    if df is None or df.empty:
        return {"available": False}

    context: dict[str, Any] = {"available": True, "recent_matches": recent, "teams": {}}
    known_teams = list_known_teams(df)
    for team in [fixture.home, fixture.away]:
        team_rows = df[(df["team_home"] == team) | (df["team_away"] == team)].sort_values("date").tail(recent)
        if team_rows.empty:
            context["teams"][team] = {"available": False, "suggestions": get_close_matches(team, known_teams, n=5, cutoff=0.45)}
            continue
        xg_for: list[float] = []
        xg_against: list[float] = []
        goals_for: list[float] = []
        goals_against: list[float] = []
        for _, row in team_rows.iterrows():
            is_home = row["team_home"] == team
            if is_home:
                xg_for.append(float(row.get("xg_home", np.nan)))
                xg_against.append(float(row.get("xg_away", np.nan)))
                goals_for.append(float(row.get("goals_home", np.nan)))
                goals_against.append(float(row.get("goals_away", np.nan)))
            else:
                xg_for.append(float(row.get("xg_away", np.nan)))
                xg_against.append(float(row.get("xg_home", np.nan)))
                goals_for.append(float(row.get("goals_away", np.nan)))
                goals_against.append(float(row.get("goals_home", np.nan)))
        context["teams"][team] = {
            "available": True,
            "matches": int(len(team_rows)),
            "xg_for_avg": safe_nanmean(xg_for),
            "xg_against_avg": safe_nanmean(xg_against),
            "goals_for_avg": safe_nanmean(goals_for),
            "goals_against_avg": safe_nanmean(goals_against),
        }
    return context


def clubelo_context(df: pd.DataFrame | None, fixture: MatchFixture) -> dict[str, Any]:
    if df is None or df.empty:
        return {"available": False}
    if "team" not in df.columns or "elo" not in df.columns:
        return {"available": False, "reason": "ClubElo dataframe missing team/elo columns"}

    lookup = df.set_index("team")
    names = lookup.index.astype(str).tolist()
    result: dict[str, Any] = {"available": True}
    for team, key in [(fixture.home, "home"), (fixture.away, "away")]:
        if team not in lookup.index:
            result[key] = {"available": False, "team": team, "suggestions": get_close_matches(team, names, n=5, cutoff=0.45)}
        else:
            row = lookup.loc[team]
            result[key] = {"available": True, "team": team, "elo": float(row["elo"])}
    home_elo = result.get("home", {}).get("elo")
    away_elo = result.get("away", {}).get("elo")
    if home_elo is not None and away_elo is not None:
        result["elo_diff_home_minus_away"] = home_elo - away_elo
    return result


def predict_fixture(
    bundle: ModelBundle,
    fixture: MatchFixture,
    market_book: MarketBook | None = None,
    total_lines: list[float] | None = None,
    home_handicaps: list[float] | None = None,
    top_scores: int = 8,
    recent: int = 6,
    min_ev: float = 0.0,
    kelly_fraction_multiplier: float = 0.25,
    max_kelly: float | None = 0.03,
) -> FixturePredictionReport:
    teams = list_known_teams(bundle.football_data)
    assert_team_known(fixture.home, teams, "home team")
    assert_team_known(fixture.away, teams, "away team")

    total_lines = total_lines or DEFAULT_TOTAL_LINES
    home_handicaps = home_handicaps or DEFAULT_HOME_HANDICAPS
    market_book = market_book or MarketBook()
    model_predictions: dict[str, dict[str, Any]] = {}
    warnings = list(bundle.warnings)

    for name, model in bundle.models.items():
        try:
            grid = model.predict(fixture.home, fixture.away)
            model_predictions[name] = prediction_from_grid(grid, total_lines, home_handicaps, top_scores)
        except Exception as exc:
            warnings.append(f"Prediction failed for {name}: {type(exc).__name__}: {exc}")

    if not model_predictions:
        raise RuntimeError("All model predictions failed.")

    ensemble = average_prediction_dicts(model_predictions.values())
    betting_analysis = [
        item.to_dict()
        for item in analyze_market_book(
            market_book,
            ensemble,
            min_ev=min_ev,
            kelly_fraction_multiplier=kelly_fraction_multiplier,
            max_kelly=max_kelly,
        )
    ]

    summary = PredictionSummary(
        home_win=ensemble["home_win"],
        draw=ensemble["draw"],
        away_win=ensemble["away_win"],
        home_goal_expectation=ensemble["home_goal_expectation"],
        away_goal_expectation=ensemble["away_goal_expectation"],
        btts_yes=ensemble["btts_yes"],
        totals=ensemble["totals"],
        asian_handicaps=ensemble["asian_handicaps_home_perspective"],
        top_exact_scores=next(iter(model_predictions.values()))["top_exact_scores"],
    )

    return FixturePredictionReport(
        fixture=fixture,
        summary=summary,
        model_predictions=model_predictions,
        market_book=market_book,
        betting_analysis=betting_analysis,
        context=PredictionContext(
            understat_recent_xg=recent_xg_context(bundle.understat_data, fixture, recent),
            clubelo=clubelo_context(bundle.clubelo_data, fixture),
        ),
        metadata={**bundle.metadata, "model_count": len(model_predictions), "models": list(model_predictions.keys())},
        warnings=warnings,
    )
