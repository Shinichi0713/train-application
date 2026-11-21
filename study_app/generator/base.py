"""問題データ構造と共通ユーティリティ。"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, Dict, List, Optional


@dataclass
class Question:
    id: str
    subject: str
    grade: int
    topic: str
    prompt: str
    answer: str
    explanation: str
    choices: List[str] = field(default_factory=list)
    passage: Optional[str] = None

    def public(self) -> Dict[str, Any]:
        """正解を漏らさずにクライアントへ渡す形。"""
        return {
            "id": self.id,
            "subject": self.subject,
            "grade": self.grade,
            "topic": self.topic,
            "prompt": self.prompt,
            "choices": self.choices,
            "passage": self.passage,
        }


_UNITS = ("パーセント", "cm2", "cm3", "cm²", "cm³", "kg", "g", "ml", "L",
          "cm", "m", "こ", "個", "円", "度", "分", "%")


def normalize_answer(value: Any) -> str:
    """全角半角・空白・単位の表記ゆれを吸収する。"""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = text.replace(" ", "").replace("\u3000", "")
    text = text.rstrip("。.")
    for unit in _UNITS:
        if text.endswith(unit) and len(text) > len(unit):
            text = text[: -len(unit)]
            break
    return text.lower()


def answers_match(given: Any, correct: Any) -> bool:
    """文字列・数値・分数のいずれの表記でも正誤を判定する。"""
    left, right = normalize_answer(given), normalize_answer(correct)
    if left == right:
        return True
    for pair in ((left, right), (left.replace("/", ""), right.replace("/", ""))):
        try:
            if float(pair[0]) == float(pair[1]):
                return True
        except (ValueError, ZeroDivisionError):
            pass
    try:
        return Fraction(left) == Fraction(right)
    except (ValueError, ZeroDivisionError):
        return False


def fmt_number(value: Any) -> str:
    """小数の末尾ゼロを消した読みやすい表記。"""
    text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def fmt_fraction(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def pick_choices(rng, correct: str, wrong_candidates: List[str], size: int = 4) -> List[str]:
    """正解を必ず含む選択肢を作る。"""
    wrong = []
    for candidate in wrong_candidates:
        value = str(candidate)
        if normalize_answer(value) != normalize_answer(correct) and value not in wrong:
            wrong.append(value)
    rng.shuffle(wrong)
    choices = [correct] + wrong[: max(0, size - 1)]
    rng.shuffle(choices)
    return choices
