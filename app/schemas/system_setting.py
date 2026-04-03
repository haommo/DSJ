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
