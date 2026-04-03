from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, selectinload
from typing import Optional
from datetime import datetime
import json
import asyncio

from app.database import get_db, SessionLocal
from app.models.user import User, UserRole
from app.models.account import Account
from app.models.task import Task, TaskDetail, TaskStatus, ResultStatus
from app.schemas.task import (
    TaskCreate, TaskResponse, TaskDetailItem, TaskDetailResponse,
    PaginationMeta, TaskListResponse,
)
from app.dependencies import get_current_user, require_roles
from app.services.account_service import get_customer_account_codes

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _build_detail_items(db: Session, details, current_user: User = None):
    """Helper: build TaskDetailItem list từ details (batch load accounts)"""
    codes = list({d.account_code for d in details})
    accounts_map = {}
    if codes:
        accounts = db.query(Account).filter(Account.account_code.in_(codes)).all()
        accounts_map = {a.account_code: a.email for a in accounts}

    items = []
    for d in details:
        items.append(TaskDetailItem(
            id=d.id, account_code=d.account_code,
            email=accounts_map.get(d.account_code),
            balance=d.balance, status=d.status,
            result_message=d.result_message, screenshot_path=d.screenshot_path,
        ))
    return items


# ============== CRUD ENDPOINTS ==============

@router.post("", response_model=TaskResponse)
async def create_task(
    task_data: TaskCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Tạo task mới và khởi chạy automation (Admin/Staff)"""
    existing = db.query(Task).filter(Task.task_code == task_data.task_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Task code already exists")

    if task_data.account_ids:
        accounts = db.query(Account).filter(Account.id.in_(task_data.account_ids)).all()
    else:
        accounts = db.query(Account).all()

    if not accounts:
        raise HTTPException(status_code=400, detail="No accounts available")

    try:
        db_task = Task(
            task_code=task_data.task_code,
            status=TaskStatus.PENDING,
            total_accounts=len(accounts),
            created_by=current_user.id,
        )
        db.add(db_task)
        db.flush()

        for account in accounts:
            db.add(TaskDetail(
                task_id=db_task.id,
                account_code=account.account_code,
                status=ResultStatus.PENDING,
            ))

        db.commit()
        db.refresh(db_task)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.run_task, db_task.id, task_data.headless)
    return db_task


@router.get("", response_model=TaskListResponse)
def get_tasks(
    page: int = 1,
    page_size: int = 5,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lấy danh sách tasks (Customer chỉ thấy tasks liên quan)"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    query = db.query(Task).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)

    # Customer chỉ thấy tasks có chứa accounts của mình
    if current_user.role == UserRole.CUSTOMER:
        account_codes = get_customer_account_codes(db, current_user)
        if account_codes:
            task_ids = db.query(TaskDetail.task_id).filter(
                TaskDetail.account_code.in_(account_codes)
            ).distinct().all()
            task_ids = [t[0] for t in task_ids]
            query = query.filter(Task.id.in_(task_ids))
        else:
            query = query.filter(Task.id == -1)  # No results

    total_items = query.count()
    total_pages = (total_items + page_size - 1) // page_size
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for task in tasks:
        details = db.query(TaskDetail).filter(TaskDetail.task_id == task.id).all()
        # Customer chỉ thấy details của accounts mình
        if current_user.role == UserRole.CUSTOMER:
            details = [d for d in details if d.account_code in account_codes]

        result.append(TaskDetailResponse(
            id=task.id, task_code=task.task_code, status=task.status,
            total_accounts=task.total_accounts, success_count=task.success_count,
            failed_count=task.failed_count, total_balance=task.total_balance,
            created_by=task.created_by, created_at=task.created_at,
            updated_at=task.updated_at,
            details=_build_detail_items(db, details),
        ))

    return TaskListResponse(
        data=result,
        pagination=PaginationMeta(
            page=page, page_size=page_size, total_items=total_items,
            total_pages=total_pages, has_next=page < total_pages, has_prev=page > 1,
        ),
    )


@router.get("/{task_id}", response_model=TaskDetailResponse)
def get_task_detail(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lấy chi tiết task"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    details = db.query(TaskDetail).filter(TaskDetail.task_id == task_id).all()

    if current_user.role == UserRole.CUSTOMER:
        account_codes = get_customer_account_codes(db, current_user)
        details = [d for d in details if d.account_code in account_codes]
        if not details:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

    return TaskDetailResponse(
        id=task.id, task_code=task.task_code, status=task.status,
        total_accounts=task.total_accounts, success_count=task.success_count,
        failed_count=task.failed_count, total_balance=task.total_balance,
        created_by=task.created_by, created_at=task.created_at,
        updated_at=task.updated_at,
        details=_build_detail_items(db, details),
    )


@router.delete("/{task_id}")
def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN, UserRole.STAFF)),
):
    """Xóa task (Admin/Staff)"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete running task")

    db.query(TaskDetail).filter(TaskDetail.task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return {"message": f"Task {task.task_code} deleted successfully"}


@router.delete("/{task_id}/force")
def force_delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Force xóa task bất kể trạng thái (Admin only)"""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    db.query(TaskDetail).filter(TaskDetail.task_id == task_id).delete()
    db.delete(task)
    db.commit()
    return {"message": f"Task {task.task_code} force deleted"}
