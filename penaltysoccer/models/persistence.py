"""Model bundle persistence for the application layer."""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ModelBundle:
    """A serializable bundle containing trained models and context data."""

    models: dict[str, Any]
    metadata: dict[str, Any]
    football_data: pd.DataFrame
    understat_data: pd.DataFrame | None = None
    clubelo_data: pd.DataFrame | None = None
    warnings: list[str] = field(default_factory=list)


def save_bundle(bundle: ModelBundle, path: str | Path) -> None:
    """Save a model bundle as pickle."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(bundle, handle)


def load_bundle(path: str | Path) -> ModelBundle:
    """Load a model bundle saved by :func:`save_bundle`."""

    with Path(path).open("rb") as handle:
        loaded = pickle.load(handle)
    if isinstance(loaded, ModelBundle):
        return loaded
    if isinstance(loaded, dict):
        return ModelBundle(
            models=loaded["models"],
            metadata=loaded.get("metadata", {}),
            football_data=loaded.get("football_data", pd.DataFrame()),
            understat_data=loaded.get("understat_data"),
            clubelo_data=loaded.get("clubelo_data"),
            warnings=loaded.get("warnings", []),
        )
    raise TypeError(f"Unsupported bundle type: {type(loaded)!r}")
