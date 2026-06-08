"""Training workflow for PenaltySoccer models."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import penaltyblog as pb

from penaltysoccer.data.loaders import load_all_sources

from .persistence import ModelBundle
from .registry import DEFAULT_MODELS, MODEL_REGISTRY

ProgressCallback = Callable[[str], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def train_models(
    football_data: pd.DataFrame,
    model_names: list[str] | None = None,
    xi: float = 0.001,
    warnings: list[str] | None = None,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Train selected penaltyblog goal models from normalized football data."""

    sink = warnings if warnings is not None else []
    names = model_names or DEFAULT_MODELS
    if football_data.empty:
        raise ValueError("No completed matches are available for training.")

    _progress(progress, f"Building Dixon-Coles time weights with xi={xi}")
    weights = pb.models.dixon_coles_weights(football_data["date"], xi=xi)
    trained: dict[str, Any] = {}
    for name in names:
        if name not in MODEL_REGISTRY:
            sink.append(f"Unknown model skipped: {name}")
            continue
        try:
            _progress(progress, f"Training model: {name}")
            model = MODEL_REGISTRY[name](
                football_data["goals_home"],
                football_data["goals_away"],
                football_data["team_home"],
                football_data["team_away"],
                weights=weights,
            )
            model.fit()
            trained[name] = model
            _progress(progress, f"Model trained: {name}")
        except Exception as exc:
            message = f"Model {name} failed and was skipped: {type(exc).__name__}: {exc}"
            _progress(progress, message)
            sink.append(message)

    if not trained:
        raise RuntimeError("All requested models failed to train.")
    return trained


def train_model_bundle(config: dict[str, Any], progress: ProgressCallback | None = None) -> ModelBundle:
    """Train a complete model bundle from a JSON-style config dict."""

    competition = config["competition"]
    season = config["season"]
    cutoff_date = config.get("cutoff_date")
    warnings: list[str] = []
    _progress(progress, f"Preparing training bundle: {competition} {season}")
    loaded = load_all_sources(
        competition=competition,
        season=season,
        use_understat=bool(config.get("use_understat", True)),
        use_clubelo=bool(config.get("use_clubelo", True)),
        elo_date=config.get("elo_date"),
        cutoff_date=cutoff_date,
        progress=progress,
        suppress_dataframe_warnings=bool(config.get("suppress_dataframe_warnings", True)),
    )
    warnings.extend(loaded.warnings)
    model_names = list(config.get("models") or DEFAULT_MODELS)
    xi = float(config.get("xi", 0.001))
    min_training_matches = int(config.get("min_training_matches", 80))
    match_count = int(len(loaded.football_data))
    _progress(progress, f"Training data ready: {match_count} matches, {loaded.football_data['team_home'].nunique()} home teams")
    if match_count < min_training_matches:
        raise ValueError(
            f"Only {match_count} completed matches available after filtering; "
            f"minimum required is {min_training_matches}. Use a later cutoff date or lower min_training_matches."
        )

    models = train_models(loaded.football_data, model_names, xi, warnings, progress=progress)

    metadata = {
        "competition": competition,
        "season": season,
        "trained_at": utc_now_iso(),
        "cutoff_date": cutoff_date,
        "training_match_count": match_count,
        "min_training_matches": min_training_matches,
        "training_start_date": loaded.football_data["date"].min().date().isoformat(),
        "training_end_date": loaded.football_data["date"].max().date().isoformat(),
        "models": list(models.keys()),
        "xi": xi,
        "used_understat": loaded.understat_data is not None,
        "used_clubelo": loaded.clubelo_data is not None,
        "clubelo_date": config.get("elo_date") or cutoff_date,
        "application_layer": "penaltysoccer",
    }
    _progress(progress, "Training bundle ready")
    return ModelBundle(
        models=models,
        metadata=metadata,
        football_data=loaded.football_data,
        understat_data=loaded.understat_data,
        clubelo_data=loaded.clubelo_data,
        warnings=warnings,
    )
