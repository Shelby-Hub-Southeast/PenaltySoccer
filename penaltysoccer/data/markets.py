"""Market-data structures and config parsing.

This module is the first application-layer market source. It supports M0 market
input from JSON configuration files and creates normalized objects for 1X2,
totals, and Asian handicap markets. Later versions can add adapters for
FootballData historical odds, odds APIs, web scrapers, and screenshot parsing
without changing prediction or betting logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

MarketType = Literal["1x2", "total", "asian_handicap"]
Side = Literal["home", "away", "draw", "over", "under"]


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class OneXTwoMarket:
    home: float
    draw: float
    away: float
    source: str = "config"
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "1x2"


@dataclass(frozen=True)
class TotalMarket:
    line: float
    over: float | None = None
    under: float | None = None
    source: str = "config"
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "total"


@dataclass(frozen=True)
class AsianHandicapMarket:
    side: Literal["home", "away"]
    line: float
    odds: float
    source: str = "config"
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "asian_handicap"


@dataclass(frozen=True)
class MarketBook:
    one_x_two: OneXTwoMarket | None = None
    totals: list[TotalMarket] = field(default_factory=list)
    asian_handicaps: list[AsianHandicapMarket] = field(default_factory=list)
    source: str = "config"
    captured_at: str = field(default_factory=now_utc_iso)

    @property
    def has_markets(self) -> bool:
        return bool(self.one_x_two or self.totals or self.asian_handicaps)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def load_market_book_from_config(markets: dict[str, Any] | None, source: str = "config") -> MarketBook:
    """Parse a fixture's ``markets`` config into normalized market objects."""

    if not markets:
        return MarketBook(source=source)

    captured_at = str(markets.get("captured_at") or now_utc_iso())
    one_x_two = None
    raw_1x2 = markets.get("1x2")
    if raw_1x2:
        one_x_two = OneXTwoMarket(
            home=float(raw_1x2["home"]),
            draw=float(raw_1x2["draw"]),
            away=float(raw_1x2["away"]),
            source=source,
            captured_at=captured_at,
        )

    totals = [
        TotalMarket(
            line=float(item["line"]),
            over=_float_or_none(item.get("over")),
            under=_float_or_none(item.get("under")),
            source=source,
            captured_at=str(item.get("captured_at") or captured_at),
        )
        for item in markets.get("totals", [])
    ]

    asian_handicaps = [
        AsianHandicapMarket(
            side=item.get("side", "home"),
            line=float(item["line"]),
            odds=float(item["odds"]),
            source=source,
            captured_at=str(item.get("captured_at") or captured_at),
        )
        for item in markets.get("asian_handicap", [])
    ]

    return MarketBook(
        one_x_two=one_x_two,
        totals=totals,
        asian_handicaps=asian_handicaps,
        source=source,
        captured_at=captured_at,
    )
