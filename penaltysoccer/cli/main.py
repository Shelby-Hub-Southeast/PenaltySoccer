"""Command-line entrypoint for the PenaltySoccer application layer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from penaltysoccer.models.persistence import load_bundle, save_bundle
from penaltysoccer.models.training import train_model_bundle
from penaltysoccer.prediction.batch import predict_batch_from_config
from penaltysoccer.reporting.json_report import save_reports_json
from penaltysoccer.reporting.markdown_report import save_reports_markdown
from penaltysoccer.reporting.terminal_report import print_prediction_report, print_reports_summary


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def command_train(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    bundle = train_model_bundle(config)
    model_out = args.model_out or config.get("model_out")
    if not model_out:
        raise ValueError("Model output path is required via --model-out or config.model_out")
    save_bundle(bundle, model_out)
    print(f"Saved model bundle to: {model_out}")
    print(f"Models trained: {', '.join(bundle.models.keys())}")
    print(f"Training matches: {len(bundle.football_data)}")
    if bundle.warnings:
        print("Warnings:")
        for warning in bundle.warnings:
            print(f"- {warning}")
    return 0


def command_predict(args: argparse.Namespace) -> int:
    config = load_json(args.config)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PenaltySoccer application-layer CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    train = subparsers.add_parser("train", help="Train models from a training config")
    train.add_argument("--config", required=True, help="Training config JSON path")
    train.add_argument("--model-out", default=None, help="Override model output path")
    train.set_defaults(func=command_train)

    predict = subparsers.add_parser("predict", help="Predict fixtures from a prediction config")
    predict.add_argument("--config", required=True, help="Prediction config JSON path")
    predict.add_argument("--model", default=None, help="Override model bundle path")
    predict.add_argument("--report-out", default=None, help="Override report output JSON path")
    predict.add_argument("--markdown-out", default=None, help="Override report output Markdown path")
    predict.add_argument("--verbose", action="store_true", help="Print full report for every fixture")
    predict.set_defaults(func=command_predict)

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
