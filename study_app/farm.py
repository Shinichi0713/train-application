"""農場ゲームの定義（作物・動物・建物と育成計算）。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

CROPS: Dict[str, Dict[str, Any]] = {
    "cabbage": {"name": "キャベツ", "emoji": "🥬", "cost": 10, "grow": 30, "sell": 20},
    "tomato": {"name": "トマト", "emoji": "🍅", "cost": 20, "grow": 60, "sell": 45},
    "strawberry": {"name": "イチゴ", "emoji": "🍓", "cost": 35, "grow": 120, "sell": 85},
    "sunflower": {"name": "ひまわり", "emoji": "🌻", "cost": 50, "grow": 180, "sell": 130},
}

ANIMALS: Dict[str, Dict[str, Any]] = {
    "chicken": {"name": "にわとり", "emoji": "🐔", "cost": 80, "interval": 90,
                "product": "たまご", "product_emoji": "🥚", "sell": 25},
    "rabbit": {"name": "うさぎ", "emoji": "🐰", "cost": 140, "interval": 150,
               "product": "にんじん", "product_emoji": "🥕", "sell": 50},
    "cow": {"name": "うし", "emoji": "🐄", "cost": 300, "interval": 240,
            "product": "ぎゅうにゅう", "product_emoji": "🥛", "sell": 95},
}

BUILDINGS: Dict[str, Dict[str, Any]] = {
    "barn": {"name": "こや", "emoji": "🏠", "cost": 200, "description": "農場が にぎやかに なる"},
    "pond": {"name": "いけ", "emoji": "💧", "cost": 350, "description": "みずが たまって きれい"},
    "windmill": {"name": "かざぐるま", "emoji": "🌬️", "cost": 500, "description": "かぜで くるくる まわります"},
}

MAX_PLOTS = 18
PLOTS_PER_ROW = 3
PLOT_EXPANSION_COST = 150


def catalog() -> Dict[str, Any]:
    return {
        "crops": [{"key": key, **value} for key, value in CROPS.items()],
        "animals": [{"key": key, **value} for key, value in ANIMALS.items()],
        "buildings": [{"key": key, **value} for key, value in BUILDINGS.items()],
        "plot_expansion_cost": PLOT_EXPANSION_COST,
        "max_plots": MAX_PLOTS,
    }


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def remaining_seconds(target_iso: str) -> int:
    try:
        target = datetime.fromisoformat(target_iso)
    except (TypeError, ValueError):
        return 0
    return max(0, int((target - datetime.now()).total_seconds()))


def growth_info(started_iso: str, grow_seconds: int) -> Dict[str, Any]:
    try:
        started = datetime.fromisoformat(started_iso)
    except (TypeError, ValueError):
        started = datetime.now()
    elapsed = max(0.0, (datetime.now() - started).total_seconds())
    progress = min(1.0, elapsed / grow_seconds) if grow_seconds else 1.0
    return {
        "ready": progress >= 1.0,
        "progress": round(progress, 3),
        "remaining": max(0, int(grow_seconds - elapsed)),
        "ready_at": (started + timedelta(seconds=grow_seconds)).isoformat(timespec="seconds"),
    }


def farm_level(exp: int) -> int:
    return exp // 100 + 1
