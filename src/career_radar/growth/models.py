"""Strict model output contracts. Grades are never accepted as levels."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirement(StrictModel):
    skill: str = Field(min_length=1, max_length=100, description="一项独立能力或报名资格名称；Python 与 HTTP 必须分别列出，不能合并省略")
    quote: str = Field(min_length=1, max_length=2000)
    kind: Literal["skill", "hard", "bonus"] = Field(description="skill=所有必需技术能力，包含必须/熟练等措辞；hard=学历、届别、在校身份、正式工作年限等报名资格；bonus=明确优先/加分项。不能把必须会Python归为hard。")
    minimumLevel: int = Field(default=2, ge=1, le=5)


class JDAnalysis(StrictModel):
    requirements: list[Requirement] = Field(max_length=30)


class Question(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    code: str = Field(default="", max_length=8000)
    pointIds: list[str] = Field(min_length=1, max_length=8)
    expectedAnswer: str = Field(min_length=1, max_length=5000)
    mode: Literal["identify", "explain", "apply", "code", "implementation", "transfer"]


class QuestionOutput(StrictModel):
    question: Question


class PointGrade(StrictModel):
    pointId: str
    passed: bool
    answerQuote: str = Field(max_length=2000)
    reason: str = Field(min_length=1, max_length=1000)


class Grade(StrictModel):
    points: list[PointGrade] = Field(min_length=1, max_length=8)
    feedback: str = Field(min_length=1, max_length=4000)
    teaching: str = Field(min_length=1, max_length=6000)
    followup: Question | None = None


class Teaching(StrictModel):
    explanation: str = Field(min_length=1, max_length=6000)


class ProjectReview(StrictModel):
    feedback: str = Field(min_length=1, max_length=4000)
    points: list[PointGrade] = Field(min_length=1, max_length=8)
    question: Question
    runResultQuote: str = Field(default="", max_length=2000, description="仅从用户runRecord逐字复制实际提交的运行或测试结果；无记录、仅预期/计划、明确未运行时必须为空。不表示系统执行验证。")
