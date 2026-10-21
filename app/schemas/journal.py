from pydantic import BaseModel, Field


class AnnotationIn(BaseModel):
    setup_name: str | None = Field(default=None, max_length=120)
    trading_session_override: str | None = Field(default=None, max_length=20)
    market_condition: str | None = Field(default=None, max_length=80)
    entry_timeframe: str | None = Field(default=None, max_length=20)
    higher_timeframe_context: str | None = Field(default=None, max_length=255)
    entry_reason: str | None = Field(default=None, max_length=5000)
    exit_reason: str | None = Field(default=None, max_length=5000)
    rule_followed: bool | None = None
    emotional_state: str | None = Field(default=None, max_length=80)
    screenshot_ref: str | None = Field(default=None, max_length=500)
    personal_notes: str | None = Field(default=None, max_length=20000)
    mistakes: list[str] | None = Field(default=None, max_length=50)
    ict_tags: list[str] | None = Field(default=None, max_length=50)
    setup_tags: list[str] | None = Field(default=None, max_length=50)
    custom_tags: list[str] | None = Field(default=None, max_length=50)
