"""学習支援アプリの FastAPI エントリポイント。

起動方法（いずれも可）:
    python run_study.py
    python -m study_app.main
    python study_app/main.py
"""
from __future__ import annotations

# `python study_app/main.py` のように直接実行された場合でも相対 import を効かせる
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
    __package__ = "study_app"

import threading
import uuid
from collections import OrderedDict
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import DB_PATH, STATIC_DIR
from .generator.base import answers_match
from .generator.registry import config, generate_quiz
from .models import (
    AccountCreate, AnswerRequest, DeleteAccountRequest, FarmAccountRequest, FarmAnimalBuyRequest,
    FarmBuildingRequest, FarmCollectRequest, FarmGatherRequest, FarmHarvestRequest, FarmPlantRequest,
    LoginRequest, QuizRequest,
)
from .store import ProgressStore

app = FastAPI(title="まなびサポート", description="小学生向け 算数・国語 学習支援アプリ")
store = ProgressStore(DB_PATH)

_quizzes: "OrderedDict[str, dict]" = OrderedDict()
_quiz_lock = threading.Lock()
_MAX_QUIZZES = 100


def _save_quiz(payload: dict) -> str:
    quiz_id = uuid.uuid4().hex
    with _quiz_lock:
        _quizzes[quiz_id] = payload
        while len(_quizzes) > _MAX_QUIZZES:
            _quizzes.popitem(last=False)
    return quiz_id


def _get_quiz(quiz_id: str) -> dict:
    with _quiz_lock:
        quiz = _quizzes.get(quiz_id)
        if not quiz:
            raise HTTPException(status_code=404, detail="クイズが見つかりません。もう一度問題を出してください。")
        _quizzes.move_to_end(quiz_id)
        return quiz


def _account_or_404(account_id: int) -> dict:
    account = store.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="アカウントが見つかりません")
    return account


def _farm_action(action, *args):
    try:
        return action(*args)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


def _handle_account_error(error: Exception) -> None:
    if isinstance(error, LookupError):
        raise HTTPException(status_code=404, detail=str(error))
    if isinstance(error, (PermissionError, ValueError)):
        raise HTTPException(status_code=400, detail=str(error))
    raise error


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
def get_config():
    return config()


# ---------------- アカウント ----------------
@app.get("/api/accounts")
def list_accounts():
    return store.list_accounts()


@app.post("/api/accounts", status_code=201)
def create_account(request: AccountCreate):
    if any(item["nickname"] == request.nickname for item in store.list_accounts()):
        raise HTTPException(status_code=400, detail="同じなまえのアカウントがあります")
    account = store.create_account(request.nickname, request.pin)
    return store.login(account["id"], request.pin, trusted=True)


@app.get("/api/accounts/{account_id}")
def get_account(account_id: int):
    return _account_or_404(account_id)


@app.post("/api/accounts/{account_id}/login")
def login(account_id: int, request: LoginRequest):
    try:
        return store.login(account_id, request.pin, request.trusted)
    except (LookupError, PermissionError, ValueError) as error:
        _handle_account_error(error)


@app.post("/api/accounts/{account_id}/delete")
def delete_account(account_id: int, request: DeleteAccountRequest):
    try:
        store.delete_account(account_id, request.pin, request.trusted)
    except (LookupError, PermissionError, ValueError) as error:
        _handle_account_error(error)
    return {"ok": True}


@app.get("/api/accounts/{account_id}/progress")
def get_account_progress(account_id: int):
    try:
        return store.account_progress(account_id)
    except LookupError as error:
        _handle_account_error(error)


# ---------------- クイズ ----------------
@app.post("/api/quiz")
def create_quiz(request: QuizRequest):
    _account_or_404(request.account_id)
    questions = generate_quiz(
        subject=request.subject,
        grade=request.grade,
        topics=request.topics,
        count=request.count,
        difficulty=request.difficulty,
    )
    payload = {
        "account_id": request.account_id,
        "grade": request.grade,
        "subject": request.subject,
        "questions": {q.id: q for q in questions},
        "order": [q.id for q in questions],
        "answered": {},
        "rewarded": False,
    }
    return {
        "quiz_id": _save_quiz(payload),
        "grade": request.grade,
        "subject": request.subject,
        "total": len(questions),
        "questions": [q.public() for q in questions],
    }


