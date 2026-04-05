from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class SettingUpdate(BaseModel):
    value: str


class SettingResponse(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AutomationSettingsResponse(BaseModel):
    batch_size: int
    max_retries: int
    site_domain: str
    bg_signal_text: str


class FollowSettingsResponse(BaseModel):
    follow_confirm_text: str
    follow_done_text: str
    follow_completed_text: str
