"""農場ゲームの定義（作物・動物・建物・採集スポットと育成計算）。

ルール:
- お金 = 学習アプリで貯めたポイント（wallet）
- 食料・資材 = 農場ゲーム内で貯める資源
- 食料: 農業（作物）・酪農/畜産（どうぶつ）で獲得
- 資材: 付近の森・鉱脈（木材・石・石炭・鉄）で獲得
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any, Dict

# 作物: 種代はポイント(wallet)、収穫で食料を得る
CROPS: Dict[str, Dict[str, Any]] = {
    "cabbage": {"name": "キャベツ", "emoji": "🥬", "cost": 10, "grow": 30, "yield": 8, "resource": "vegetable", "food_type": "野菜"},
    "tomato": {"name": "トマト", "emoji": "🍅", "cost": 20, "grow": 60, "yield": 16, "resource": "vegetable", "food_type": "野菜"},
    "strawberry": {"name": "イチゴ", "emoji": "🍓", "cost": 35, "grow": 120, "yield": 30, "resource": "fruit", "food_type": "くだもの"},
    "sunflower": {"name": "ひまわり", "emoji": "🌻", "cost": 50, "grow": 180, "yield": 45, "resource": "fruit", "food_type": "くだもの"},
}

# どうぶつ: 購入はポイント(wallet)。畑の収穫物を与えると満腹度が上がり、一定以上で食料を生産する
ANIMALS: Dict[str, Dict[str, Any]] = {
    "chicken": {"name": "にわとり", "emoji": "🐔", "cost": 80,
                "product": "たまご", "product_emoji": "🥚", "yield": 10, "resource": "egg",
                "fullness_need": 60, "favorite_food": ["vegetable", "fruit"]},
    "rabbit": {"name": "うさぎ", "emoji": "🐰", "cost": 140,
               "product": "にんじん", "product_emoji": "🥕", "yield": 18, "resource": "carrot",
               "fullness_need": 70, "favorite_food": ["vegetable", "carrot"]},
    "cow": {"name": "うし", "emoji": "🐄", "cost": 300,
            "product": "ミルク", "product_emoji": "🥛", "yield": 35, "resource": "milk",
            "fullness_need": 80, "favorite_food": ["vegetable", "fruit"]},
}

ANIMAL_PERSONALITIES: Dict[str, Dict[str, Any]] = {
    "genki": {"name": "元気", "emoji": "✨", "description": "いつも 元気いっぱい。ときどき おまけを くれる"},
    "otonashii": {"name": "おとなしい", "emoji": "🌸", "description": "おだやかで なつきやすい。きずなが 育ちやすい"},
    "kuishinbo": {"name": "くいしんぼう", "emoji": "🍽️", "description": "ごはんが 大好き。食料イベントが 起きやすい"},
    "nonbiri": {"name": "のんびり", "emoji": "☁️", "description": "マイペース。ゆっくり 仲良く なれる"},
    "nakayoshi": {"name": "なかよし", "emoji": "💛", "description": "人なつっこい。お世話イベントが 起きやすい"},
}

ANIMAL_NICKNAMES = [
    "モモ", "ココ", "ソラ", "ミルク", "ハナ", "マル", "ポチ", "チロ", "ルナ", "ピコ",
    "ふわり", "ころん", "ぽんた", "きなこ", "みかん", "すず", "こむぎ", "そらまめ",
]


# 建物: ポイントと資材で建設する
BUILDINGS: Dict[str, Dict[str, Any]] = {
    "barn": {"name": "こや", "emoji": "🏠", "cost": {"points": 200, "wood": 15}, "description": "農場が にぎやかに なる"},
    "pond": {"name": "いけ", "emoji": "💧", "cost": {"points": 350, "stone": 20}, "description": "みずが たまって きれい"},
    "windmill": {"name": "かざぐるま", "emoji": "🌬️", "cost": {"points": 500, "wood": 20, "iron": 5}, "description": "かぜで くるくる まわります"},
}

# 道具: 資材とポイントで入手。次のグレードの道具や動作を解放する
TOOLS: Dict[str, Dict[str, Any]] = {
    "axe": {
        "name": "オノ", "emoji": "🪓", "grade": 1, "prereq": None,
        "cost": {"points": 100, "wood": 5, "stone": 2},
        "description": "木を うまく 切れる。森で 追加の木材を 集められる。",
        "unlocks": ["chop_bonus"],
        "unlock_label": "木材ボーナス採集",
    },
    "pickaxe": {
        "name": "ツルハシ", "emoji": "⛏️", "grade": 1, "prereq": None,
        "cost": {"points": 120, "wood": 5, "stone": 5},
        "description": "石炭こうみゃくで 採掘できるようになる。",
        "unlocks": ["mine_coal"],
        "unlock_label": "石炭こうみゃく採掘",
    },
    "watering_can": {
        "name": "ジョウロ", "emoji": "🪣", "grade": 1, "prereq": None,
        "cost": {"points": 80, "wood": 8},
        "description": "畑に水をやって、作物の成長を早められる。",
        "unlocks": ["water_crop"],
        "unlock_label": "作物に水やり",
    },
    "steel_pickaxe": {
        "name": "鋼のツルハシ", "emoji": "⚒️", "grade": 2, "prereq": "pickaxe",
        "cost": {"points": 250, "iron": 5, "wood": 10},
        "description": "鉄こうみゃくで 採掘できるようになる。",
        "unlocks": ["mine_iron"],
        "unlock_label": "鉄こうみゃく採掘",
    },
    "hammer": {
        "name": "ハンマー", "emoji": "🔨", "grade": 2, "prereq": "axe",
        "cost": {"points": 220, "iron": 4, "wood": 8},
        "description": "丈夫な工作ができる。採集した資材を まとめて 加工できる。",
        "unlocks": ["craft_bundle"],
        "unlock_label": "資材加工",
    },
}

# 働き手候補: 学習イベントで出会い、牧場で雇用できる
WORKER_CANDIDATES: Dict[str, Dict[str, Any]] = {
    "taro": {
        "name": "タロウ", "emoji": "👨‍🌾", "role": "農夫",
        "description": "畑の手伝いが得意。野菜を育ててくれる。",
        "hire_cost": {"points": 120, "vegetable": 10},
        "work_interval": 120, "yield": {"vegetable": 12},
        "encounter": {"type": "correct_streak", "value": 5, "text": "畑仕事が得意な タロウ と出会った！"},
    },
    "hana": {
        "name": "ハナ", "emoji": "👩‍🌾", "role": "酪農家",
        "description": "どうぶつの世話が上手。たまごやミルクを集めてくれる。",
        "hire_cost": {"points": 150, "carrot": 8, "wood": 5},
        "work_interval": 150, "yield": {"egg": 8, "milk": 6},
        "encounter": {"type": "total_correct", "value": 30, "text": "どうぶつ好きの ハナ と出会った！"},
    },
    "ken": {
        "name": "ケン", "emoji": "🪓", "role": "木こり",
        "description": "森で木材を集めるのが速い。",
        "hire_cost": {"points": 140, "wood": 5},
        "work_interval": 140, "yield": {"wood": 10},
        "encounter": {"type": "random_correct", "chance": 0.08, "text": "森の近くで 木こりの ケン と出会った！"},
    },
    "mina": {
        "name": "ミナ", "emoji": "⛏️", "role": "鉱夫",
        "description": "こうみゃくで石や石炭を掘ってくれる。",
        "hire_cost": {"points": 180, "stone": 4},
        "work_interval": 180, "yield": {"stone": 6, "coal": 3},
        "encounter": {"type": "total_answered", "value": 50, "text": "こうみゃくを調べていた ミナ と出会った！"},
    },
    "sora": {
        "name": "ソラ", "emoji": "🔧", "role": "整備士",
        "description": "機械の修理が得意。鉄を見つけてくれる。",
        "hire_cost": {"points": 220, "iron": 2, "wood": 4},
        "work_interval": 210, "yield": {"iron": 4, "stone": 2},
        "encounter": {"type": "random_correct", "chance": 0.04, "text": "旅する整備士 ソラ と出会った！"},
    },
}


# 採集スポット: 時間がたつと資材を集められる（農場内で資材を貯める）
GATHER_SPOTS: Dict[str, Dict[str, Any]] = {
    "forest": {"name": "もり", "emoji": "🌲", "resource": "wood", "resource_name": "木材",
               "interval": 45, "yield": 6, "description": "木を きって 木材を 集める", "required_tool": None},
    "quarry": {"name": "いしきりば", "emoji": "🪨", "resource": "stone", "resource_name": "石",
               "interval": 60, "yield": 5, "description": "石を ほって 石材を 集める", "required_tool": None},
    "coal_mine": {"name": "石炭こうみゃく", "emoji": "⛏️", "resource": "coal", "resource_name": "石炭",
                  "interval": 90, "yield": 4, "description": "石炭こうみゃくで 石炭を 掘る", "required_tool": "pickaxe"},
    "iron_mine": {"name": "鉄こうみゃく", "emoji": "🔩", "resource": "iron", "resource_name": "鉄",
                  "interval": 120, "yield": 3, "description": "鉄こうみゃくで 鉄を 掘る", "required_tool": "steel_pickaxe"},
}

RESOURCE_META: Dict[str, Dict[str, Any]] = {
    "vegetable": {"name": "野菜", "emoji": "🥬", "category": "food", "feed_value": 2, "eat_value": 12},
    "fruit": {"name": "くだもの", "emoji": "🍓", "category": "food", "feed_value": 2, "eat_value": 10},
    "egg": {"name": "たまご", "emoji": "🥚", "category": "food", "feed_value": 1, "eat_value": 15},
    "milk": {"name": "ミルク", "emoji": "🥛", "category": "food", "feed_value": 1, "eat_value": 14},
    "carrot": {"name": "にんじん", "emoji": "🥕", "category": "food", "feed_value": 2, "eat_value": 8},
    "feed": {"name": "飼料", "emoji": "🌾", "category": "food", "feed_value": 0, "eat_value": 4},
    "wood": {"name": "木材", "emoji": "🪵", "category": "material", "feed_value": 0, "eat_value": 0},
    "stone": {"name": "石", "emoji": "🪨", "category": "material", "feed_value": 0, "eat_value": 0},
    "coal": {"name": "石炭", "emoji": "⚫", "category": "material", "feed_value": 0, "eat_value": 0},
    "iron": {"name": "鉄", "emoji": "🔩", "category": "material", "feed_value": 0, "eat_value": 0},
}

# 主人公の空腹度: 時間で上がる。食べ物で下げる。
HUNGER_MAX = 100
HUNGER_INTERVAL_SECONDS = 120  # この秒数ごとに+1
HUNGER_WARNING = 70
HUNGER_STARVING = 100
HUNGER_PENALTY_POINTS_PER_TICK = 2  # 満腹度が限界を超えて放置された時のポイント減少

# どうぶつ: 畑の収穫物を与えると満腹度が上がり、一定以上で食料を生産
ANIMAL_FULLNESS_MAX = 100
ANIMAL_FULLNESS_DECAY_PER_HOUR = 8  # 放置で減る（さぼると赤字）
ANIMAL_PRODUCE_THRESHOLD = 80

ANIMAL_EVENTS = [
    {"key": "bonus_food", "name": "おまけ", "message": "{nickname} が うれしそう！ {product} を おまけで {bonus} こ くれたよ。", "bonus": 3, "bond": 1, "weight": 18},
    {"key": "big_bonus", "name": "大サービス", "message": "{nickname} は きょう とっても ごきげん！ {product} が {bonus} こ 多かった！", "bonus": 6, "bond": 2, "weight": 8},
    {"key": "bond_up", "name": "なついた", "message": "{nickname} が あなたに なついた！ きずなが ふかまったよ。", "bonus": 0, "bond": 2, "weight": 14},
    {"key": "play", "name": "あそんだ", "message": "{nickname} と いっしょに あそんだ。{nickname} は にこにこ！", "bonus": 0, "bond": 1, "weight": 14},
    {"key": "normal", "name": "いつもどおり", "message": "{nickname} は げんきに {product} を とらせてくれたよ。", "bonus": 0, "bond": 1, "weight": 46},
]


def pick_personality(rng: random.Random) -> str:
    return rng.choice(list(ANIMAL_PERSONALITIES.keys()))


def pick_nickname(rng: random.Random, existing: set[str] | None = None) -> str:
    existing = existing or set()
    candidates = [name for name in ANIMAL_NICKNAMES if name not in existing]
    if candidates:
        return rng.choice(candidates)
    return rng.choice(ANIMAL_NICKNAMES)


def roll_animal_event(animal: Dict[str, Any], personality_key: str, bond: int, rng: random.Random) -> Dict[str, Any]:
    personality = ANIMAL_PERSONALITIES.get(personality_key, {})
    weights = []
    for event in ANIMAL_EVENTS:
        weight = event["weight"]
        if personality_key == "genki" and event["bonus"] > 0:
            weight += 8
        if personality_key == "kuishinbo" and event["key"] == "bonus_food":
            weight += 10
        if personality_key == "nakayoshi" and event["bond"] >= 2:
            weight += 8
        if personality_key == "otonashii" and event["key"] == "bond_up":
            weight += 6
        if bond >= 10 and event["bonus"] > 0:
            weight += 4
        weights.append(weight)
    chosen = rng.choices(ANIMAL_EVENTS, weights=weights, k=1)[0]
    bonus = chosen["bonus"]
    if bonus and personality_key == "genki":
        bonus += 1
    message = chosen["message"].format(
        nickname=animal.get("nickname", animal.get("name", "どうぶつ")),
        product=animal.get("product", "たべもの"),
        bonus=bonus,
    )
    return {
        "key": chosen["key"],
        "name": chosen["name"],
        "message": message,
        "bonus_yield": bonus,
        "bond_gain": chosen["bond"],
        "personality": personality.get("name", ""),
    }


MAX_PLOTS = 18
PLOTS_PER_ROW = 3
PLOT_EXPANSION_COST = 150


def catalog() -> Dict[str, Any]:
    return {
        "crops": [{"key": key, **value} for key, value in CROPS.items()],
        "animals": [{"key": key, **value} for key, value in ANIMALS.items()],
        "buildings": [{"key": key, **value} for key, value in BUILDINGS.items()],
        "tools": [{"key": key, **value} for key, value in TOOLS.items()],
        "gather_spots": [{"key": key, **value} for key, value in GATHER_SPOTS.items()],
        "resources": [{"key": key, **value} for key, value in RESOURCE_META.items()],
        "personalities": [{"key": key, **value} for key, value in ANIMAL_PERSONALITIES.items()],
        "workers": [{"key": key, **value} for key, value in WORKER_CANDIDATES.items()],
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
