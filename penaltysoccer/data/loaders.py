"""Data loaders wrapping penaltyblog scrapers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as date_cls
import io
import warnings as py_warnings

import pandas as pd
from pandas.errors import PerformanceWarning
import penaltyblog as pb
from penaltyblog.scrapers.common import sanitize_columns
import requests

from .fixtures import normalize_fixture_frame

ProgressCallback = Callable[[str], None]


@dataclass
class LoadedData:
    """Container for optional data sources used by predictions."""

    football_data: pd.DataFrame
    understat_data: pd.DataFrame | None = None
    clubelo_data: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _scrape_with_warning_policy(callback: Callable[[], pd.DataFrame], suppress_dataframe_warnings: bool) -> pd.DataFrame:
    """Run a scraper while optionally hiding noisy pandas fragmentation warnings."""

    if not suppress_dataframe_warnings:
        return callback()
    with py_warnings.catch_warnings():
        py_warnings.filterwarnings("ignore", category=PerformanceWarning)
        return callback()


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


def load_football_data(
    competition: str,
    season: str,
    cutoff_date: str | None = None,
    progress: ProgressCallback | None = None,
    suppress_dataframe_warnings: bool = True,
) -> pd.DataFrame:
    """Load historical fixtures/results from football-data.co.uk."""

    _progress(progress, f"Loading FootballData: {competition} {season}")
    scraper = pb.scrapers.FootballData(competition, season)
    df = _scrape_with_warning_policy(lambda: scraper.get_fixtures().reset_index(), suppress_dataframe_warnings)
    df = normalize_fixture_frame(df)
    df = df.dropna(subset=["date", "team_home", "team_away", "goals_home", "goals_away"])
    before = len(df)
    filtered = filter_before_cutoff(df, cutoff_date)
    output = filtered if filtered is not None else df
    if cutoff_date:
        _progress(progress, f"FootballData loaded: {len(output)} completed matches before {cutoff_date} from {before} available rows")
    else:
        _progress(progress, f"FootballData loaded: {len(output)} completed matches")
    return output


def load_understat(
    competition: str,
    season: str,
    warnings: list[str] | None = None,
    cutoff_date: str | None = None,
    progress: ProgressCallback | None = None,
    suppress_dataframe_warnings: bool = True,
) -> pd.DataFrame | None:
    """Load Understat fixture/xG data, returning None when the source fails."""

    sink = warnings if warnings is not None else []
    _progress(progress, f"Loading Understat context: {competition} {season}")
    try:
        scraper = pb.scrapers.Understat(competition, season)
        df = _scrape_with_warning_policy(lambda: scraper.get_fixtures().reset_index(), suppress_dataframe_warnings)
        df = normalize_fixture_frame(df)
        df = df.dropna(subset=["date", "team_home", "team_away"])
        before = len(df)
        filtered = filter_before_cutoff(df, cutoff_date)
        output = filtered if filtered is not None else df
        if cutoff_date:
            _progress(progress, f"Understat loaded: {len(output)} rows before {cutoff_date} from {before} available rows")
        else:
            _progress(progress, f"Understat loaded: {len(output)} rows")
        return output
    except Exception as exc:
        message = f"Understat skipped: {type(exc).__name__}: {exc}"
        _progress(progress, message)
        sink.append(message)
        return None


def _clubelo_date_path(as_of: str | None) -> str:
    if as_of is None:
        today = date_cls.today()
        return f"{today.year}-{today.month}-{today.day}"
    parsed = pd.to_datetime(as_of, errors="raise").date()
    return f"{parsed.year}-{parsed.month}-{parsed.day}"


def _parse_clubelo_csv(content: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(content))
    if df.empty:
        raise ValueError("ClubElo returned an empty CSV")
    df = df.rename(columns={"Club": "team", "Elo": "elo"})
    df = sanitize_columns(df)
    if "team" not in df.columns or "elo" not in df.columns:
        raise ValueError(f"ClubElo CSV missing required columns. Available columns: {list(df.columns)}")
    if "from" in df.columns:
        df["from"] = pd.to_datetime(df["from"], errors="coerce")
    if "to" in df.columns:
        df["to"] = pd.to_datetime(df["to"], errors="coerce")
    return df.sort_values("elo", ascending=False).reset_index(drop=True)


def _download_clubelo_csv(url: str, timeout: float) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "Chrome/102.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    if not response.text.strip():
        raise ValueError("empty response")
    return response.text


def load_clubelo(
    as_of: str | None = None,
    warnings: list[str] | None = None,
    progress: ProgressCallback | None = None,
    timeout: float = 20.0,
) -> pd.DataFrame | None:
    """Load ClubElo ratings, returning None when the source fails.

    The upstream penaltyblog ClubElo scraper uses HTTP without a request timeout,
    which can block indefinitely when api.clubelo.com accepts the connection but
    sends no data. The application layer uses explicit timeouts and tries HTTPS
    before HTTP so training can continue with a clear warning when ClubElo is
    unreachable from the current environment.
    """

    sink = warnings if warnings is not None else []
    label = as_of or "latest"
    path = _clubelo_date_path(as_of)
    urls = [f"https://api.clubelo.com/{path}", f"http://api.clubelo.com/{path}"]
    _progress(progress, f"Loading ClubElo ratings: {label} with {timeout:g}s timeout")
    errors: list[str] = []
    for url in urls:
        try:
            _progress(progress, f"Trying ClubElo endpoint: {url}")
            content = _download_clubelo_csv(url, timeout=timeout)
            df = _parse_clubelo_csv(content)
            _progress(progress, f"ClubElo loaded: {len(df)} rows from {url}")
            return df
        except Exception as exc:
            errors.append(f"{url} -> {type(exc).__name__}: {exc}")
            _progress(progress, f"ClubElo endpoint failed: {type(exc).__name__}: {exc}")

    message = "ClubElo skipped after endpoint failures: " + " | ".join(errors)
    _progress(progress, message)
    sink.append(message)
    return None


def load_all_sources(
    competition: str,
    season: str,
    use_understat: bool = True,
    use_clubelo: bool = True,
    elo_date: str | None = None,
    cutoff_date: str | None = None,
    progress: ProgressCallback | None = None,
    suppress_dataframe_warnings: bool = True,
    clubelo_timeout: float = 20.0,
) -> LoadedData:
    """Load the standard prediction data bundle."""

    warnings: list[str] = []
    football_data = load_football_data(
        competition,
        season,
        cutoff_date=cutoff_date,
        progress=progress,
        suppress_dataframe_warnings=suppress_dataframe_warnings,
    )
    if use_understat:
        understat_data = load_understat(
            competition,
            season,
            warnings,
            cutoff_date=cutoff_date,
            progress=progress,
            suppress_dataframe_warnings=suppress_dataframe_warnings,
        )
    else:
        _progress(progress, "Understat disabled by config or CLI flag")
        understat_data = None

    clubelo_as_of = elo_date or cutoff_date
    if use_clubelo:
        clubelo_data = load_clubelo(clubelo_as_of, warnings, progress=progress, timeout=clubelo_timeout)
    else:
        _progress(progress, "ClubElo disabled by config or CLI flag")
        clubelo_data = None

    if cutoff_date:
        warnings.append(f"Training/context data filtered to dates before {cutoff_date}")
    return LoadedData(
        football_data=football_data,
        understat_data=understat_data,
        clubelo_data=clubelo_data,
        warnings=warnings,
    )
