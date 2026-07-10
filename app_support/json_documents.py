from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def write_json_atomic(path: Path, payload: Any) -> None:
    write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def load_normalized_json(path: Path, normalize: Callable[[Any], T]) -> T:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        normalized = normalize({})
        write_json_atomic(path, normalized)
        return normalized
    return normalize(load_json(path))


def save_normalized_json(path: Path, payload: Any, normalize: Callable[[Any], T]) -> T:
    normalized = normalize(payload)
    write_json_atomic(path, normalized)
    return normalized
