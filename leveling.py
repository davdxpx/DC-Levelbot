"""Helper functions for XP and level tracking."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DATA_PATH = Path('xp_data.json')
XP_PER_LEVEL = 100


@dataclass
class UserData:
    xp: int = 0


def _load() -> dict[str, UserData]:
    if DATA_PATH.exists():
        print(f"\U0001F4C2 Lade {DATA_PATH.name}")
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {uid: UserData(**vals) for uid, vals in data.items()}
    return {}


def _save(data: dict[str, UserData]) -> None:
    print(f"\U0001F4BE Speichere {DATA_PATH.name}")
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump({k: vars(v) for k, v in data.items()}, f)


_DATA = _load()


def calculate_level(xp: int) -> int:
    return xp // XP_PER_LEVEL


def xp_for_next_level(level: int) -> int:
    return (level + 1) * XP_PER_LEVEL


def add_xp(user_id: int, amount: int) -> int:
    uid = str(user_id)
    data = _DATA.setdefault(uid, UserData())
    data.xp += amount
    print(f"\u2728 {uid} +{amount} XP")
    _save(_DATA)
    return calculate_level(data.xp)


def get_level(user_id: int) -> int:
    level = calculate_level(_DATA.get(str(user_id), UserData()).xp)
    print(f"\U0001F4CA Level von {user_id}: {level}")
    return level


def get_user_data(user_id: int) -> tuple[int, int, int]:
    data = _DATA.get(str(user_id), UserData())
    level = calculate_level(data.xp)
    next_xp = xp_for_next_level(level)
    return data.xp, level, next_xp


def get_top_users(limit: int) -> Iterable[tuple[int, int]]:
    sorted_items = sorted(_DATA.items(), key=lambda item: item[1].xp, reverse=True)
    for uid, dat in sorted_items[:limit]:
        yield int(uid), dat.xp


def new_day() -> None:
    """Placeholder for daily events or decay."""
    print("\U0001F525 Neuer Tag")
