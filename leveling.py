"""Helper functions for XP and level tracking."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DATA_PATH = Path('xp_data.json')
XP_PER_LEVEL = 100


from datetime import datetime, timedelta # Added datetime, timedelta

XP_DAILY_AMOUNT = 25 # Amount of XP for daily claim
DAILY_COOLDOWN_HOURS = 23 # Cooldown for daily claim

@dataclass
class UserData:
    xp: int = 0
    last_daily_claim: str | None = None # ISO format string


def _load() -> dict[str, UserData]:
    if DATA_PATH.exists():
        print(f"\U0001F4C2 Lade {DATA_PATH.name}")
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        processed_data = {}
        for uid, vals in raw_data.items():
            # Handle old format where last_daily_claim might not exist
            processed_data[uid] = UserData(
                xp=vals.get('xp', 0),
                last_daily_claim=vals.get('last_daily_claim')
            )
        return processed_data
    return {}

def _save(data_to_save: dict[str, UserData]) -> None:
    print(f"\U0001F4BE Speichere {DATA_PATH.name}")
    # Ensure all UserData fields are present for saving
    serializable_data = {}
    for k, v_obj in data_to_save.items():
        serializable_data[k] = {
            'xp': v_obj.xp,
            'last_daily_claim': v_obj.last_daily_claim
        }
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(serializable_data, f, indent=2) # Added indent for readability


_DATA = _load()


def get_user_object(user_id: int) -> UserData:
    """Ensures a user exists in _DATA and returns their UserData object."""
    uid_str = str(user_id)
    if uid_str not in _DATA:
        _DATA[uid_str] = UserData()
    return _DATA[uid_str]


def calculate_level(xp: int) -> int:
    return xp // XP_PER_LEVEL


def xp_for_next_level(level: int) -> int:
    return (level + 1) * XP_PER_LEVEL


def add_xp(user_id: int, amount: int) -> int:
    user_obj = get_user_object(user_id)
    user_obj.xp += amount
    print(f"\u2728 {user_id} +{amount} XP")
    _save(_DATA)
    return calculate_level(user_obj.xp)


def get_level(user_id: int) -> int:
    user_obj = get_user_object(user_id)
    level = calculate_level(user_obj.xp)
    print(f"\U0001F4CA Level von {user_id}: {level}")
    return level


def get_user_data(user_id: int) -> tuple[int, int, int]:
    user_obj = get_user_object(user_id)
    level = calculate_level(user_obj.xp)
    next_xp = xp_for_next_level(level)
    return user_obj.xp, level, next_xp


def can_claim_daily(user_id: int) -> tuple[bool, timedelta | None]:
    """Checks if a user can claim daily XP. Returns (can_claim, time_remaining)."""
    user_obj = get_user_object(user_id)
    if user_obj.last_daily_claim is None:
        return True, None

    last_claim_time = datetime.fromisoformat(user_obj.last_daily_claim)
    next_claim_time = last_claim_time + timedelta(hours=DAILY_COOLDOWN_HOURS)
    now = datetime.utcnow()

    if now >= next_claim_time:
        return True, None
    else:
        return False, next_claim_time - now


def claim_daily(user_id: int) -> tuple[int | None, int]:
    """Attempts to claim daily XP for the user. Returns (xp_gained, new_level) or (None, current_level) if on cooldown."""
    can_claim, _ = can_claim_daily(user_id)
    user_obj = get_user_object(user_id) # Ensure user_obj is fresh

    if not can_claim:
        return None, calculate_level(user_obj.xp)

    new_level = add_xp(user_id, XP_DAILY_AMOUNT) # add_xp handles saving
    user_obj.last_daily_claim = datetime.utcnow().isoformat()
    _save(_DATA) # Save again to store the last_daily_claim timestamp
    print(f"\U0001F4B0 {user_id} hat tägliche Belohnung ({XP_DAILY_AMOUNT} XP) erhalten.")
    return XP_DAILY_AMOUNT, new_level


def get_top_users(limit: int) -> Iterable[tuple[int, int]]:
    sorted_items = sorted(_DATA.items(), key=lambda item: item[1].xp, reverse=True)
    for uid, dat in sorted_items[:limit]:
        yield int(uid), dat.xp


def new_day() -> None:
    """Placeholder for daily events or decay."""
    print("\U0001F525 Neuer Tag")
