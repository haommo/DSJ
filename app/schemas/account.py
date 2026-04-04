from pydantic import BaseModel
from typing import Optional


class AccountCreate(BaseModel):
    account_code: str
    email: str
    password: str
    owner_id: Optional[int] = None
    follow_active: bool = True


class AccountUpdate(BaseModel):
    account_code: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    owner_id: Optional[int] = None
    follow_active: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    account_code: str
    email: str
    owner_id: Optional[int] = None
    follow_active: bool = True

    class Config:
        from_attributes = True
