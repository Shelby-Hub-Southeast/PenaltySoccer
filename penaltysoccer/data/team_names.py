"""Team-name helpers shared across data sources."""

from __future__ import annotations

from difflib import get_close_matches

import pandas as pd


def list_known_teams(df: pd.DataFrame) -> list[str]:
    """Return sorted unique teams from a normalized fixture dataframe."""

    if "team_home" not in df.columns or "team_away" not in df.columns:
        return []
    teams = pd.concat([df["team_home"], df["team_away"]], ignore_index=True).dropna().astype(str)
    return sorted(teams.unique().tolist())


def assert_team_known(team: str, teams: list[str], label: str = "team") -> None:
    """Raise a helpful error when a team is not in the training data."""

    if team in teams:
        return
    suggestions = get_close_matches(team, teams, n=8, cutoff=0.45)
    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
    raise ValueError(f"Unknown {label}: {team}.{hint}")
