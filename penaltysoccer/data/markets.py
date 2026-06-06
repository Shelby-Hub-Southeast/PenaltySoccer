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


def validate_decimal_odds(value: float, label: str) -> float:
    odds = float(value)
    if odds <= 1.0:
        raise ValueError(f"{label} odds must be greater than 1.0, got {odds}")
    return odds


@dataclass(frozen=True)
class OneXTwoMarket:
    home: float
    draw: float
    away: float
    source: str = "config"
    bookmaker: str | None = None
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "1x2"

    def __post_init__(self) -> None:
        validate_decimal_odds(self.home, "1X2 home")
        validate_decimal_odds(self.draw, "1X2 draw")
        validate_decimal_odds(self.away, "1X2 away")


@dataclass(frozen=True)
class TotalMarket:
    line: float
    over: float | None = None
    under: float | None = None
    source: str = "config"
    bookmaker: str | None = None
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "total"

    def __post_init__(self) -> None:
        if self.over is None and self.under is None:
            raise ValueError(f"Total market {self.line} must include over or under odds")
        if self.over is not None:
            validate_decimal_odds(self.over, f"total {self.line} over")
        if self.under is not None:
            validate_decimal_odds(self.under, f"total {self.line} under")


@dataclass(frozen=True)
class AsianHandicapMarket:
    side: Literal["home", "away"]
    line: float
    odds: float
    source: str = "config"
    bookmaker: str | None = None
    captured_at: str = field(default_factory=now_utc_iso)
    market_type: MarketType = "asian_handicap"

    def __post_init__(self) -> None:
        if self.side not in {"home", "away"}:
            raise ValueError(f"Asian handicap side must be home or away, got {self.side}")
        validate_decimal_odds(self.odds, f"asian handicap {self.side} {self.line}")


@dataclass(frozen=True)
class MarketBook:
    one_x_two: OneXTwoMarket | None = None
    totals: list[TotalMarket] = field(default_factory=list)
    asian_handicaps: list[AsianHandicapMarket] = field(default_factory=list)
    source: str = "config"
    bookmaker: str | None = None
    captured_at: str = field(default_factory=now_utc_iso)

    @property
    def has_markets(self) -> bool:
        return bool(self.one_x_two or self.totals or self.asian_handicaps)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _item_meta(item: dict[str, Any], default_source: str, default_bookmaker: str | None, default_captured_at: str) -> tuple[str, str | None, str]:
    source = str(item.get("source") or default_source)
    bookmaker = item.get("bookmaker", default_bookmaker)
    captured_at = str(item.get("captured_at") or default_captured_at)
    return source, bookmaker, captured_at


def load_market_book_from_config(markets: dict[str, Any] | None, source: str = "config") -> MarketBook:
    """Parse a fixture's ``markets`` config into normalized market objects.

    The returned structures are intentionally source-agnostic. Future adapters
    for historical odds, APIs, web pages, or screenshot parsing should return the
    same objects so prediction and betting logic do not change.
    """

    if not markets:
        return MarketBook(source=source)

    source = str(markets.get("source") or source)
    bookmaker = markets.get("bookmaker")
    captured_at = str(markets.get("captured_at") or now_utc_iso())

    one_x_two = None
    raw_1x2 = markets.get("1x2")
    if raw_1x2:
        market_source, market_bookmaker, market_captured_at = _item_meta(raw_1x2, source, bookmaker, captured_at)
        one_x_two = OneXTwoMarket(
            home=float(raw_1x2["home"]),
            draw=float(raw_1x2["draw"]),
            away=float(raw_1x2["away"]),
            source=market_source,
            bookmaker=market_bookmaker,
            captured_at=market_captured_at,
        )

    totals = []
    for item in markets.get("totals", []):
        market_source, market_bookmaker, market_captured_at = _item_meta(item, source, bookmaker, captured_at)
        totals.append(
            TotalMarket(
                line=float(item["line"]),
                over=_float_or_none(item.get("over")),
                under=_float_or_none(item.get("under")),
                source=market_source,
                bookmaker=market_bookmaker,
                captured_at=market_captured_at,
            )
        )

    asian_handicaps = []
    for item in markets.get("asian_handicap", []):
        market_source, market_bookmaker, market_captured_at = _item_meta(item, source, bookmaker, captured_at)
        asian_handicaps.append(
            AsianHandicapMarket(
                side=item.get("side", "home"),
                line=float(item["line"]),
                odds=float(item["odds"]),
                source=market_source,
                bookmaker=market_bookmaker,
                captured_at=market_captured_at,
            )
        )

    return MarketBook(
        one_x_two=one_x_two,
        totals=totals,
        asian_handicaps=asian_handicaps,
        source=source,
        bookmaker=bookmaker,
        captured_at=captured_at,
    )
