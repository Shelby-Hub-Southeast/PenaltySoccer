"""Data loaders wrapping penaltyblog scrapers."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import penaltyblog as pb

from .fixtures import normalize_fixture_frame


@dataclass
class LoadedData:
    """Container for optional data sources used by predictions."""

    football_data: pd.DataFrame
    understat_data: pd.DataFrame | None = None
    clubelo_data: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)


def load_football_data(competition: str, season: str) -> pd.DataFrame:
    """Load historical fixtures/results from football-data.co.uk."""

    scraper = pb.scrapers.FootballData(competition, season)
    df = scraper.get_fixtures().reset_index()
    df = normalize_fixture_frame(df)
    return df.dropna(subset=["date", "team_home", "team_away", "goals_home", "goals_away"])


def load_understat(competition: str, season: str, warnings: list[str] | None = None) -> pd.DataFrame | None:
    """Load Understat fixture/xG data, returning None when the source fails."""

    sink = warnings if warnings is not None else []
    try:
        scraper = pb.scrapers.Understat(competition, season)
        df = scraper.get_fixtures().reset_index()
        df = normalize_fixture_frame(df)
        return df.dropna(subset=["date", "team_home", "team_away"])
    except Exception as exc:
        sink.append(f"Understat skipped: {type(exc).__name__}: {exc}")
        return None


def load_clubelo(as_of: str | None = None, warnings: list[str] | None = None) -> pd.DataFrame | None:
    """Load ClubElo ratings, returning None when the source fails."""

    sink = warnings if warnings is not None else []
    try:
        scraper = pb.scrapers.ClubElo()
        return scraper.get_elo_by_date(as_of).reset_index()
    except Exception as exc:
        sink.append(f"ClubElo skipped: {type(exc).__name__}: {exc}")
        return None


def load_all_sources(
    competition: str,
    season: str,
    use_understat: bool = True,
    use_clubelo: bool = True,
    elo_date: str | None = None,
) -> LoadedData:
    """Load the standard prediction data bundle."""

    warnings: list[str] = []
    football_data = load_football_data(competition, season)
    understat_data = load_understat(competition, season, warnings) if use_understat else None
    clubelo_data = load_clubelo(elo_date, warnings) if use_clubelo else None
    return LoadedData(
        football_data=football_data,
        understat_data=understat_data,
        clubelo_data=clubelo_data,
        warnings=warnings,
    )
