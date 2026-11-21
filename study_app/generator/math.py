"""算数の問題自動生成（小学1〜6年）。"""
from __future__ import annotations

import random
from fractions import Fraction
from typing import Callable, List

from .base import Question, fmt_fraction, fmt_number, pick_choices

Generator = Callable[[random.Random, int, str, str], Question]

_DIFFICULTY = {"easy": 0.55, "normal": 1.0, "hard": 1.6}


def _limit(grade: int, difficulty: str, base: int) -> int:
    return max(2, int(base * _DIFFICULTY.get(difficulty, 1.0)))


def _number_choices(rng: random.Random, correct: int, spread: int = 5) -> List[str]:
    candidates = [correct + rng.randint(-spread, spread) for _ in range(10)]
    candidates += [correct * 2, max(0, correct // 2)]
    return pick_choices(rng, str(correct), [str(c) for c in candidates if c >= 0])


def gen_calc_add(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    top = 10 if grade == 1 else _limit(grade, difficulty, {2: 100, 3: 1000, 4: 10000, 5: 10000, 6: 10000}[grade])
    a, b = rng.randint(1, top), rng.randint(1, top)
    return Question(qid, "算数", grade, "calc_add", f"{a} + {b} はいくつ？", str(a + b),
                    f"{a} と {b} を合わせると {a + b} です。")


def gen_calc_sub(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    top = 10 if grade == 1 else _limit(grade, difficulty, {2: 100, 3: 1000, 4: 10000, 5: 10000, 6: 10000}[grade])
    a = rng.randint(2, top)
    b = rng.randint(1, a)
    return Question(qid, "算数", grade, "calc_sub", f"{a} − {b} はいくつ？", str(a - b),
                    f"{a} から {b} を引くと {a - b} です。")


def gen_compare(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    top = _limit(grade, difficulty, {1: 10, 2: 100, 3: 1000, 4: 10000, 5: 10000, 6: 10000}[grade])
    a, b = rng.sample(range(1, top + 1), 2)
    correct = str(max(a, b))
    return Question(qid, "算数", grade, "compare", f"大きい数はどちら？　{a}　と　{b}",
                    correct, f"{max(a, b)} のほうが {min(a, b)} より大きいです。",
                    pick_choices(rng, correct, [str(a), str(b), str(min(a, b) - 1)]))


def gen_make_ten(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    a = rng.randint(1, 9)
    answer = 10 - a
    return Question(qid, "算数", grade, "make_ten", f"10 にするには、{a} にいくつを足しますか？",
                    str(answer), f"{a} + {answer} = 10 です。")


def gen_count_shapes(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    shapes = ["○", "△", "□"]
    counts = [rng.randint(1, 5) for _ in shapes]
    question = "、".join(f"{shape} が {count} つ" for shape, count in zip(shapes, counts))
    return Question(qid, "算数", grade, "count_shapes", f"{question}あります。全部でいくつ？",
                    str(sum(counts)), f"{' + '.join(map(str, counts))} = {sum(counts)} です。")


def gen_multiplication(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    if difficulty == "easy" or grade <= 2:
        a, b = rng.randint(1, 5), rng.randint(1, 5)
    elif difficulty == "hard" and grade >= 4:
        a, b = rng.randint(11, 99), rng.randint(2, 9)
    else:
        a, b = rng.randint(1, 9), rng.randint(1, 9)
    return Question(qid, "算数", grade, "multiplication", f"{a} × {b} はいくつ？", str(a * b),
                    f"{a} を {b} つ分足すと {a * b} です。")


def gen_division(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    divisor = rng.randint(2, 12 if grade >= 3 else 9)
    quotient = rng.randint(2, 12 if difficulty == "hard" else 9)
    dividend = divisor * quotient
    return Question(qid, "算数", grade, "division", f"{dividend} ÷ {divisor} はいくつ？", str(quotient),
                    f"{divisor} × {quotient} = {dividend} なので、答えは {quotient} です。")


def gen_units(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    pairs = [
        ("1 m は何 cm？", 100, "1 m = 100 cm です。"),
        ("1 km は何 m？", 1000, "1 km = 1000 m です。"),
        ("1 kg は何 g？", 1000, "1 kg = 1000 g です。"),
        ("1 L は何 ml？", 1000, "1 L = 1000 ml です。"),
        ("1 時間は何分？", 60, "1 時間 = 60 分です。"),
        ("1 分は何秒？", 60, "1 分 = 60 秒です。"),
    ]
    prompt, value, note = rng.choice(pairs)
    return Question(qid, "算数", grade, "units", prompt, str(value), note, _number_choices(rng, value, 50))


def gen_clock(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    hour = rng.randint(1, 12)
    minute = rng.choice([0, 15, 30, 45] if difficulty == "easy" else [i * 5 for i in range(12)])
    correct = f"{hour}時{minute}分"
    marker = 12 if minute == 0 else minute // 5
    wrong = [f"{hour}時{(minute + 5) % 60}分", f"{(hour % 12) + 1}時{minute}分", f"{hour}時{(minute + 30) % 60}分"]
    return Question(qid, "算数", grade, "clock",
                    f"短い針が {hour}、長い針が {marker} を指しています。何時何分？",
                    correct, f"短い針が {hour}、長い針が {marker} なので {correct} です。",
                    pick_choices(rng, correct, wrong))


def gen_fraction_basic(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    den = rng.choice([2, 3, 4, 5, 6, 8])
    a, b = rng.randint(1, den - 1), rng.randint(1, den - 1)
    if a + b > den:
        a, b = min(a, den - b), b
    op, left, right = rng.choice([
        ("+", Fraction(a, den), Fraction(b, den)),
        ("−", Fraction(max(a, b), den), Fraction(min(a, b), den)),
    ])
    result = left + right if op == "+" else left - right
    answer = fmt_fraction(result)
    return Question(qid, "算数", grade, "fraction_basic",
                    f"{fmt_fraction(left)} {op} {fmt_fraction(right)} はいくつ？", answer,
                    f"分母が同じなので、分子をそのまま{'足し' if op == '+' else '引き'}、約分すると {answer} です。")


def gen_decimal_basic(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    places = 10 if difficulty != "hard" else 100
    a, b = rng.randint(1, 9 * places), rng.randint(1, 9 * places)
    op = rng.choice(["+", "−"])
    if op == "−" and a < b:
        a, b = b, a
    left, right = a / places, b / places
    result = left + right if op == "+" else left - right
    digits = 1 if places == 10 else 2
    shown_left, shown_right, answer = f"{left:.{digits}f}", f"{right:.{digits}f}", f"{result:.{digits}f}"
    return Question(qid, "算数", grade, "decimal_basic", f"{shown_left} {op} {shown_right} はいくつ？",
                    answer, f"{shown_left} {op} {shown_right} = {answer} です。")


def _gen_shape(rng: random.Random, grade: int, difficulty: str, qid: str, topic: str) -> Question:
    width, height = rng.randint(2, 12), rng.randint(2, 12)
    if topic == "shape_perimeter":
        answer = (width + height) * 2
        prompt = f"たて {height} cm、よこ {width} cm の長方形のまわりの長さは何 cm？"
        note = f"({height} + {width}) × 2 = {answer} cm です。"
    else:
        answer = width * height
        prompt = f"たて {height} cm、よこ {width} cm の長方形の面積は何 cm²？"
        note = f"{height} × {width} = {answer} cm² です。"
    q = Question(qid, "算数", grade, topic, prompt, str(answer), note)
    q.choices = _number_choices(rng, answer, 6)
    return q


def gen_shape_perimeter(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    return _gen_shape(rng, grade, difficulty, qid, "shape_perimeter")


def gen_shape_area(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    return _gen_shape(rng, grade, difficulty, qid, "shape_area")


def gen_four_ops(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    a, b, c = rng.randint(2, 20), rng.randint(2, 9), rng.randint(2, 9)
    answer = a + b * c
    return Question(qid, "算数", grade, "four_ops", f"{a} + {b} × {c} はいくつ？", str(answer),
                    f"かけ算を先に計算します。{b} × {c} = {b * c}、{a} + {b * c} = {answer} です。")


def gen_angle(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    kind = rng.choice(["triangle", "right", "quad"])
    if kind == "triangle":
        a, b = rng.randint(20, 80), rng.randint(20, 80)
        answer = 180 - a - b
        prompt, note = f"三角形の2つの角が {a}° と {b}° です。残りの角は何度？", "三角形の内角の和は180°です。"
    elif kind == "right":
        a = rng.randint(15, 70)
        answer = 90 - a
        prompt, note = f"直角三角形の一方の鋭角が {a}° です。もう一方は何度？", "直角三角形の鋭角の和は90°です。"
    else:
        a, b, c = rng.randint(60, 110), rng.randint(60, 110), rng.randint(60, 110)
        answer = 360 - a - b - c
        prompt, note = f"四角形の3つの角が {a}°、{b}°、{c}° です。残りの角は何度？", "四角形の内角の和は360°です。"
    q = Question(qid, "算数", grade, "angle", prompt, str(answer), f"{note} 答えは {answer}° です。")
    q.choices = _number_choices(rng, answer, 10)
    return q


def gen_fraction_muldiv(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    a = Fraction(rng.randint(1, 5), rng.randint(2, 6))
    b = Fraction(rng.randint(1, 5), rng.randint(2, 6))
    if rng.choice([True, False]):
        result, op = a * b, "×"
    else:
        result, op = a / b, "÷"
    answer = fmt_fraction(result)
    return Question(qid, "算数", grade, "fraction_muldiv",
                    f"{fmt_fraction(a)} {op} {fmt_fraction(b)} はいくつ？", answer,
                    f"分数の{'かけ算' if op == '×' else 'わり算'}をして約分すると {answer} です。")


def gen_decimal_muldiv(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    base = rng.randint(2, 45)
    left = base / 10
    factor = rng.randint(2, 9)
    if rng.choice([True, False]):
        result, op = left * factor, "×"
        right = factor
    else:
        result, op = left / factor, "÷"
        right = factor
    answer = fmt_number(round(result, 2))
    return Question(qid, "算数", grade, "decimal_muldiv", f"{fmt_number(left)} {op} {right} はいくつ？",
                    answer, f"{fmt_number(left)} {op} {right} = {answer} です。")


def gen_volume(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    a, b, c = (rng.randint(2, 10) for _ in range(3))
    answer = a * b * c
    return Question(qid, "算数", grade, "volume",
                    f"たて {a} cm、よこ {b} cm、高さ {c} cm の直方体の体積は何 cm³？", str(answer),
                    f"たて × よこ × 高さ = {a} × {b} × {c} = {answer} cm³ です。")


def gen_average(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    count = rng.randint(3, 5)
    mean = rng.randint(5, 20)
    for _ in range(100):
        deltas = [rng.randint(-3, 3) for _ in range(count - 1)]
        last = -sum(deltas)
        if abs(last) <= 3:
            break
    values = [mean + delta for delta in deltas + [last]]
    rng.shuffle(values)
    answer = fmt_number(mean)
    return Question(qid, "算数", grade, "average",
                    f"{'、'.join(map(str, values))} の平均はいくつ？", answer,
                    f"合計 {sum(values)} ÷ {count} = {answer} です。")


def gen_percent(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    whole = rng.choice([20, 25, 40, 50, 100])
    # 百分率が整数になる組み合わせだけを選び、解説と答えを一致させる
    percents = [percent for percent in range(5, 96, 5) if whole * percent % 100 == 0]
    percent = rng.choice(percents)
    part = whole * percent // 100
    correct = f"{percent}%"
    wrong = [f"{percent + rng.randint(5, 20)}%", f"{max(5, percent - rng.randint(5, 20))}%", f"{min(95, percent * 2)}%"]
    q = Question(qid, "算数", grade, "percent", f"{whole} 個のうち {part} 個は全体の何%？", correct,
                 f"{part} ÷ {whole} = {part / whole:.2f}、百分率にすると {correct} です。")
    q.choices = pick_choices(rng, correct, wrong)
    return q


def gen_proportion(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    unit = rng.randint(2, 12)
    first = rng.randint(2, 6)
    second = rng.randint(7, 12 if difficulty == "hard" else 10)
    answer = unit * second
    return Question(qid, "算数", grade, "proportion",
                    f"りんご {first} 個が {unit * first} 円です。同じ値段で {second} 個はいくら？",
                    str(answer), f"1 個あたり {unit} 円なので、{unit} × {second} = {answer} 円です。")


def _gen_circle(rng: random.Random, grade: int, difficulty: str, qid: str, topic: str) -> Question:
    radius = rng.randint(2, 10)
    if topic == "circle_length":
        result = 2 * 3.14 * radius
        prompt, note = f"半径 {radius} cm の円の円周の長さは何 cm？", "円周 = 直径 × 3.14 です。"
    else:
        result = 3.14 * radius * radius
        prompt, note = f"半径 {radius} cm の円の面積は何 cm²？", "円の面積 = 半径 × 半径 × 3.14 です。"
    answer = fmt_number(round(result, 2))
    q = Question(qid, "算数", grade, topic, prompt, answer, f"{note} 円周率(π)は3.14として {answer} です。")
    q.choices = pick_choices(rng, answer, [fmt_number(round(result + d, 2)) for d in (1.57, -1.57, 3.14)])
    return q


def gen_circle_length(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    return _gen_circle(rng, grade, difficulty, qid, "circle_length")


def gen_circle_area(rng: random.Random, grade: int, difficulty: str, qid: str) -> Question:
    return _gen_circle(rng, grade, difficulty, qid, "circle_area")


GENERATORS: dict = {
    "calc_add": gen_calc_add, "calc_sub": gen_calc_sub, "compare": gen_compare,
    "make_ten": gen_make_ten, "count_shapes": gen_count_shapes,
    "multiplication": gen_multiplication, "division": gen_division, "units": gen_units,
    "clock": gen_clock, "fraction_basic": gen_fraction_basic, "decimal_basic": gen_decimal_basic,
    "shape_perimeter": gen_shape_perimeter, "shape_area": gen_shape_area, "four_ops": gen_four_ops,
    "angle": gen_angle, "fraction_muldiv": gen_fraction_muldiv, "decimal_muldiv": gen_decimal_muldiv,
    "volume": gen_volume, "average": gen_average, "percent": gen_percent,
    "proportion": gen_proportion, "circle_length": gen_circle_length, "circle_area": gen_circle_area,
}


MATH_TOPICS: dict = {
    1: [("calc_add", "たし算（10以内）"), ("calc_sub", "ひき算（10以内）"),
        ("compare", "数の大小"), ("make_ten", "10をつくる"), ("count_shapes", "図形の数え上げ")],
    2: [("calc_add", "たし算（100以内）"), ("calc_sub", "ひき算（100以内）"),
        ("multiplication", "かけ算（九九）"), ("division", "わり算の基礎"),
        ("units", "長さ・重さ・時間の単位"), ("clock", "時計の読み")],
    3: [("calc_add", "たし算"), ("calc_sub", "ひき算"), ("multiplication", "かけ算"),
        ("division", "わり算"), ("fraction_basic", "分数の基礎"),
        ("decimal_basic", "小数の基礎"), ("shape_perimeter", "図形のまわり"),
        ("shape_area", "図形の面積"), ("units", "単位の変換")],
    4: [("four_ops", "四則混合"), ("calc_add", "たし算"), ("calc_sub", "ひき算"),
        ("fraction_basic", "分数のたし算・ひき算"), ("decimal_basic", "小数のたし算・ひき算"),
        ("shape_area", "図形の面積"), ("angle", "角度"), ("proportion", "割合の基礎")],
    5: [("four_ops", "四則混合"), ("fraction_muldiv", "分数のかけ算・わり算"),
        ("decimal_muldiv", "小数のかけ算・わり算"), ("percent", "割合と百分率"),
        ("volume", "体積"), ("average", "平均"), ("shape_area", "図形の面積")],
    6: [("four_ops", "四則混合"), ("fraction_muldiv", "分数のかけ算・わり算"),
        ("decimal_muldiv", "小数のかけ算・わり算"), ("percent", "割合の応用"),
        ("proportion", "比例の考え方"), ("circle_length", "円周"), ("circle_area", "円の面積"),
        ("average", "平均と統計")],
}
