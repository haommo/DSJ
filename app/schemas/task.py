from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class TaskCreate(BaseModel):
    task_code: str
    account_ids: Optional[List[int]] = None
    headless: bool = True


class MissionCreate(BaseModel):
    account_ids: List[int]
    headless: bool = True
    scheduled_at: Optional[datetime] = None


class TaskResponse(BaseModel):
    id: int
    task_code: str
    status: str
    total_accounts: int
    success_count: int
    failed_count: int
    total_balance: float
    created_by: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class TaskDetailItem(BaseModel):
    id: int
    account_code: str
    email: Optional[str] = None
    balance: Optional[float] = None
    status: str
    result_message: Optional[str] = None
    screenshot_path: Optional[str] = None

    class Config:
        from_attributes = True


class TaskDetailResponse(TaskResponse):
    details: List[TaskDetailItem]


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool


class TaskListResponse(BaseModel):
    data: List[TaskDetailResponse]
    pagination: PaginationMeta


class Statistics(BaseModel):
    total_balance: float
    total_accounts: int
    total_tasks: int
    success_rate: float
