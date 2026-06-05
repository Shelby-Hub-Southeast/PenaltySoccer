"""JSON serialization helpers for reports."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [to_jsonable(v) for v in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def dataclass_to_dict(value: Any) -> dict[str, Any]:
    return to_jsonable(value)


def save_reports_json(reports: list[Any], path: str | Path) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [to_jsonable(report) for report in reports]
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
