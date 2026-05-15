from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Any, Dict
from datetime import datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    provider: Optional[str] = None   # e.g. "openai", "deepseek", "qwen", "kimi"
    model: Optional[str] = None      # override model name
    api_key: Optional[str] = None    # user-provided API key (overrides env var)


class SkillSpec(BaseModel):
    name: str = ""
    description: str = ""
    role: str = ""
    workflow: List[str] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    exceptions: List[str] = Field(default_factory=list)
    output_format: str = ""


class SkillEvaluation(BaseModel):
    """Evaluation record for a generated skill, cached for feedback collection."""
    evaluation_id: str = ""
    conversation_id: str = ""
    score: int = 0                          # overall 0-100
    dimensions: Dict[str, int] = Field(default_factory=dict)  # per-dimension scores
    feedback: str = ""                      # narrative feedback
    suggestions: List[str] = Field(default_factory=list)  # actionable improvements
    created_at: str = ""


class Draft(BaseModel):
    conversation_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
    spec: SkillSpec = Field(default_factory=SkillSpec)
    attachments: List[str] = Field(default_factory=list)
    history_summary: Optional[str] = None  # compressed summary of older messages


class TestRequest(BaseModel):
    skill_spec: SkillSpec
    query: str


class TestResponse(BaseModel):
    answer: str
    checks: List[str]
    score: int
    tool_calls: List[Any] = Field(default_factory=list)
