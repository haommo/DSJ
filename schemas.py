from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# ============== Account Schemas ==============

class AccountCreate(BaseModel):
    account_code: str
    email: str
    password: str


class AccountUpdate(BaseModel):
    account_code: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


class AccountResponse(BaseModel):
    id: int
    account_code: str
    email: str

    class Config:
        from_attributes = True


# ============== Task Schemas ==============

class TaskCreate(BaseModel):
    task_code: str
    account_ids: Optional[List[int]] = None  # Nếu None, chạy tất cả accounts
    headless: bool = True  # True = ẩn browser, False = hiển browser (nhưng sẽ tự động ẩn xuống)


class TaskResponse(BaseModel):
    id: int
    task_code: str
    status: str
    total_accounts: int
    success_count: int
    failed_count: int
    total_balance: float
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ============== TaskDetail Schemas ==============

class TaskDetailItem(BaseModel):
    id: int
    account_code: str
    email: Optional[str] = None  # Email từ bảng Account
    balance: Optional[float] = None
    status: str
    result_message: Optional[str] = None
    screenshot_path: Optional[str] = None

    class Config:
        from_attributes = True


class TaskDetailResponse(TaskResponse):
    details: List[TaskDetailItem]


# ============== Pagination Schemas ==============

class PaginationMeta(BaseModel):
    page: int                 # Trang hiện tại (bắt đầu từ 1)
    page_size: int            # Số items mỗi trang
    total_items: int          # Tổng số items
    total_pages: int          # Tổng số trang
    has_next: bool            # Có trang tiếp không
    has_prev: bool            # Có trang trước không


class TaskListResponse(BaseModel):
    data: List[TaskDetailResponse]
    pagination: PaginationMeta


# ============== Statistics Schemas ==============

class Statistics(BaseModel):
    total_balance: float      # Tổng số dư
    total_accounts: int       # Tổng tài khoản
    total_tasks: int          # Tổng task
    success_rate: float       # Tỷ lệ thành công (%)
