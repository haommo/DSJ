"""Mission routes: follow order automation (Admin only)."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timezone, timedelta

from app.database import get_db
from app.models.user import User, UserRole
from app.models.account import Account
from app.models.task import Task, TaskDetail, TaskStatus, ResultStatus, TaskType
from app.schemas.task import (
    MissionCreate, TaskResponse, TaskDetailItem, TaskDetailResponse,
    PaginationMeta, TaskListResponse,
)
from app.dependencies import require_roles

router = APIRouter(prefix="/missions", tags=["Missions"])


def _build_detail_items(db: Session, details):
    """Build TaskDetailItem list from details (batch load accounts)."""
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


@router.post("", response_model=TaskResponse)
async def create_mission(
    data: MissionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Tạo mission follow order (Admin only, bắt buộc chọn accounts)"""
    accounts = db.query(Account).filter(
        Account.id.in_(data.account_ids),
        Account.follow_active == True,
    ).all()
    if not accounts:
        raise HTTPException(status_code=400, detail="No valid accounts found (check follow_active status)")

    vn_tz = timezone(timedelta(hours=7))
    task_code = f"MISSION-{datetime.now(vn_tz).strftime('%Y%m%d-%H%M%S')}"
    is_scheduled = data.scheduled_at is not None
    scheduled_at_aware = data.scheduled_at.replace(tzinfo=vn_tz) if is_scheduled else None

    try:
        db_task = Task(
            task_code=task_code,
            task_type=TaskType.MISSION,
            status=TaskStatus.SCHEDULED if is_scheduled else TaskStatus.PENDING,
            total_accounts=len(accounts),
            created_by=current_user.id,
            headless=data.headless,
            scheduled_at=scheduled_at_aware,
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
        raise HTTPException(status_code=500, detail=f"Failed to create mission: {str(e)}")

    if not is_scheduled:
        from app.services.task_manager import task_manager
        background_tasks.add_task(task_manager.run_task, db_task.id, data.headless)
    return db_task


@router.get("", response_model=TaskListResponse)
def get_missions(
    page: int = 1,
    page_size: int = 5,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Lấy danh sách missions (Admin only)"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    query = db.query(Task).filter(Task.task_type == TaskType.MISSION).order_by(Task.created_at.desc())
    if status:
        query = query.filter(Task.status == status)

    total_items = query.count()
    total_pages = (total_items + page_size - 1) // page_size
    tasks = query.offset((page - 1) * page_size).limit(page_size).all()

    result = []
    for task in tasks:
        details = db.query(TaskDetail).filter(TaskDetail.task_id == task.id).all()
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


@router.get("/{mission_id}", response_model=TaskDetailResponse)
def get_mission_detail(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Lấy chi tiết mission"""
    task = db.query(Task).filter(Task.id == mission_id, Task.task_type == TaskType.MISSION).first()
    if not task:
        raise HTTPException(status_code=404, detail="Mission not found")

    details = db.query(TaskDetail).filter(TaskDetail.task_id == mission_id).all()
    return TaskDetailResponse(
        id=task.id, task_code=task.task_code, status=task.status,
        total_accounts=task.total_accounts, success_count=task.success_count,
        failed_count=task.failed_count, total_balance=task.total_balance,
        created_by=task.created_by, created_at=task.created_at,
        updated_at=task.updated_at,
        details=_build_detail_items(db, details),
    )


@router.post("/{mission_id}/cancel")
def cancel_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Hủy mission đang chạy"""
    task = db.query(Task).filter(Task.id == mission_id, Task.task_type == TaskType.MISSION).first()
    if not task:
        raise HTTPException(status_code=404, detail="Mission not found")
    if task.status != TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Mission is not running")

    from app.services.task_manager import task_manager
    task_manager.cancel_task(mission_id)
    return {"message": "Mission cancelled"}


@router.post("/{mission_id}/retry/{detail_id}")
async def retry_mission_detail(
    mission_id: int,
    detail_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Chạy lại một account cụ thể trong mission"""
    task = db.query(Task).filter(Task.id == mission_id, Task.task_type == TaskType.MISSION).first()
    if not task:
        raise HTTPException(status_code=404, detail="Mission not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot retry while mission is running")

    detail = db.query(TaskDetail).filter(
        TaskDetail.id == detail_id, TaskDetail.task_id == mission_id
    ).first()
    if not detail:
        raise HTTPException(status_code=404, detail="Detail not found")
    if detail.status not in [ResultStatus.FAILED, ResultStatus.PENDING]:
        raise HTTPException(status_code=400, detail=f"Can only retry failed/pending. Current: {detail.status}")

    if detail.status == ResultStatus.FAILED:
        task.failed_count = max(0, task.failed_count - 1)

    detail.status = ResultStatus.PENDING
    detail.result_message = None
    detail.balance = None
    detail.screenshot_path = None
    db.commit()

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.retry_single_detail, mission_id, detail_id, headless)
    return {"message": f"Retrying account {detail.account_code}"}


@router.post("/{mission_id}/retry-all")
async def retry_all_failed_mission(
    mission_id: int,
    headless: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Chạy lại tất cả accounts failed trong mission"""
    task = db.query(Task).filter(Task.id == mission_id, Task.task_type == TaskType.MISSION).first()
    if not task:
        raise HTTPException(status_code=404, detail="Mission not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Mission is already running")

    failed_details = db.query(TaskDetail).filter(
        TaskDetail.task_id == mission_id, TaskDetail.status == ResultStatus.FAILED
    ).all()
    if not failed_details:
        return {"message": "No failed accounts to retry", "count": 0}

    for detail in failed_details:
        detail.status = ResultStatus.PENDING
        detail.result_message = None
        detail.balance = None
        detail.screenshot_path = None
        task.failed_count -= 1
    db.commit()

    from app.services.task_manager import task_manager
    background_tasks.add_task(task_manager.run_task, mission_id, headless)
    return {"message": f"Retrying {len(failed_details)} failed accounts", "count": len(failed_details)}


@router.delete("/{mission_id}")
def delete_mission(
    mission_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Xóa mission"""
    task = db.query(Task).filter(Task.id == mission_id, Task.task_type == TaskType.MISSION).first()
    if not task:
        raise HTTPException(status_code=404, detail="Mission not found")
    if task.status == TaskStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cannot delete running mission")

    db.query(TaskDetail).filter(TaskDetail.task_id == mission_id).delete()
    db.delete(task)
    db.commit()
    return {"message": f"Mission {task.task_code} deleted successfully"}
