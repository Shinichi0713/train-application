"""農場ゲームの定義（作物・動物・建物・採集スポットと育成計算）。

ルール:
- お金 = 学習アプリで貯めたポイント（wallet）
- 食料・資材 = 農場ゲーム内で貯める資源
- 食料: 農業（作物）・酪農/畜産（どうぶつ）で獲得
- 資材: 付近の森・鉱脈（木材・石・石炭・鉄）で獲得
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

# 作物: 種代はポイント(wallet)、収穫で食料を得る
CROPS: Dict[str, Dict[str, Any]] = {
    "cabbage": {"name": "キャベツ", "emoji": "🥬", "cost": 10, "grow": 30, "yield": 8, "resource": "food"},
    "tomato": {"name": "トマト", "emoji": "🍅", "cost": 20, "grow": 60, "yield": 16, "resource": "food"},
    "strawberry": {"name": "イチゴ", "emoji": "🍓", "cost": 35, "grow": 120, "yield": 30, "resource": "food"},
    "sunflower": {"name": "ひまわり", "emoji": "🌻", "cost": 50, "grow": 180, "yield": 45, "resource": "food"},
}

# どうぶつ: 購入はポイント(wallet)、一定時間ごとに食料を得る
ANIMALS: Dict[str, Dict[str, Any]] = {
    "chicken": {"name": "にわとり", "emoji": "🐔", "cost": 80, "interval": 90,
                "product": "たまご", "product_emoji": "🥚", "yield": 10, "resource": "food"},
    "rabbit": {"name": "うさぎ", "emoji": "🐰", "cost": 140, "interval": 150,
               "product": "にんじん", "product_emoji": "🥕", "yield": 18, "resource": "food"},
    "cow": {"name": "うし", "emoji": "🐄", "cost": 300, "interval": 240,
            "product": "ぎゅうにゅう", "product_emoji": "🥛", "yield": 35, "resource": "food"},
}

# 建物: 購入はポイント(wallet)。農場の見た目と達成感のための要素
BUILDINGS: Dict[str, Dict[str, Any]] = {
    "barn": {"name": "こや", "emoji": "🏠", "cost": 200, "description": "農場が にぎやかに なる"},
    "pond": {"name": "いけ", "emoji": "💧", "cost": 350, "description": "みずが たまって きれい"},
    "windmill": {"name": "かざぐるま", "emoji": "🌬️", "cost": 500, "description": "かぜで くるくる まわります"},
}

# 採集スポット: 時間がたつと資材を集められる（農場内で資材を貯める）
GATHER_SPOTS: Dict[str, Dict[str, Any]] = {
    "forest": {"name": "もり", "emoji": "🌲", "resource": "wood", "resource_name": "木材",
               "interval": 45, "yield": 6, "description": "木を きって 木材を 集める"},
    "quarry": {"name": "いしきりば", "emoji": "🪨", "resource": "stone", "resource_name": "石",
               "interval": 60, "yield": 5, "description": "石を ほって 石材を 集める"},
    "coal_mine": {"name": "石炭こうみゃく", "emoji": "⛏️", "resource": "coal", "resource_name": "石炭",
                  "interval": 90, "yield": 4, "description": "石炭こうみゃくで 石炭を 掘る"},
    "iron_mine": {"name": "鉄こうみゃく", "emoji": "🔩", "resource": "iron", "resource_name": "鉄",
                  "interval": 120, "yield": 3, "description": "鉄こうみゃくで 鉄を 掘る"},
}

RESOURCE_META: Dict[str, Dict[str, str]] = {
    "food": {"name": "食料", "emoji": "🍚"},
    "wood": {"name": "木材", "emoji": "🪵"},
    "stone": {"name": "石", "emoji": "🪨"},
    "coal": {"name": "石炭", "emoji": "⚫"},
    "iron": {"name": "鉄", "emoji": "🔩"},
}

MAX_PLOTS = 18
PLOTS_PER_ROW = 3
PLOT_EXPANSION_COST = 150


def catalog() -> Dict[str, Any]:
    return {
        "crops": [{"key": key, **value} for key, value in CROPS.items()],
        "animals": [{"key": key, **value} for key, value in ANIMALS.items()],
        "buildings": [{"key": key, **value} for key, value in BUILDINGS.items()],
        "gather_spots": [{"key": key, **value} for key, value in GATHER_SPOTS.items()],
        "resources": [{"key": key, **value} for key, value in RESOURCE_META.items()],
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
