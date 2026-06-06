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


def filter_before_cutoff(df: pd.DataFrame | None, cutoff_date: str | None) -> pd.DataFrame | None:
    """Keep rows dated strictly before ``cutoff_date``.

    This is the first no-future-data guard for training and context data. The
    cutoff is strict because a match on the cutoff date may not have finished
    before the fixture being predicted.
    """

    if df is None or not cutoff_date or df.empty or "date" not in df.columns:
        return df
    cutoff = pd.to_datetime(cutoff_date, errors="raise")
    filtered = df[pd.to_datetime(df["date"], errors="coerce") < cutoff].copy()
    return filtered


def load_football_data(competition: str, season: str, cutoff_date: str | None = None) -> pd.DataFrame:
    """Load historical fixtures/results from football-data.co.uk."""

    scraper = pb.scrapers.FootballData(competition, season)
    df = scraper.get_fixtures().reset_index()
    df = normalize_fixture_frame(df)
    df = df.dropna(subset=["date", "team_home", "team_away", "goals_home", "goals_away"])
    filtered = filter_before_cutoff(df, cutoff_date)
    return filtered if filtered is not None else df


def load_understat(
    competition: str,
    season: str,
    warnings: list[str] | None = None,
    cutoff_date: str | None = None,
) -> pd.DataFrame | None:
    """Load Understat fixture/xG data, returning None when the source fails."""

    sink = warnings if warnings is not None else []
    try:
        scraper = pb.scrapers.Understat(competition, season)
        df = scraper.get_fixtures().reset_index()
        df = normalize_fixture_frame(df)
        df = df.dropna(subset=["date", "team_home", "team_away"])
        filtered = filter_before_cutoff(df, cutoff_date)
        return filtered if filtered is not None else df
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
    cutoff_date: str | None = None,
) -> LoadedData:
    """Load the standard prediction data bundle."""

    warnings: list[str] = []
    football_data = load_football_data(competition, season, cutoff_date=cutoff_date)
    understat_data = load_understat(competition, season, warnings, cutoff_date=cutoff_date) if use_understat else None
    clubelo_as_of = elo_date or cutoff_date
    clubelo_data = load_clubelo(clubelo_as_of, warnings) if use_clubelo else None
    if cutoff_date:
        warnings.append(f"Training/context data filtered to dates before {cutoff_date}")
    return LoadedData(
        football_data=football_data,
        understat_data=understat_data,
        clubelo_data=clubelo_data,
        warnings=warnings,
    )
