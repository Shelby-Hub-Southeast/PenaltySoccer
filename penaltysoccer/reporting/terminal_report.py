"""Terminal report rendering."""

from __future__ import annotations

from typing import Any

from penaltysoccer.prediction.report_schema import FixturePredictionReport


def fmt_pct(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.2f}%"


def fmt_num(value: float | None, digits: int = 3) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def best_ev(report: FixturePredictionReport) -> float | None:
    values = [float(item["expected_value"]) for item in report.betting_analysis]
    return max(values) if values else None


def best_value_bet(report: FixturePredictionReport) -> str:
    value_items = [item for item in report.betting_analysis if item["is_value_bet"]]
    if not value_items:
        return "-"
    item = max(value_items, key=lambda row: float(row["expected_value"]))
    line = "" if item["line"] is None else f" {float(item['line']):g}"
    return f"{item['market_type']} {item['selection']}{line}"


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


def print_prediction_report(report: FixturePredictionReport) -> None:
    fixture = report.fixture
    summary = report.summary
    print_section(f"Prediction: {fixture.home} vs {fixture.away}")
    print(f"Models: {', '.join(report.metadata.get('models', []))}")
    print(f"Training matches: {report.metadata.get('training_match_count')}")

    print_section("1X2")
    print_table(
        [
            {"Outcome": "Home", "Probability": fmt_pct(summary.home_win)},
            {"Outcome": "Draw", "Probability": fmt_pct(summary.draw)},
            {"Outcome": "Away", "Probability": fmt_pct(summary.away_win)},
        ],
        ["Outcome", "Probability"],
    )
    print(f"Expected goals: {fixture.home} {fmt_num(summary.home_goal_expectation)} | {fixture.away} {fmt_num(summary.away_goal_expectation)}")
    print(f"BTTS yes: {fmt_pct(summary.btts_yes)}")

    print_section("Totals")
    rows = []
    for line, probs in summary.totals.items():
        lean = "Under" if probs["under"] >= probs["over"] else "Over"
        rows.append({"Line": line, "Under": fmt_pct(probs["under"]), "Push": fmt_pct(probs["push"]), "Over": fmt_pct(probs["over"]), "Lean": lean})
    print_table(rows, ["Line", "Under", "Push", "Over", "Lean"])

    print_section("Asian handicap, home perspective")
    rows = []
    for line, item in summary.asian_handicaps.items():
        home = item["home"]
        away = item["away"]
        lean = fixture.home if home["win"] >= away["win"] else fixture.away
        rows.append({"Home line": f"{float(line):g}", "Home win": fmt_pct(home["win"]), "Home push": fmt_pct(home["push"]), "Away win": fmt_pct(away["win"]), "Lean": lean})
    print_table(rows, ["Home line", "Home win", "Home push", "Away win", "Lean"])

    if report.betting_analysis:
        print_section("Betting value analysis")
        rows = []
        for item in report.betting_analysis:
            rows.append(
                {
                    "Market": item["market_type"],
                    "Selection": item["selection"],
                    "Line": "" if item["line"] is None else f"{float(item['line']):g}",
                    "Odds": fmt_num(item["odds"], 2),
                    "Win": fmt_pct(item["win_probability"]),
                    "Push": fmt_pct(item["push_probability"]),
                    "Lose": fmt_pct(item["lose_probability"]),
                    "Edge": fmt_pct(item["edge"]),
                    "EV": fmt_num(item["expected_value"], 4),
                    "Kelly": fmt_pct(item["suggested_kelly"]),
                    "Source": item.get("source", ""),
                    "Book": item.get("bookmaker") or "-",
                    "Value": "yes" if item["is_value_bet"] else "no",
                }
            )
        print_table(rows, ["Market", "Selection", "Line", "Odds", "Win", "Push", "Lose", "Edge", "EV", "Kelly", "Source", "Book", "Value"])

    if report.context.clubelo.get("available"):
        print_section("ClubElo")
        print(report.context.clubelo)
    if report.context.understat_recent_xg.get("available"):
        print_section("Understat recent xG")
        print(report.context.understat_recent_xg)

    if report.warnings:
        print_section("Warnings")
        for warning in report.warnings:
            print(f"- {warning}")


def print_reports_summary(reports: list[FixturePredictionReport]) -> None:
    print_section("Batch summary")
    rows = []
    for report in reports:
        rows.append(
            {
                "Fixture": f"{report.fixture.home} vs {report.fixture.away}",
                "Home": fmt_pct(report.summary.home_win),
                "Draw": fmt_pct(report.summary.draw),
                "Away": fmt_pct(report.summary.away_win),
                "xG": f"{fmt_num(report.summary.home_goal_expectation)}-{fmt_num(report.summary.away_goal_expectation)}",
                "Value bets": str(sum(1 for item in report.betting_analysis if item["is_value_bet"])),
                "Best EV": fmt_num(best_ev(report), 4),
                "Best value": best_value_bet(report),
            }
        )
    print_table(rows, ["Fixture", "Home", "Draw", "Away", "xG", "Value bets", "Best EV", "Best value"])
