"""パス設定とデータ読み込み。"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
KANJI_PATH = DATA_DIR / "kanji-1026.json"
DB_PATH = Path(os.environ.get("STUDY_DB_PATH", str(DATA_DIR / "progress.sqlite3")))

_SUB = str.maketrans("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン",
                    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん")


def to_hiragana(text: str) -> str:
    """カタカナをひらがなに寄せる（読みの比較用）。"""
    return text.translate(_SUB)


def clean_reading(raw: str) -> List[str]:
    """「ひと（つ）」のような送りがなを除き、読みの候補を返す。"""
    if not raw:
        return []
    body = re.sub(r"[（(].*?[)）]", "", raw)
    parts = re.split(r"[・、／/]", body)
    result = []
    for part in parts:
        value = to_hiragana(part).strip()
        # データセット中の「なし」は「訓読みなし」を示すプレースホルダーなので除外
        if value and value != "なし" and re.fullmatch(r"[ぁ-んー]+", value):
            result.append(value)
    return result


@lru_cache(maxsize=1)
def load_kanji() -> List[dict]:
    with KANJI_PATH.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    items = []
    for entry in payload["kanji"]:
        readings = clean_reading(entry.get("kun", "")) + clean_reading(entry.get("on", ""))
        # 「梨」だけは「なし」が正しい訓読み（プレースホルダーではない）
        if not readings and entry["char"] == "梨":
            readings = ["なし"]
        strokes = int(entry["strokes"]) if str(entry["strokes"]).isdigit() else 0
        items.append({
            "char": entry["char"],
            "grade": int(entry["grade"]),
            "strokes": strokes,
            "radical": entry.get("radical", ""),
            "readings": list(dict.fromkeys(readings)),
        })
    return items


@lru_cache(maxsize=1)
def kanji_by_grade() -> Dict[int, List[dict]]:
    grouped: Dict[int, List[dict]] = {grade: [] for grade in range(1, 7)}
    for item in load_kanji():
        if item["grade"] in grouped:
            grouped[item["grade"]].append(item)
    return grouped