@app.post("/api/quiz/{quiz_id}/answer")
def answer(quiz_id: str, request: AnswerRequest):
    quiz = _get_quiz(quiz_id)
    question = quiz["questions"].get(request.question_id)
    if not question:
        raise HTTPException(status_code=400, detail="問題が見つかりません。")

    account_id = quiz["account_id"]
    account = _account_or_404(account_id)

    # 二重送信でもポイントが増えないようにする
    if question.id in quiz["answered"]:
        return {
            "correct": quiz["answered"][question.id],
            "correct_answer": question.answer,
            "explanation": question.explanation,
            "answered": len(quiz["answered"]),
            "total": len(quiz["order"]),
            "earned": 0,
            "account": account,
        }

    correct = answers_match(request.answer, question.answer)
    store.record(question.subject, question.grade, question.topic, question.prompt,
                 correct, request.answer, question.answer, account_id)

    with _quiz_lock:
        quiz["answered"][question.id] = correct
        answered_count = len(quiz["answered"])
        completed = answered_count == len(quiz["order"]) and not quiz["rewarded"]
        if completed:
            quiz["rewarded"] = True
        correct_count = sum(1 for value in quiz["answered"].values() if value)

    # 正解10点／連続5回ごとにボーナス5点／間違えても参加点2点
    if correct:
        streak = account["streak"] + 1
        base, reason = 10, "正解"
        bonus = 5 if streak % 5 == 0 else 0
    else:
        streak = 0
        base, reason = 2, "がんばり点数"
        bonus = 0
    store.set_streak(account_id, streak)
    store.add_points(account_id, reason, base)
    if bonus:
        store.add_points(account_id, "連続正解ボーナス", bonus)
    earned = base + bonus

    if completed:
        rate = correct_count / len(quiz["order"])
        if rate == 1:
            completion = ("全問正解ボーナス", 50)
        elif rate >= 0.8:
            completion = ("よくできたボーナス", 20)
        else:
            completion = ("がんばりボーナス", 10)
        store.add_points(account_id, completion[0], completion[1])
        earned += completion[1]

    return {
        "correct": correct,
        "correct_answer": question.answer,
        "explanation": question.explanation,
        "answered": answered_count,
        "total": len(quiz["order"]),
        "earned": earned,
        "account": store.get_account(account_id),
    }


@app.get("/api/quiz/{quiz_id}/result")
def quiz_result(quiz_id: str):
    quiz = _get_quiz(quiz_id)
    answered = quiz["answered"]
    items = []
    for qid in quiz["order"]:
        question = quiz["questions"][qid]
        if qid not in answered:
            continue
        items.append({
            "prompt": question.prompt,
            "topic": question.topic,
            "correct": answered[qid],
            "correct_answer": question.answer,
            "explanation": question.explanation,
        })
    ok = sum(1 for item in items if item["correct"])
    return {"answered": len(items), "total": len(quiz["order"]), "correct": ok, "items": items}


# ---------------- 記録 ----------------
@app.get("/api/progress")
def get_progress(account_id: Optional[int] = Query(None)):
    if account_id is not None:
        return store.account_progress(account_id)
    return store.summary()


@app.delete("/api/progress")
def clear_progress(account_id: Optional[int] = Query(None)):
    store.clear(account_id)
    return {"ok": True}


# ---------------- 農場ゲーム ----------------
@app.get("/api/farm")
def get_farm(account_id: int):
    return _farm_action(store.get_farm, account_id)


@app.post("/api/farm/plant")
def farm_plant(request: FarmPlantRequest):
    return _farm_action(store.plant, request.account_id, request.plot, request.crop)


@app.post("/api/farm/harvest")
def farm_harvest(request: FarmHarvestRequest):
    return _farm_action(store.harvest, request.account_id, request.plot)


@app.post("/api/farm/buy-animal")
def farm_buy_animal(request: FarmAnimalBuyRequest):
    return _farm_action(store.buy_animal, request.account_id, request.animal)


@app.post("/api/farm/collect-animal")
def farm_collect_animal(request: FarmCollectRequest):
    return _farm_action(store.collect_animal, request.account_id, request.animal_id)


@app.post("/api/farm/buy-building")
def farm_buy_building(request: FarmBuildingRequest):
    return _farm_action(store.buy_building, request.account_id, request.building)


@app.post("/api/farm/gather")
def farm_gather(request: FarmGatherRequest):
    return _farm_action(store.gather, request.account_id, request.spot)


@app.post("/api/farm/expand")
def farm_expand(request: FarmAccountRequest):
    return _farm_action(store.expand_farm, request.account_id)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
