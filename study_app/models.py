"""API のリクエスト／レスポンスモデル。"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    nickname: str = Field(min_length=1, max_length=12)
    pin: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")


class LoginRequest(BaseModel):
    pin: Optional[str] = None
    trusted: bool = False


class DeleteAccountRequest(BaseModel):
    pin: Optional[str] = None
    trusted: bool = False


class QuizRequest(BaseModel):
    grade: int = Field(default=1, ge=1, le=6)
    subject: str = "math"
    topics: List[str] = Field(default_factory=list)
    count: int = Field(default=10, ge=1, le=50)
    difficulty: str = "normal"
    adaptive: bool = False
    account_id: int


class AnswerRequest(BaseModel):
    question_id: str
    answer: str = ""


class QuizResponse(BaseModel):
    quiz_id: str
    grade: int
    subject: str
    total: int
    questions: List[dict]


class FarmAccountRequest(BaseModel):
    account_id: int


class FarmPlantRequest(BaseModel):
    account_id: int
    plot: int = Field(ge=0, le=17)
    crop: str


class FarmHarvestRequest(BaseModel):
    account_id: int
    plot: int = Field(ge=0, le=17)


class FarmAnimalBuyRequest(BaseModel):
    account_id: int
    animal: str


class FarmCollectRequest(BaseModel):
    account_id: int
    animal_id: int


class FarmBuildingRequest(BaseModel):
    account_id: int
    building: str


class FarmGatherRequest(BaseModel):
    account_id: int
    spot: str


class MissionClaimRequest(BaseModel):
    account_id: int
    mission_key: str


class FarmHireWorkerRequest(BaseModel):
    account_id: int
    worker_key: str


class FarmCollectWorkerRequest(BaseModel):
    account_id: int
    worker_key: str


class AnswerResponse(BaseModel):
    correct: bool
    correct_answer: str
    explanation: str
    answered: int
    total: int
    earned: int
    account: dict
