"""Fixture data structures and normalization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class MatchFixture:
    """A normalized football fixture used by the application layer."""

    home: str
    away: str
    kickoff: str | None = None
    competition: str | None = None
    season: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "MatchFixture":
        home = data.get("home") or data.get("team_home")
        away = data.get("away") or data.get("team_away")
        if not home or not away:
            raise ValueError("Fixture must include home/team_home and away/team_away")
        return cls(
            home=str(home),
            away=str(away),
            kickoff=data.get("kickoff") or data.get("datetime"),
            competition=data.get("competition"),
            season=data.get("season"),
        )


def normalize_fixture_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a defensive copy with normalized date and goal columns.

    The lower-level ``penaltyblog.scrapers.FootballData`` already standardizes
    most names. This helper makes the application layer resilient to small
    source differences and keeps model-training inputs writable for Cython code.
    """

    normalized = df.copy()
    if "date" in normalized.columns:
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
    if "datetime" in normalized.columns:
        normalized["datetime"] = pd.to_datetime(normalized["datetime"], errors="coerce")
    if "goals_home" in normalized.columns:
        normalized["goals_home"] = pd.to_numeric(normalized["goals_home"], errors="coerce")
    if "goals_away" in normalized.columns:
        normalized["goals_away"] = pd.to_numeric(normalized["goals_away"], errors="coerce")
    return normalized
