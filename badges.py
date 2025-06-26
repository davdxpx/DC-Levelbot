"""Badge management module."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

BADGES_PATH = Path("badges_data.json")
STATS_PATH = Path("badge_stats.json")


@dataclass
class BadgeDefinition:
    """Static badge information."""

    name: str
    description: str
    icon: str
    condition: dict[str, int]


BADGE_DEFINITIONS: Dict[str, BadgeDefinition] = {
    "chatterbox": BadgeDefinition(
        name="Plaudertasche",
        description="1000 Nachrichten gesendet",
        icon="\U0001f4ac",
        condition={"messages": 1000},
    ),
    "reaction_master": BadgeDefinition(
        name="Reaktionsk\u00f6nig",
        description="500 Reaktionen vergeben",
        icon="\U0001f44d",
        condition={"reactions_given": 500},
    ),
    "community_favorite": BadgeDefinition(
        name="Community-Liebling",
        description="100 Reaktionen auf eigene Beitr\u00e4ge erhalten",
        icon="\u2764\ufe0f",
        condition={"reactions_received": 100},
    ),
    "veteran": BadgeDefinition(
        name="Veteran",
        description="Seit einem Jahr Mitglied",
        icon="\U0001f396\ufe0f",
        condition={"days_member": 365},
    ),
}

_BADGE_DATA: Dict[str, List[str]] = {}
_STATS: Dict[str, dict] = {}


def _load(path: Path) -> dict:
    if path.exists():
        print(f"\U0001F4C2 Lade {path.name}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    return {}


def _save(path: Path, data: dict) -> None:
    print(f"\U0001F4BE Speichere {path.name}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


_BADGE_DATA = _load(BADGES_PATH)
_STATS = _load(STATS_PATH)


def _ensure_user(user_id: int) -> None:
    uid = str(user_id)
    if uid not in _STATS:
        _STATS[uid] = {
            "messages": 0,
            "reactions_given": 0,
            "reactions_received": 0,
            "join_date": datetime.utcnow().isoformat(),
        }
        _save(STATS_PATH, _STATS)
        print(f"\U0001F195 Neuer Nutzer {uid} angelegt")
    if uid not in _BADGE_DATA:
        _BADGE_DATA[uid] = []
        _save(BADGES_PATH, _BADGE_DATA)


def _check_badges(user_id: int) -> List[str]:
    """Check if user earned new badges and return their IDs."""
    uid = str(user_id)
    stats = _STATS.get(uid, {})
    earned = set(_BADGE_DATA.get(uid, []))
    newly_earned: List[str] = []
    for bid, badge in BADGE_DEFINITIONS.items():
        if bid in earned:
            continue
        cond = badge.condition
        if "messages" in cond and stats.get("messages", 0) >= cond["messages"]:
            newly_earned.append(bid)
        elif "reactions_given" in cond and stats.get("reactions_given", 0) >= cond["reactions_given"]:
            newly_earned.append(bid)
        elif "reactions_received" in cond and stats.get("reactions_received", 0) >= cond["reactions_received"]:
            newly_earned.append(bid)
        elif "days_member" in cond:
            join = datetime.fromisoformat(stats.get("join_date"))
            if datetime.utcnow() - join >= timedelta(days=cond["days_member"]):
                newly_earned.append(bid)
    if newly_earned:
        _BADGE_DATA[uid] = sorted(earned | set(newly_earned))
        _save(BADGES_PATH, _BADGE_DATA)
        for nb in newly_earned:
            print(f"\U0001F396 Badge verliehen: {BADGE_DEFINITIONS[nb].name}")
    return newly_earned


def increment_messages(user_id: int) -> List[str]:
    _ensure_user(user_id)
    _STATS[str(user_id)]["messages"] += 1
    _save(STATS_PATH, _STATS)
    print(f"\U0001F4AC Nachrichtenzähler für {user_id}")
    return _check_badges(user_id)


def increment_reaction_given(user_id: int) -> List[str]:
    _ensure_user(user_id)
    _STATS[str(user_id)]["reactions_given"] += 1
    _save(STATS_PATH, _STATS)
    print(f"\U0001F44D Reaktionen vergeben von {user_id}")
    return _check_badges(user_id)


def increment_reaction_received(user_id: int) -> List[str]:
    _ensure_user(user_id)
    _STATS[str(user_id)]["reactions_received"] += 1
    _save(STATS_PATH, _STATS)
    print(f"\u2764\ufe0f Reaktionen erhalten für {user_id}")
    return _check_badges(user_id)


def get_user_badges(user_id: int) -> List[str]:
    _ensure_user(user_id)
    badges_list = list(_BADGE_DATA.get(str(user_id), []))
    print(f"\U0001F3AB Abzeichen für {user_id}: {len(badges_list)}")
    return badges_list
