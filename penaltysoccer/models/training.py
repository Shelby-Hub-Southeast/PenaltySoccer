"""Training workflow for PenaltySoccer models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import penaltyblog as pb

from penaltysoccer.data.loaders import load_all_sources

from .persistence import ModelBundle
from .registry import DEFAULT_MODELS, MODEL_REGISTRY


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def train_models(
    football_data: pd.DataFrame,
    model_names: list[str] | None = None,
    xi: float = 0.001,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Train selected penaltyblog goal models from normalized football data."""

    sink = warnings if warnings is not None else []
    names = model_names or DEFAULT_MODELS
    if football_data.empty:
        raise ValueError("No completed matches are available for training.")

    weights = pb.models.dixon_coles_weights(football_data["date"], xi=xi)
    trained: dict[str, Any] = {}
    for name in names:
        if name not in MODEL_REGISTRY:
            sink.append(f"Unknown model skipped: {name}")
            continue
        try:
            model = MODEL_REGISTRY[name](
                football_data["goals_home"],
                football_data["goals_away"],
                football_data["team_home"],
                football_data["team_away"],
                weights=weights,
            )
            model.fit()
            trained[name] = model
        except Exception as exc:
            sink.append(f"Model {name} failed and was skipped: {type(exc).__name__}: {exc}")

    if not trained:
        raise RuntimeError("All requested models failed to train.")
    return trained


def train_model_bundle(config: dict[str, Any]) -> ModelBundle:
    """Train a complete model bundle from a JSON-style config dict."""

    competition = config["competition"]
    season = config["season"]
    warnings: list[str] = []
    loaded = load_all_sources(
        competition=competition,
        season=season,
        use_understat=bool(config.get("use_understat", True)),
        use_clubelo=bool(config.get("use_clubelo", True)),
        elo_date=config.get("elo_date"),
    )
    warnings.extend(loaded.warnings)
    model_names = list(config.get("models") or DEFAULT_MODELS)
    xi = float(config.get("xi", 0.001))
    models = train_models(loaded.football_data, model_names, xi, warnings)

    metadata = {
        "competition": competition,
        "season": season,
        "trained_at": utc_now_iso(),
        "training_match_count": int(len(loaded.football_data)),
        "training_start_date": loaded.football_data["date"].min().date().isoformat(),
        "training_end_date": loaded.football_data["date"].max().date().isoformat(),
        "models": list(models.keys()),
        "xi": xi,
        "used_understat": loaded.understat_data is not None,
        "used_clubelo": loaded.clubelo_data is not None,
        "clubelo_date": config.get("elo_date"),
        "application_layer": "penaltysoccer",
    }
    return ModelBundle(
        models=models,
        metadata=metadata,
        football_data=loaded.football_data,
        understat_data=loaded.understat_data,
        clubelo_data=loaded.clubelo_data,
        warnings=warnings,
    )
