"""Prediction ensembling helpers."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def average_prediction_dicts(predictions: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Average compatible nested prediction dictionaries.

    Numeric scalar leaves are averaged. Lists of numeric values, such as
    ``home_draw_away``, are averaged elementwise. Non-numeric structures, such
    as the ``top_exact_scores`` list of dictionaries, keep the first model's
    value. This is intentionally simple for the first application-layer version;
    later versions can add model weights based on backtesting metrics.
    """

    values = list(predictions)
    if not values:
        return {}

    def combine(items: list[Any]) -> Any:
        first = items[0]
        if isinstance(first, dict):
            return {key: combine([item[key] for item in items]) for key in first.keys()}
        if isinstance(first, list):
            if not first:
                return []
            if all(isinstance(item, list) and len(item) == len(first) for item in items):
                if all(isinstance(item[i], (int, float, np.number)) for item in items for i in range(len(first))):
                    return [float(np.mean([item[i] for item in items])) for i in range(len(first))]
            return first
        if isinstance(first, (int, float, np.number)):
            return float(np.mean(items))
        return first

    return {key: combine([item[key] for item in values]) for key in values[0].keys()}
