from typing import Literal

from pydantic import BaseModel


class StartSessionRequest(BaseModel):
    scenario_id: str
    mode: Literal["smart", "naive"] = "smart"
    language: Literal["en", "es"] = "en"


class StartSessionResponse(BaseModel):
    session_id: str
    scenario_title: str
    scenario_subtitle: str
    property: str
    mode: str
    language: str
    script: list[str]  # scripted caller lines the frontend can step through


class MessageRequest(BaseModel):
    text: str


class MessageResponse(BaseModel):
    turn_index: int
    caller_text: str
    agent_reply: str
    mode: str
    # Present only in "smart" mode:
    intent_confidence: float | None = None
    data_sufficiency: float | None = None
    sensitivity_flag: bool | None = None
    sensitivity_reason: str | None = None
    decision: str | None = None
    reason: str | None = None
    handoff: dict | None = None


class SpeakRequest(BaseModel):
    text: str
    language: Literal["en", "es"] = "en"
