"""Markdown report rendering for prediction batches."""

from __future__ import annotations

from pathlib import Path

from penaltysoccer.prediction.report_schema import FixturePredictionReport
from penaltysoccer.reporting.terminal_report import best_ev, best_value_bet, fmt_num, fmt_pct, value_rule


def _market_line(value: float | None) -> str:
    return "" if value is None else f"{float(value):g}"


def render_report_markdown(report: FixturePredictionReport) -> str:
    fixture = report.fixture
    summary = report.summary
    lines: list[str] = []
    lines.append(f"## {fixture.home} vs {fixture.away}")
    lines.append("")
    lines.append(f"Models: {', '.join(report.metadata.get('models', []))}")
    lines.append(f"Training matches: {report.metadata.get('training_match_count')}")
    if report.metadata.get("cutoff_date"):
        lines.append(f"Cutoff date: {report.metadata.get('cutoff_date')}")
    lines.append("")
    lines.append("### 1X2")
    lines.append("| Outcome | Probability |")
    lines.append("| --- | ---: |")
    lines.append(f"| Home | {fmt_pct(summary.home_win)} |")
    lines.append(f"| Draw | {fmt_pct(summary.draw)} |")
    lines.append(f"| Away | {fmt_pct(summary.away_win)} |")
    lines.append("")
    lines.append(f"Expected goals: **{fixture.home} {fmt_num(summary.home_goal_expectation)} - {fmt_num(summary.away_goal_expectation)} {fixture.away}**")
    lines.append(f"BTTS yes: **{fmt_pct(summary.btts_yes)}**")
    lines.append("")

    lines.append("### Totals")
    lines.append("| Line | Under | Push | Over | Lean |")
    lines.append("| ---: | ---: | ---: | ---: | --- |")
    for line, probs in summary.totals.items():
        lean = "Under" if probs["under"] >= probs["over"] else "Over"
        lines.append(f"| {line} | {fmt_pct(probs['under'])} | {fmt_pct(probs['push'])} | {fmt_pct(probs['over'])} | {lean} |")
    lines.append("")

    lines.append("### Asian handicap, home perspective")
    lines.append("| Home line | Home win | Home push | Away win | Lean |")
    lines.append("| ---: | ---: | ---: | ---: | --- |")
    for line, item in summary.asian_handicaps.items():
        home = item["home"]
        away = item["away"]
        lean = fixture.home if home["win"] >= away["win"] else fixture.away
        lines.append(f"| {float(line):g} | {fmt_pct(home['win'])} | {fmt_pct(home['push'])} | {fmt_pct(away['win'])} | {lean} |")
    lines.append("")

    if report.betting_analysis:
        lines.append("### Betting value analysis")
        lines.append("| Market | Selection | Line | Odds | Win | Push | Lose | Raw Edge | EV | Kelly | Rule | Source | Book | Value |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |")
        for item in report.betting_analysis:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item["market_type"]),
                        str(item["selection"]),
                        _market_line(item["line"]),
                        fmt_num(item["odds"], 2),
                        fmt_pct(item["win_probability"]),
                        fmt_pct(item["push_probability"]),
                        fmt_pct(item["lose_probability"]),
                        fmt_pct(item["edge"]),
                        fmt_num(item["expected_value"], 4),
                        fmt_pct(item["suggested_kelly"]),
                        value_rule(item),
                        str(item.get("source", "")),
                        str(item.get("bookmaker") or "-"),
                        "yes" if item["is_value_bet"] else "no",
                    ]
                )
                + " |"
            )
        lines.append("")

    if report.context.clubelo.get("available"):
        lines.append("### ClubElo")
        lines.append("```text")
        lines.append(str(report.context.clubelo))
        lines.append("```")
        lines.append("")
    if report.context.understat_recent_xg.get("available"):
        lines.append("### Understat recent xG")
        lines.append("```text")
        lines.append(str(report.context.understat_recent_xg))
        lines.append("```")
        lines.append("")
    if report.warnings:
        lines.append("### Warnings")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")
    return "\n".join(lines)


def render_reports_markdown(reports: list[FixturePredictionReport]) -> str:
    lines: list[str] = []
    lines.append("# PenaltySoccer prediction report")
    lines.append("")
    lines.append("## Batch summary")
    lines.append("| Fixture | Home | Draw | Away | xG | Value bets | Best EV | Best value |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |")
    for report in reports:
        fixture = report.fixture
        value_count = sum(1 for item in report.betting_analysis if item["is_value_bet"])
        lines.append(
            f"| {fixture.home} vs {fixture.away} | {fmt_pct(report.summary.home_win)} | {fmt_pct(report.summary.draw)} | "
            f"{fmt_pct(report.summary.away_win)} | {fmt_num(report.summary.home_goal_expectation)}-{fmt_num(report.summary.away_goal_expectation)} | "
            f"{value_count} | {fmt_num(best_ev(report), 4)} | {best_value_bet(report)} |"
        )
    lines.append("")
    for report in reports:
        lines.append(render_report_markdown(report))
    return "\n".join(lines)


def save_reports_markdown(reports: list[FixturePredictionReport], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_reports_markdown(reports), encoding="utf-8")
