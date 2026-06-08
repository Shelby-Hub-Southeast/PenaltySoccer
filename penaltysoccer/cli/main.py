"""Command-line entrypoint for the PenaltySoccer application layer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from penaltysoccer.data.team_names import list_known_teams
from penaltysoccer.models.persistence import load_bundle, save_bundle
from penaltysoccer.models.training import train_model_bundle
from penaltysoccer.prediction.batch import predict_batch_from_config
from penaltysoccer.reporting.json_report import save_reports_json
from penaltysoccer.reporting.markdown_report import save_reports_markdown
from penaltysoccer.reporting.terminal_report import print_prediction_report, print_reports_summary


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def progress(message: str) -> None:
    print(f"[PenaltySoccer] {message}", flush=True)


def apply_prediction_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Return a config copy with CLI prediction overrides applied."""

    updated = dict(config)
    for arg_name, config_key in [
        ("min_ev", "min_ev"),
        ("min_edge", "min_edge"),
        ("kelly_fraction", "kelly_fraction"),
        ("max_kelly", "max_kelly"),
        ("sort_by", "sort_by"),
    ]:
        value = getattr(args, arg_name, None)
        if value is not None:
            updated[config_key] = value
    return updated


def apply_training_overrides(config: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """Return a config copy with CLI training overrides applied."""

    updated = dict(config)
    if args.cutoff_date:
        updated["cutoff_date"] = args.cutoff_date
    if args.no_understat:
        updated["use_understat"] = False
    if args.no_clubelo:
        updated["use_clubelo"] = False
    if args.min_training_matches is not None:
        updated["min_training_matches"] = args.min_training_matches
    if args.show_dataframe_warnings:
        updated["suppress_dataframe_warnings"] = False
    else:
        updated.setdefault("suppress_dataframe_warnings", True)
    return updated


def command_train(args: argparse.Namespace) -> int:
    config = apply_training_overrides(load_json(args.config), args)
    progress(f"Training config: {args.config}")
    if config.get("cutoff_date"):
        progress(f"Cutoff date: {config['cutoff_date']}")
    if not config.get("use_understat", True):
        progress("Understat context disabled")
    if not config.get("use_clubelo", True):
        progress("ClubElo context disabled")

    bundle = train_model_bundle(config, progress=progress)
    model_out = args.model_out or config.get("model_out")
    if not model_out:
        raise ValueError("Model output path is required via --model-out or config.model_out")
    progress(f"Saving model bundle: {model_out}")
    save_bundle(bundle, model_out)
    print(f"Saved model bundle to: {model_out}")
    print(f"Models trained: {', '.join(bundle.models.keys())}")
    print(f"Training matches: {len(bundle.football_data)}")
    if bundle.metadata.get("cutoff_date"):
        print(f"Cutoff date: {bundle.metadata['cutoff_date']}")
    if bundle.warnings:
        print("Warnings:")
        for warning in bundle.warnings:
            print(f"- {warning}")
    return 0


def command_predict(args: argparse.Namespace) -> int:
    config = apply_prediction_overrides(load_json(args.config), args)
    model_path = args.model or config.get("model")
    if not model_path:
        raise ValueError("Model path is required via --model or config.model")
    bundle = load_bundle(model_path)
    reports = predict_batch_from_config(bundle, config)
    print_reports_summary(reports)
    if len(reports) == 1 or args.verbose:
        for report in reports:
            print_prediction_report(report)

    report_out = args.report_out or config.get("report_out")
    if report_out:
        save_reports_json(reports, report_out)
        print(f"Saved report JSON to: {report_out}")

    markdown_out = args.markdown_out or config.get("markdown_out")
    if markdown_out:
        save_reports_markdown(reports, markdown_out)
        print(f"Saved report Markdown to: {markdown_out}")
    return 0


def command_teams(args: argparse.Namespace) -> int:
    """Print known teams in a saved model bundle."""

    bundle = load_bundle(args.model)
    teams = list_known_teams(bundle.football_data)
    if args.query:
        q = args.query.lower()
        teams = [team for team in teams if q in team.lower()]
    for team in teams:
        print(team)
    print(f"Total teams: {len(teams)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PenaltySoccer application-layer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Train models from a training config")
    train.add_argument("--config", required=True, help="Training config JSON path")
    train.add_argument("--model-out", default=None, help="Override model output path")
    train.add_argument("--cutoff-date", default=None, help="Use only matches before this date for training/context data")
    train.add_argument("--no-understat", action="store_true", help="Disable Understat context loading for this training run")
    train.add_argument("--no-clubelo", action="store_true", help="Disable ClubElo context loading for this training run")
    train.add_argument("--min-training-matches", type=int, default=None, help="Minimum completed matches required after filtering")
    train.add_argument("--show-dataframe-warnings", action="store_true", help="Show pandas DataFrame fragmentation warnings from scrapers")
    train.set_defaults(func=command_train)

    predict = subparsers.add_parser("predict", help="Predict fixtures from a prediction config")
    predict.add_argument("--config", required=True, help="Prediction config JSON path")
    predict.add_argument("--model", default=None, help="Override model bundle path")
    predict.add_argument("--report-out", default=None, help="Override report output JSON path")
    predict.add_argument("--markdown-out", default=None, help="Override report output Markdown path")
    predict.add_argument("--min-ev", type=float, default=None, help="Override minimum EV threshold")
    predict.add_argument("--min-edge", type=float, default=None, help="Override minimum raw-edge threshold for binary markets")
    predict.add_argument("--kelly-fraction", type=float, default=None, help="Override fractional Kelly multiplier")
    predict.add_argument("--max-kelly", type=float, default=None, help="Override maximum suggested Kelly fraction")
    predict.add_argument("--sort-by", default=None, choices=["input", "value_bets", "best_ev", "home_win", "away_win"], help="Override batch summary sorting")
    predict.add_argument("--verbose", action="store_true", help="Print full report for every fixture")
    predict.set_defaults(func=command_predict)

    teams = subparsers.add_parser("teams", help="List teams available in a model bundle")
    teams.add_argument("--model", required=True, help="Model bundle path")
    teams.add_argument("--query", default=None, help="Optional substring filter")
    teams.set_defaults(func=command_teams)

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
