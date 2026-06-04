#!/usr/bin/env python3
"""Full football prediction workflow built on penaltyblog.

The script has three modes:

1. train: fetch results, fit one or more models, and save a reusable bundle.
2. predict: load a saved bundle and analyse one fixture.
3. train-predict: train and immediately analyse one fixture.

Default handicap convention follows the app screenshots used in this project:
negative line means the home team receives goals, positive/no-sign line means
home team gives goals. Use --handicap-style standard for the native penaltyblog
sign convention.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import penaltyblog as pb


DEFAULT_MODELS = ["dc", "poisson", "bivariate"]
DEFAULT_TOTAL_LINES = [2.0, 2.25, 2.5, 2.75, 3.0, 3.25]
DEFAULT_APP_HOME_HANDICAPS = [
    -1.5,
    -1.25,
    -1.0,
    -0.75,
    -0.5,
    -0.25,
    0.0,
    0.25,
    0.5,
    0.75,
    1.0,
    1.25,
    1.5,
]
DEFAULT_TOP_SCORES = 8
DEFAULT_RECENT_MATCHES = 6

MODEL_REGISTRY = {
    "dc": pb.models.DixonColesGoalModel,
    "poisson": pb.models.PoissonGoalsModel,
    "bivariate": pb.models.BivariatePoissonGoalModel,
    "negative_binomial": pb.models.NegativeBinomialGoalModel,
    "zero_inflated": pb.models.ZeroInflatedPoissonGoalsModel,
    "weibull_copula": pb.models.WeibullCopulaGoalsModel,
}

MODEL_DISPLAY_NAMES = {
    "dc": "Dixon-Coles",
    "poisson": "Poisson",
    "bivariate": "Bivariate Poisson",
    "negative_binomial": "Negative Binomial",
    "zero_inflated": "Zero-Inflated Poisson",
    "weibull_copula": "Weibull Copula",
}


@dataclass
class TrainResult:
    models: dict[str, Any]
    metadata: dict[str, Any]
    football_data: pd.DataFrame
    understat_data: pd.DataFrame | None = None
    clubelo_data: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class PredictionReport:
    metadata: dict[str, Any]
    home: str
    away: str
    model_predictions: dict[str, dict[str, Any]]
    ensemble: dict[str, Any]
    context: dict[str, Any]
    warnings: list[str]


def parse_float_list(values: list[str] | None, defaults: list[float]) -> list[float]:
    if not values:
        return defaults
    return [float(value) for value in values]


def ensure_output_parent(path: str | Path | None) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)


def normalize_date_for_json(value: Any) -> Any:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_jsonable(v) for v in obj]
    return normalize_date_for_json(obj)


def print_section(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("(empty)")
        return
    widths = {col: max(len(col), *(len(str(row.get(col, ""))) for row in rows)) for col in columns}
    print("  ".join(col.ljust(widths[col]) for col in columns))
    print("  ".join("-" * widths[col] for col in columns))
    for row in rows:
        print("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def fmt_num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def load_football_data(competition: str, season: str) -> pd.DataFrame:
    scraper = pb.scrapers.FootballData(competition, season)
    df = scraper.get_fixtures().reset_index().copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["goals_home"] = pd.to_numeric(df["goals_home"], errors="coerce")
    df["goals_away"] = pd.to_numeric(df["goals_away"], errors="coerce")
    return df.dropna(subset=["date", "team_home", "team_away", "goals_home", "goals_away"])


def load_understat_data(competition: str, season: str, warnings: list[str]) -> pd.DataFrame | None:
    try:
        scraper = pb.scrapers.Understat(competition, season)
        df = scraper.get_fixtures().reset_index().copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        return df.dropna(subset=["date", "team_home", "team_away"])
    except Exception as exc:
        warnings.append(f"Understat enrichment skipped: {type(exc).__name__}: {exc}")
        return None


def load_clubelo_data(as_of: str | None, warnings: list[str]) -> pd.DataFrame | None:
    try:
        scraper = pb.scrapers.ClubElo()
        return scraper.get_elo_by_date(as_of).reset_index()
    except Exception as exc:
        warnings.append(f"ClubElo enrichment skipped: {type(exc).__name__}: {exc}")
        return None


def list_known_teams(df: pd.DataFrame) -> list[str]:
    teams = pd.concat([df["team_home"], df["team_away"]], ignore_index=True).dropna().astype(str)
    return sorted(teams.unique().tolist())


def assert_team_known(team: str, teams: list[str], label: str) -> None:
    if team in teams:
        return
    suggestions = get_close_matches(team, teams, n=8, cutoff=0.45)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise ValueError(f"Unknown {label} team: {team}.{hint}")


def train_models(df: pd.DataFrame, model_names: list[str], xi: float, warnings: list[str]) -> dict[str, Any]:
    if df.empty:
        raise ValueError("No completed matches are available for training.")

    weights = pb.models.dixon_coles_weights(df["date"], xi=xi)
    models: dict[str, Any] = {}

    for name in model_names:
        if name not in MODEL_REGISTRY:
            warnings.append(f"Unknown model skipped: {name}")
            continue
        try:
            model = MODEL_REGISTRY[name](
                df["goals_home"],
                df["goals_away"],
                df["team_home"],
                df["team_away"],
                weights=weights,
            )
            model.fit()
            models[name] = model
        except Exception as exc:
            warnings.append(f"Model {name} failed and was skipped: {type(exc).__name__}: {exc}")

    if not models:
        raise RuntimeError("All requested models failed to train.")
    return models


def build_training_result(args: argparse.Namespace) -> TrainResult:
    warnings: list[str] = []
    football_data = load_football_data(args.competition, args.season)
    understat_data = load_understat_data(args.competition, args.season, warnings) if args.use_understat else None
    clubelo_data = load_clubelo_data(args.elo_date, warnings) if args.use_clubelo else None
    models = train_models(football_data, args.models or DEFAULT_MODELS, args.xi, warnings)

    metadata = {
        "competition": args.competition,
        "season": args.season,
        "trained_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "training_match_count": int(len(football_data)),
        "training_start_date": football_data["date"].min().date().isoformat(),
        "training_end_date": football_data["date"].max().date().isoformat(),
        "models": list(models.keys()),
        "xi": args.xi,
        "used_understat": understat_data is not None,
        "used_clubelo": clubelo_data is not None,
        "clubelo_date": args.elo_date,
    }
    return TrainResult(models, metadata, football_data, understat_data, clubelo_data, warnings)


def save_bundle(result: TrainResult, path: str | Path) -> None:
    ensure_output_parent(path)
    bundle = {
        "models": result.models,
        "metadata": result.metadata,
        "football_data": result.football_data,
        "understat_data": result.understat_data,
        "clubelo_data": result.clubelo_data,
        "warnings": result.warnings,
    }
    with open(path, "wb") as handle:
        pickle.dump(bundle, handle)


def load_bundle(path: str | Path) -> TrainResult:
    with open(path, "rb") as handle:
        bundle = pickle.load(handle)
    return TrainResult(
        models=bundle["models"],
        metadata=bundle.get("metadata", {}),
        football_data=bundle.get("football_data", pd.DataFrame()),
        understat_data=bundle.get("understat_data"),
        clubelo_data=bundle.get("clubelo_data"),
        warnings=bundle.get("warnings", []),
    )


def app_line_to_penaltyblog_home_line(app_line: float, handicap_style: str) -> float:
    if handicap_style == "standard":
        return app_line
    if handicap_style == "app":
        return -app_line
    raise ValueError("handicap_style must be 'app' or 'standard'")


def top_exact_scores(pred: Any, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grid = pred.grid
    for home_goals in range(grid.shape[0]):
        for away_goals in range(grid.shape[1]):
            rows.append({"score": f"{home_goals}-{away_goals}", "prob": float(grid[home_goals, away_goals])})
    rows.sort(key=lambda item: item["prob"], reverse=True)
    return rows[:limit]


def prediction_from_grid(
    pred: Any,
    total_lines: list[float],
    home_handicaps: list[float],
    top_scores: int,
    handicap_style: str,
) -> dict[str, Any]:
    totals = {}
    for line in total_lines:
        under, push, over = pred.totals(line)
        totals[str(line)] = {"under": under, "push": push, "over": over}

    handicaps = {}
    for displayed_line in home_handicaps:
        model_home_line = app_line_to_penaltyblog_home_line(displayed_line, handicap_style)
        home_probs = pred.asian_handicap_probs("home", model_home_line)
        away_probs = pred.asian_handicap_probs("away", -model_home_line)
        handicaps[str(displayed_line)] = {
            "displayed_home_line": displayed_line,
            "handicap_style": handicap_style,
            "penaltyblog_home_line": model_home_line,
            "home": home_probs,
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


def mean_nested_dict(dicts: Iterable[dict[str, Any]]) -> dict[str, Any]:
    values = list(dicts)
    if not values:
        return {}

    def combine(items: list[Any]) -> Any:
        first = items[0]
        if isinstance(first, dict):
            return {key: combine([item[key] for item in items]) for key in first.keys()}
        if isinstance(first, list):
            return [float(np.mean([item[i] for item in items])) for i in range(len(first))]
        if isinstance(first, (int, float, np.number)):
            return float(np.mean(items))
        return first

    keys = [
        "home_win", "draw", "away_win", "home_draw_away",
        "home_goal_expectation", "away_goal_expectation", "btts_yes", "btts_no",
        "double_chance_1x", "double_chance_x2", "double_chance_12",
        "draw_no_bet_home", "draw_no_bet_away", "totals", "asian_handicaps_home_perspective",
    ]
    return {key: combine([item[key] for item in values]) for key in keys if key in values[0]}


def safe_nanmean(values: list[float]) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0 or np.all(np.isnan(arr)):
        return None
    return float(np.nanmean(arr))


def recent_xg_summary(df: pd.DataFrame | None, home: str, away: str, recent: int) -> dict[str, Any]:
    if df is None or df.empty:
        return {"available": False}
    summary: dict[str, Any] = {"available": True, "recent_matches": recent, "teams": {}}
    for team in [home, away]:
        team_rows = df[(df["team_home"] == team) | (df["team_away"] == team)].sort_values("date").tail(recent)
        if team_rows.empty:
            summary["teams"][team] = {"available": False, "suggestions": get_close_matches(team, list_known_teams(df), n=5, cutoff=0.45)}
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
        summary["teams"][team] = {
            "available": True,
            "matches": int(len(team_rows)),
            "xg_for_avg": safe_nanmean(xg_for),
            "xg_against_avg": safe_nanmean(xg_against),
            "goals_for_avg": safe_nanmean(goals_for),
            "goals_against_avg": safe_nanmean(goals_against),
        }
    return summary


def clubelo_summary(df: pd.DataFrame | None, home: str, away: str) -> dict[str, Any]:
    if df is None or df.empty:
        return {"available": False}
    if "team" not in df.columns or "elo" not in df.columns:
        return {"available": False, "reason": "ClubElo dataframe missing team/elo columns"}
    lookup = df.set_index("team")
    result: dict[str, Any] = {"available": True}
    team_names = lookup.index.astype(str).tolist()
    for team, key in [(home, "home"), (away, "away")]:
        if team not in lookup.index:
            result[key] = {"available": False, "team": team, "suggestions": get_close_matches(team, team_names, n=5, cutoff=0.45)}
        else:
            row = lookup.loc[team]
            result[key] = {"available": True, "team": team, "elo": float(row["elo"])}
    home_elo = result.get("home", {}).get("elo")
    away_elo = result.get("away", {}).get("elo")
    if home_elo is not None and away_elo is not None:
        result["elo_diff_home_minus_away"] = home_elo - away_elo
    return result


def implied_1x2_summary(odds: list[float] | None, ensemble_hda: list[float]) -> dict[str, Any]:
    if not odds:
        return {"available": False}
    implied = pb.implied.calculate_implied(odds, market_names=["home", "draw", "away"])
    probs = implied.probabilities
    gaps = [ensemble_hda[i] - probs[i] for i in range(3)]
    return {
        "available": True,
        "odds": odds,
        "method": str(implied.method),
        "margin": implied.margin,
        "implied_probabilities": probs,
        "model_minus_market": {"home": gaps[0], "draw": gaps[1], "away": gaps[2]},
    }


def build_model_leans(ensemble: dict[str, Any]) -> dict[str, Any]:
    h, d, a = ensemble["home_draw_away"]
    best_1x2 = max([("home", h), ("draw", d), ("away", a)], key=lambda item: item[1])
    totals = []
    for line, probs in ensemble["totals"].items():
        side = "under" if probs["under"] >= probs["over"] else "over"
        totals.append({"line": line, "lean": side, "probability": probs[side], "push": probs["push"]})
    handicaps = []
    for line, item in ensemble["asian_handicaps_home_perspective"].items():
        home_win = item["home"]["win"]
        away_win = item["away"]["win"]
        handicaps.append({"displayed_home_line": line, "lean": "home" if home_win >= away_win else "away", "probability": max(home_win, away_win)})
    return {"most_likely_1x2": {"outcome": best_1x2[0], "probability": best_1x2[1]}, "totals": totals, "asian_handicaps": handicaps}


def build_prediction_report(
    result: TrainResult,
    home: str,
    away: str,
    total_lines: list[float],
    home_handicaps: list[float],
    top_scores: int,
    recent: int,
    odds_1x2: list[float] | None,
    handicap_style: str,
) -> PredictionReport:
    teams = list_known_teams(result.football_data)
    assert_team_known(home, teams, "home")
    assert_team_known(away, teams, "away")
    model_predictions: dict[str, dict[str, Any]] = {}
    warnings = list(result.warnings)

    for name, model in result.models.items():
        try:
            pred = model.predict(home, away)
            model_predictions[name] = prediction_from_grid(pred, total_lines, home_handicaps, top_scores, handicap_style)
        except Exception as exc:
            warnings.append(f"Prediction failed for {name}: {type(exc).__name__}: {exc}")

    if not model_predictions:
        raise RuntimeError("All model predictions failed.")

    ensemble = mean_nested_dict(model_predictions.values())
    ensemble["model_count"] = len(model_predictions)
    ensemble["models"] = list(model_predictions.keys())
    ensemble["market_1x2"] = implied_1x2_summary(odds_1x2, ensemble["home_draw_away"])
    ensemble["model_leans"] = build_model_leans(ensemble)
    context = {
        "understat_recent_xg": recent_xg_summary(result.understat_data, home, away, recent),
        "clubelo": clubelo_summary(result.clubelo_data, home, away),
    }
    metadata = dict(result.metadata)
    metadata["predicted_at"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    metadata["handicap_style"] = handicap_style
    return PredictionReport(metadata, home, away, model_predictions, ensemble, context, warnings)


def print_prediction_report(report: PredictionReport) -> None:
    print_section("Prediction summary")
    print(f"Competition: {report.metadata.get('competition')} | Season: {report.metadata.get('season')}")
    print(f"Fixture: {report.home} vs {report.away}")
    print(f"Models: {', '.join(report.ensemble.get('models', []))}")
    print(f"Training matches: {report.metadata.get('training_match_count')}")
    print("Handicap style: app convention, negative means home receives; positive means home gives")

    h, d, a = report.ensemble["home_draw_away"]
    print_section("Ensemble 1X2")
    print_table([
        {"Outcome": "Home", "Probability": fmt_pct(h)},
        {"Outcome": "Draw", "Probability": fmt_pct(d)},
        {"Outcome": "Away", "Probability": fmt_pct(a)},
    ], ["Outcome", "Probability"])
    print(f"Expected goals: {report.home} {fmt_num(report.ensemble['home_goal_expectation'])} | {report.away} {fmt_num(report.ensemble['away_goal_expectation'])}")
    print(f"BTTS yes: {fmt_pct(report.ensemble['btts_yes'])}")
    print(f"Double chance 1X: {fmt_pct(report.ensemble['double_chance_1x'])}")
    print(f"Double chance X2: {fmt_pct(report.ensemble['double_chance_x2'])}")

    print_section("Totals")
    total_rows = []
    for line, probs in report.ensemble["totals"].items():
        lean = "Under" if probs["under"] >= probs["over"] else "Over"
        total_rows.append({"Line": line, "Under": fmt_pct(probs["under"]), "Push": fmt_pct(probs["push"]), "Over": fmt_pct(probs["over"]), "Lean": lean})
    print_table(total_rows, ["Line", "Under", "Push", "Over", "Lean"])

    print_section("Asian handicap, home app convention")
    ah_rows = []
    for line, item in report.ensemble["asian_handicaps_home_perspective"].items():
        home_probs = item["home"]
        away_probs = item["away"]
        side = report.home if home_probs["win"] >= away_probs["win"] else report.away
        ah_rows.append({"Home line": f"{float(line):g}", "Home win": fmt_pct(home_probs["win"]), "Home push": fmt_pct(home_probs["push"]), "Away win": fmt_pct(away_probs["win"]), "Lean": side})
    print_table(ah_rows, ["Home line", "Home win", "Home push", "Away win", "Lean"])

    print_section("Per-model 1X2 and top scores")
    model_rows = []
    for name, pred in report.model_predictions.items():
        h0, d0, a0 = pred["home_draw_away"]
        top_scores = ", ".join(f"{row['score']} {fmt_pct(row['prob'])}" for row in pred["top_exact_scores"][:3])
        model_rows.append({"Model": MODEL_DISPLAY_NAMES.get(name, name), "Home": fmt_pct(h0), "Draw": fmt_pct(d0), "Away": fmt_pct(a0), "Top scores": top_scores})
    print_table(model_rows, ["Model", "Home", "Draw", "Away", "Top scores"])

    market = report.ensemble.get("market_1x2", {})
    if market.get("available"):
        print_section("Market 1X2 comparison")
        rows = []
        for idx, label in enumerate(["home", "draw", "away"]):
            rows.append({"Outcome": label, "Model": fmt_pct(report.ensemble["home_draw_away"][idx]), "Market": fmt_pct(market["implied_probabilities"][idx]), "Gap": fmt_pct(market["model_minus_market"][label])})
        print_table(rows, ["Outcome", "Model", "Market", "Gap"])
        print(f"Market margin: {fmt_pct(market.get('margin'))}")

    print_section("Model lean snapshot")
    lean = report.ensemble["model_leans"]["most_likely_1x2"]
    print(f"Most likely 1X2: {lean['outcome']} ({fmt_pct(lean['probability'])})")

    print_section("Context enrichment")
    clubelo = report.context.get("clubelo", {})
    print("ClubElo:", json.dumps(to_jsonable(clubelo), indent=2, ensure_ascii=False) if clubelo.get("available") else "unavailable")
    xg = report.context.get("understat_recent_xg", {})
    print("Understat recent xG:", json.dumps(to_jsonable(xg), indent=2, ensure_ascii=False) if xg.get("available") else "unavailable")

    if report.warnings:
        print_section("Warnings")
        for warning in report.warnings:
            print(f"- {warning}")


def save_report_json(report: PredictionReport, path: str | None) -> None:
    if not path:
        return
    ensure_output_parent(path)
    Path(path).write_text(json.dumps(to_jsonable(report.__dict__), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved report JSON to: {path}")


def command_train(args: argparse.Namespace) -> int:
    result = build_training_result(args)
    save_bundle(result, args.model_out)
    print(f"Saved model bundle to: {args.model_out}")
    print(f"Models trained: {', '.join(result.models.keys())}")
    print(f"Training matches: {len(result.football_data)}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"- {warning}")
    return 0


def command_predict(args: argparse.Namespace) -> int:
    result = load_bundle(args.model)
    report = build_prediction_report(
        result,
        args.home,
        args.away,
        parse_float_list(args.totals, DEFAULT_TOTAL_LINES),
        parse_float_list(args.handicaps, DEFAULT_APP_HOME_HANDICAPS),
        args.top_scores,
        args.recent,
        args.odds_1x2,
        args.handicap_style,
    )
    print_prediction_report(report)
    save_report_json(report, args.report_out)
    return 0


def command_train_predict(args: argparse.Namespace) -> int:
    result = build_training_result(args)
    save_bundle(result, args.model_out)
    print(f"Saved model bundle to: {args.model_out}")
    report = build_prediction_report(
        result,
        args.home,
        args.away,
        parse_float_list(args.totals, DEFAULT_TOTAL_LINES),
        parse_float_list(args.handicaps, DEFAULT_APP_HOME_HANDICAPS),
        args.top_scores,
        args.recent,
        args.odds_1x2,
        args.handicap_style,
    )
    print_prediction_report(report)
    save_report_json(report, args.report_out)
    return 0


def add_common_train_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--competition", required=True, help="Penaltyblog competition name, e.g. ENG Premier League")
    parser.add_argument("--season", required=True, help="Season in format YYYY-YYYY, e.g. 2024-2025")
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS, choices=sorted(MODEL_REGISTRY.keys()))
    parser.add_argument("--xi", type=float, default=0.001, help="Dixon-Coles time-decay weight parameter")
    parser.add_argument("--use-understat", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--use-clubelo", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--elo-date", default=None, help="ClubElo date YYYY-MM-DD. Defaults to today")


def add_common_predict_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--totals", nargs="*", help="Totals lines, e.g. 2.5 2.75 3.0")
    parser.add_argument("--handicaps", nargs="*", help="Home handicap lines in selected style")
    parser.add_argument(
        "--handicap-style",
        choices=["app", "standard"],
        default="app",
        help="app: negative means home receives, positive means home gives. standard: penaltyblog convention.",
    )
    parser.add_argument("--top-scores", type=int, default=DEFAULT_TOP_SCORES)
    parser.add_argument("--recent", type=int, default=DEFAULT_RECENT_MATCHES, help="Recent matches for Understat xG summary")
    parser.add_argument("--odds-1x2", nargs=3, type=float, metavar=("HOME", "DRAW", "AWAY"))
    parser.add_argument("--report-out", default=None, help="Optional JSON report output path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Full penaltyblog football prediction workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Fetch data, train models, and save a model bundle")
    add_common_train_args(train)
    train.add_argument("--model-out", required=True)
    train.set_defaults(func=command_train)

    predict = subparsers.add_parser("predict", help="Load a saved model bundle and predict one fixture")
    predict.add_argument("--model", required=True, help="Path to saved model bundle")
    add_common_predict_args(predict)
    predict.set_defaults(func=command_predict)

    train_predict = subparsers.add_parser("train-predict", help="Train models and immediately predict one fixture")
    add_common_train_args(train_predict)
    add_common_predict_args(train_predict)
    train_predict.add_argument("--model-out", required=True)
    train_predict.set_defaults(func=command_train_predict)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
