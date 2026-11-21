"""学年・教科・ジャンルから問題セットを組み立てる。"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Optional

from . import japanese, math
from .base import Question

SUBJECTS: Dict[str, Dict[str, Any]] = {
    "math": {"label": "算数", "topics": math.MATH_TOPICS, "generators": math.GENERATORS},
    "japanese": {"label": "国語", "topics": japanese.JAPANESE_TOPICS, "generators": japanese.GENERATORS},
}
DIFFICULTIES = [("easy", "やさしい"), ("normal", "ふつう"), ("hard", "むずかしい")]


def topics_for(subject: str, grade: int) -> List[Dict[str, str]]:
    entry = SUBJECTS.get(subject)
    if not entry or grade not in entry["topics"]:
        return []
    return [{"key": key, "label": label} for key, label in entry["topics"][grade]]


def config() -> Dict[str, Any]:
    return {
        "grades": [{"value": grade, "label": f"小学{grade}年生"} for grade in range(1, 7)],
        "subjects": [{"key": key, "label": value["label"]} for key, value in SUBJECTS.items()],
        "difficulties": [{"key": key, "label": label} for key, label in DIFFICULTIES],
        "topics": {
            subject: {str(grade): topics_for(subject, grade) for grade in range(1, 7)}
            for subject in SUBJECTS
        },
    }


def generate_quiz(subject: str, grade: int, topics: Optional[List[str]] = None,
                  count: int = 10, difficulty: str = "normal", seed: Optional[int] = None) -> List[Question]:
    entry = SUBJECTS.get(subject)
    if not entry:
        raise ValueError(f"unknown subject: {subject}")
    if grade not in entry["topics"]:
        raise ValueError(f"grade must be 1-6, got: {grade}")
    if difficulty not in dict(DIFFICULTIES):
        raise ValueError(f"unknown difficulty: {difficulty}")

    available = [key for key, _ in entry["topics"][grade]]
    selected = [key for key in (topics or []) if key in available] or available
    rng = random.Random(seed if seed is not None else int(time.time_ns()))

    questions: List[Question] = []
    seen: Dict[str, int] = {}
    attempts = 0
    target = max(1, min(count, 50))
    # 文章問題など選択肢の母数が少ないジャンルは、同じ問題を何度か出してもよい
    max_repeat = 8
    while len(questions) < target and attempts < 2000:
        topic = selected[len(questions) % len(selected)]
        generator = entry["generators"].get(topic)
        if not generator:
            attempts += 1
            continue
        question = generator(rng, grade, difficulty, f"{subject}-{grade}-{len(questions) + 1}")
        if seen.get(question.prompt, 0) >= max_repeat:
            attempts += 1
            continue
        seen[question.prompt] = seen.get(question.prompt, 0) + 1
        questions.append(question)
        attempts += 1
    return questions
